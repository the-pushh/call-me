"""Twilio media WebSocket — the audio transport (Step 1: greeting + echo).

This is the only place audio crosses between Twilio and our stack. It stays
deliberately THIN: the async WebSocket handler does nothing but move bytes
on/off two queues. All the blocking work (TTS synthesis, transcode, resample)
happens on a worker THREAD, so the event loop never stalls.

--- WebSocket, in one breath ---
Unlike HTTP (one request, one response, done), a WebSocket is a single
long-lived pipe both sides can write to at any time. Twilio's TwiML
(<Connect><Stream>) tells Twilio to open this pipe when the call connects, then
streams the caller's audio over it as a series of JSON `media` frames — each one
~20 ms of base64-encoded mu-law (160 samples @ 8 kHz). We write `media` frames
back the same way and Twilio plays them to the caller.

--- The thread<->asyncio bridge ---
The handler below runs on asyncio's event loop. The worker runs on a normal
thread. They hand audio across that boundary through `queue.Queue`, which is
thread-safe. Going async -> thread is trivial (`q.put`). The hard direction is
thread -> async: the async sender must wait for the next outbound frame WITHOUT
blocking the loop, so it does `await loop.run_in_executor(None, q.get)` — the
blocking `.get()` runs on a threadpool and the loop stays free until a frame
arrives. This same bridge will later carry transcript/state events to the
browser (Step 3).
"""

import asyncio
import base64
import json
import queue
import threading

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from audio_formatting import int16_to_float, float_to_int16
from twilio_audio import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    Resampler,
    FrameAccumulator,
)
import tts
from greetings import pick_greeting

ws_router = APIRouter()

# Sentinel pushed onto a queue to mean "no more items — shut down". Using a
# unique object (not None) avoids any clash with a real payload.
_STOP = object()


def greeting_then_echo(persona, inbound_q, outbound_q, stop_event):
    """Worker thread: speak the greeting, then echo the caller back to themselves.

    Step 1 has no VAD/Brain — this exists purely to prove the transport and the
    transcode boundary on live audio. The greeting exercises the OUTBOUND TTS
    path (24k -> 8k); the echo exercises the INBOUND path (8k -> 16k -> 512-frame
    -> back to 8k), which is exactly the chain VAD/STT will sit on in Step 2.
    """
    # Three resamplers, each created ONCE and reused for every chunk. ratecv is
    # a stateful filter; a fresh instance per chunk restarts it and clicks at
    # every ~20ms boundary. One instance per direction = one continuous filter.
    greet_rs = Resampler(24000, 8000)   # TTS native rate -> phone rate
    in_rs = Resampler(8000, 16000)      # phone -> stack rate (for VAD later)
    out_rs = Resampler(16000, 8000)     # stack rate -> phone rate
    acc = FrameAccumulator()

    # --- 1. greeting (bot speaks first) ---
    greeting = pick_greeting(persona)
    print(f"[media] greeting ({persona}): {greeting!r}")
    for pcm24 in tts.synthesize(greeting, stop_event=stop_event):
        if stop_event.is_set():
            break
        # pcm24 is whole-sample int16 bytes @ 24k -> resample -> mu-law -> out
        outbound_q.put(pcm16_to_mulaw(greet_rs.process(pcm24)))

    # --- 2. echo (caller hears themselves) ---
    while not stop_event.is_set():
        raw = inbound_q.get()                 # blocks until the WS handler feeds a frame
        if raw is _STOP:
            break

        pcm16_16k = in_rs.process(mulaw_to_pcm16(raw))
        f32 = int16_to_float(np.frombuffer(pcm16_16k, dtype=np.int16))

        # Twilio's 20ms frames don't divide into 512, so the accumulator hands
        # back only complete 512-sample frames (and carries the remainder). This
        # is where VAD will plug in at Step 2 — same frames, just inspected
        # instead of echoed.
        for frame in acc.feed(f32):
            pcm16_8k = out_rs.process(float_to_int16(frame).tobytes())
            outbound_q.put(pcm16_to_mulaw(pcm16_8k))

    outbound_q.put(_STOP)   # release the sender


async def _sender(websocket: WebSocket, outbound_q, stream_sid, stop_event):
    """Drain outbound mu-law frames and send them to Twilio as `media` messages."""
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():
        payload = await loop.run_in_executor(None, outbound_q.get)
        if payload is _STOP:
            break
        msg = {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(payload).decode("ascii")},
        }
        await websocket.send_text(json.dumps(msg))


@ws_router.websocket("/media")
async def media_ws(websocket: WebSocket):
    await websocket.accept()

    inbound_q: queue.Queue = queue.Queue()
    outbound_q: queue.Queue = queue.Queue()
    stop_event = threading.Event()
    worker: threading.Thread | None = None
    sender_task: asyncio.Task | None = None
    stream_sid: str | None = None

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            event = data.get("event")

            if event == "start":
                # `start` carries the streamSid (needed to address outbound
                # frames) and our custom parameters (the persona relayed from
                # TwiML — third and final hop of query -> Parameter -> start).
                start = data["start"]
                stream_sid = start["streamSid"]
                persona = start.get("customParameters", {}).get("persona", "eve")
                print(f"[media] start sid={stream_sid} persona={persona}")

                worker = threading.Thread(
                    target=greeting_then_echo,
                    args=(persona, inbound_q, outbound_q, stop_event),
                    daemon=True,
                )
                worker.start()
                sender_task = asyncio.create_task(
                    _sender(websocket, outbound_q, stream_sid, stop_event)
                )

            elif event == "media":
                # base64 mu-law -> raw mu-law bytes -> hand to the worker. That's
                # ALL the handler does with audio; everything else is on the thread.
                raw = base64.b64decode(data["media"]["payload"])
                inbound_q.put(raw)

            elif event == "stop":
                print(f"[media] stop sid={stream_sid}")
                break

            # `connected` (and anything else) needs no action.

    except WebSocketDisconnect:
        print(f"[media] disconnected sid={stream_sid}")
    finally:
        # One teardown path for stop, disconnect, or error: signal both the
        # worker and the sender to unwind, then wait for them.
        stop_event.set()
        inbound_q.put(_STOP)
        outbound_q.put(_STOP)
        if sender_task is not None:
            try:
                await sender_task
            except Exception:
                pass
        if worker is not None:
            worker.join(timeout=2.0)

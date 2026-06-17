"""Twilio media WebSocket — the audio transport.

This file stays THIN: the async WebSocket handler only moves bytes on and off
two queues. All the real work (listening, transcribing, thinking, speaking)
lives in a CallSession on a worker thread, so the event loop never stalls.

--- WebSocket, plainly ---
A normal web request is one question, one answer, then it's over. A WebSocket is
a phone line that stays open: both sides can talk whenever they want. Twilio's
call instructions (the <Connect><Stream> TwiML) tell Twilio to open this line
when the call connects, then it sends the caller's audio as a stream of small
JSON messages — each one about 20 ms of compressed (mu-law) sound. We send sound
back the same way and Twilio plays it to the caller.

--- Passing audio between the two worlds ---
This handler runs on the async event loop. The CallSession runs on a plain
thread. They pass audio through queues (queue.Queue is safe to share across
threads). Putting audio in from the async side is easy. Getting audio back out
to the async side is the tricky direction: the sender below uses
`run_in_executor` so the "wait for the next piece of audio" step happens off to
the side and the event loop stays free to keep receiving from Twilio.
"""

import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from orchestrator import CallSession, STOP
import transcript_socket

ws_router = APIRouter()


async def _sender(websocket: WebSocket, session: CallSession):
    """Take finished audio off the session and send it to Twilio."""
    loop = asyncio.get_running_loop()
    while not session.stop_event.is_set():
        payload = await loop.run_in_executor(None, session.outbound_q.get)
        if payload is STOP:
            break
        msg = {
            "event": "media",
            "streamSid": session.stream_sid,
            "media": {"payload": base64.b64encode(payload).decode("ascii")},
        }
        await websocket.send_text(json.dumps(msg))


@ws_router.websocket("/media")
async def media_ws(websocket: WebSocket):
    await websocket.accept()

    session: CallSession | None = None
    sender_task: asyncio.Task | None = None

    try:
        while True:
            data = json.loads(await websocket.receive_text())
            event = data.get("event")

            if event == "start":
                # `start` carries the streamSid (the address for sending audio
                # back) and the persona we relayed through the TwiML.
                start = data["start"]
                persona = start.get("customParameters", {}).get("persona", "eve")
                call_sid = start.get("callSid")
                print(f"[media] start sid={start['streamSid']} call={call_sid} persona={persona}")

                # Every state/transcript event the session emits gets fanned to
                # the browsers watching THIS call. The closure binds call_sid so
                # the session itself stays ignorant of the watch socket.
                emit = lambda event, **data: transcript_socket.push(call_sid, event, **data)

                # call_sid lets the session collect the greeting pre-warmed
                # during the ring (see audio_cache / main's /call endpoint).
                session = CallSession(persona, call_sid=call_sid, emit=emit)
                session.stream_sid = start["streamSid"]
                session.start()
                sender_task = asyncio.create_task(_sender(websocket, session))

            elif event == "media" and session is not None:
                # base64 -> raw mu-law bytes -> hand to the session. That's all
                # this handler does with audio.
                session.feed_inbound(base64.b64decode(data["media"]["payload"]))

            elif event == "stop":
                print("[media] stop")
                break

    except WebSocketDisconnect:
        print("[media] disconnected")
    finally:
        # One teardown path for stop / disconnect / error.
        if session is not None:
            session.stop()
            session.outbound_q.put(STOP)   # release the sender
        if sender_task is not None:
            try:
                await sender_task
            except Exception:
                pass

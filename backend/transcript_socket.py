"""Watch socket — the browser's window into one live call.

The phone carries the AUDIO (media_socket); this carries the STORY of the call
to the screen: state changes, the user's transcript, the bot's sentences. The
browser opens `ws /watch/{call_sid}` and receives a stream of JSON events.

The event contract (everything the frontend needs):
    {"event":"state", "value":"calling|connected|listening|thinking|speaking|ended"}
    {"event":"level", "value": <float 0..1>}          # Step 4, during LISTENING
    {"event":"user_transcript", "text": <str>}        # one user bubble, end of turn
    {"event":"assistant_sentence", "text": <str>}     # bot bubble, per sentence

--- The thread -> async hop (the one subtle part) ---
Events are produced by the CallSession's WORKER THREAD (`emit(...)` -> push()).
The sockets, though, live on the asyncio event loop, and asyncio.Queue is NOT
thread-safe. So push() never touches the queues directly: it uses
`loop.call_soon_threadsafe` to schedule the fan-out ON the loop thread, where
`put_nowait` is safe. Same bridge idea as media_socket's outbound sender, the
other direction.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

router = APIRouter()

# call_sid -> set of per-subscriber queues. One queue per open browser socket, so
# two tabs watching the same call each get their own copy. Touched only on the
# loop thread (push hops onto it), so no lock needed.
_subscribers: dict[str, set[asyncio.Queue]] = {}

# call_sid -> ordered list of the call's MEANINGFUL events (state changes,
# transcripts — NOT the high-rate `level` stream). Replayed to a socket the
# moment it subscribes, so an event fired in the gap before the browser's watch
# socket attached (e.g. the bot's greeting, pushed the instant the call is
# answered) still reaches the transcript instead of being dropped.
#
# History is kept for the life of the process (capped, see below) — NOT cleared
# when a watcher disconnects. A browser socket can briefly drop and reconnect
# (React strict-mode double-mounts the hook in dev, flaky networks in prod); if
# we wiped history on the first close, the reconnect would replay nothing and the
# greeting would vanish. Instead we bound memory by retaining only the most
# recent calls.
_history: dict[str, list[str]] = {}
_HISTORY_CAP = 300          # max events kept per call
_MAX_CALLS = 40             # max distinct calls retained (oldest evicted)

# The main event loop, captured at startup. push() runs on worker threads and
# needs this handle to hop back onto the loop.
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop):
    """Called once from the app lifespan so push() knows the loop to hop onto."""
    global _loop
    _loop = loop


def push(call_sid: str, event: str, **data):
    """Fan one event out to every browser watching `call_sid`.

    Safe to call from any thread. If nobody is watching (or we ran before the
    loop was captured), it's a no-op — events for an unwatched call just drop,
    which is fine: the screen only needs what happens while it's looking."""
    if _loop is None or not call_sid:
        return
    msg = json.dumps({"event": event, **data})

    def _fan():
        # Remember everything but the firehose `level` events, so a late
        # subscriber can be caught up without replaying thousands of amplitudes.
        if event != "level":
            if call_sid not in _history and len(_history) >= _MAX_CALLS:
                # Evict the oldest call's buffer (dicts preserve insertion order).
                del _history[next(iter(_history))]
            hist = _history.setdefault(call_sid, [])
            hist.append(msg)
            if len(hist) > _HISTORY_CAP:
                del hist[: len(hist) - _HISTORY_CAP]
        for q in _subscribers.get(call_sid, ()):
            q.put_nowait(msg)

    _loop.call_soon_threadsafe(_fan)


@router.websocket("/watch/{call_sid}")
async def watch(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(call_sid, set()).add(q)

    # Catch this socket up on anything that already happened (the greeting fires
    # the instant the call is answered, often just before the browser attaches).
    for past in list(_history.get(call_sid, ())):
        q.put_nowait(past)

    # The browser doesn't send us anything; this reader exists only to NOTICE
    # when it closes the socket, so we can stop and clean up the subscriber.
    async def _watch_for_close():
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            pass

    reader = asyncio.create_task(_watch_for_close())
    try:
        while not reader.done():
            # Stop the instant the socket leaves CONNECTED. Without this there's
            # a race: the browser closes (or Twilio teardown closes us) between
            # the reader noticing and the next send, and send_text on an
            # already-closed socket raises a RuntimeError ("Unexpected ASGI
            # message ... after sending 'websocket.close'") that isn't a
            # WebSocketDisconnect, so it escaped as a 500.
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            # Wake up periodically even with no events so a browser-side close
            # (reader.done()) is noticed promptly instead of blocking forever.
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await websocket.send_text(msg)
            except (WebSocketDisconnect, RuntimeError):
                # Closed underneath us between the state check and the send —
                # nothing left to do but clean up.
                break
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        subs = _subscribers.get(call_sid)
        if subs:
            subs.discard(q)
            if not subs:
                _subscribers.pop(call_sid, None)
        # NB: _history is intentionally NOT cleared here — a reconnecting watcher
        # must still be able to replay the greeting. It's bounded by _MAX_CALLS.

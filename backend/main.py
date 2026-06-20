"""FastAPI app + route wiring for CallMe.

Two planes meet here:
  - telephony.router : HTTP control plane (place call, TwiML, status webhooks)
  - media_socket.ws_router : the /media WebSocket carrying the audio
The `POST /call` endpoint lets us trigger a test call without the frontend
(which arrives in Step 3).
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import telephony
import media_socket
import transcript_socket
import feedback
import audio_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hand the running event loop to the watch socket. Call events are produced
    # on worker THREADS; push() needs this handle to hop them back onto the loop
    # (call_soon_threadsafe) where the sockets live.
    transcript_socket.set_loop(asyncio.get_running_loop())

    # Build the filler clips once, in the background, so the server is usable
    # immediately. If a call arrives before they're ready, that turn simply
    # skips the filler (get_filler returns None) — no error, just no "umm".
    asyncio.create_task(asyncio.to_thread(audio_cache.build_fillers))
    yield


app = FastAPI(lifespan=lifespan)

# The frontend (a different origin in dev — localhost:3000) calls POST /call and
# opens the /watch socket. Permissive here because it's a local dev tool; lock
# allow_origins down to the real frontend domain before any deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telephony.router)
app.include_router(media_socket.ws_router)
app.include_router(transcript_socket.router)
app.include_router(feedback.router)


class CallRequest(BaseModel):
    to: str
    persona: str = "eve"


@app.get("/")
def read_root():
    return {"message": "Welcome to the Call-Me API!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/call")
async def call(req: CallRequest):
    """Dial out and bridge the call to the bot. Returns the Twilio call SID."""
    call_sid = await telephony.place_call(req.to, req.persona)
    # Make the opener NOW, during the ring — by pickup it's ready to play
    # instantly. Fire-and-forget on a thread so the response returns immediately.
    asyncio.create_task(
        asyncio.to_thread(audio_cache.prewarm_greeting, call_sid, req.persona)
    )
    return {"call_sid": call_sid}

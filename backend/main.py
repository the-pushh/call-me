"""FastAPI app + route wiring for CallMe.

Two planes meet here:
  - telephony.router : HTTP control plane (place call, TwiML, status webhooks)
  - media_socket.ws_router : the /media WebSocket carrying the audio
The `POST /call` endpoint lets us trigger a test call without the frontend
(which arrives in Step 3).
"""

from fastapi import FastAPI
from pydantic import BaseModel

import telephony
import media_socket

app = FastAPI()

app.include_router(telephony.router)
app.include_router(media_socket.ws_router)


class CallRequest(BaseModel):
    to: str
    persona: str = "eve"


@app.get("/")
def read_root():
    return {"message": "Welcome to the Call-Me API!"}


@app.post("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/call")
async def call(req: CallRequest):
    """Dial out and bridge the call to the bot. Returns the Twilio call SID."""
    call_sid = await telephony.place_call(req.to, req.persona)
    return {"call_sid": call_sid}

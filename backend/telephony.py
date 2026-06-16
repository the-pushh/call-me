"""Twilio control plane — placing calls and the call's lifecycle webhooks.

This is the SIGNALLING side of the call (who to dial, what to do when answered,
status updates). The actual audio rides a separate WebSocket handled in
media_socket.py. The one link between them: the TwiML returned here tells Twilio
to open that media WebSocket, and smuggles the `persona` along so the media
socket knows which character to be.
"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

from config import (
    TWILLIO_SID,
    TWILLIO_AUTH_TOKEN,
    FROM_NUMBER,
    PUBLIC_BASE_URL,
    CALL_TIME_LIMIT,
)

router = APIRouter()
client = Client(TWILLIO_SID, TWILLIO_AUTH_TOKEN)


async def place_call(to_number: str, persona: str) -> str:
    """Dial `to_number`, hand Twilio the persona, return the call SID.

    The Twilio SDK is blocking (it makes a synchronous HTTP call). We run it via
    asyncio.to_thread so it never stalls the event loop — the same discipline
    the media socket follows for all its heavy work.
    """
    call = await asyncio.to_thread(
        client.calls.create,
        to=to_number,
        from_=FROM_NUMBER,
        # When the callee answers, Twilio fetches this URL for instructions.
        # persona rides as a query param — first hop of the relay that ends at
        # the media socket's `start` message.
        url=f"{PUBLIC_BASE_URL}/twiml?persona={persona}",
        status_callback=f"{PUBLIC_BASE_URL}/call-status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        # Hard cap enforced carrier-side. When it trips, Twilio sends the SAME
        # `stop`/`completed` events as a normal hang-up, so teardown has one path.
        time_limit=CALL_TIME_LIMIT,
    )
    return call.sid


@router.api_route("/twiml", methods=["GET", "POST"])
async def twiml_handler(request: Request):
    """Webhook Twilio hits on answer. We tell it to open a 2-way audio stream.

    <Connect><Stream> (NOT <Start>) makes the media WebSocket BIDIRECTIONAL —
    <Start> would only stream the caller's audio TO us; <Connect> also lets us
    stream audio BACK so the bot can be heard. The <Parameter> carries persona
    into the stream's `start` message (second relay hop: query -> Parameter).
    """
    persona = request.query_params.get("persona", "eve")

    # Build the wss URL from the same Host that reached us, so it works behind
    # ngrok/any tunnel without hardcoding the public domain twice.
    host = request.headers["host"]
    stream_url = f"wss://{host}/media"

    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=stream_url)
    stream.parameter(name="persona", value=persona)
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


@router.post("/call-status")
async def call_status(request: Request):
    """Twilio lifecycle events (initiated/ringing/answered/completed).

    Step 1 just logs them. Mapping these to frontend states lands in Step 3 once
    the watch socket exists.
    """
    form = await request.form()
    call_sid = form.get("CallSid")
    status = form.get("CallStatus")
    print(f"[call-status] {call_sid} -> {status}")

    return Response(status_code=204)

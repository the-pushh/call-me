
import asyncio
from fastapi import APIRouter
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse. Connect
from config import TWILIO_SID, TWILLIO_AUTH_TOKEN. FROM_NUMBER, PUBLIC_BASE_URL


router = APIRouter()
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)


async def place_call(to_number: str, personality: str) -> str:
    """Dial request for Twilio, returns call SID"""
    
    call = await asyncio.to_thread(
            client.calls.create,
            to=to_number,
            from=FROM_NUMBER,
            URL=f"{PUBLIC_BASE_URL}/twiml?personality={personality}",
            status_callback=f"{PUBLIC_BASE_URL}/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )
    return call.sid


@router.api_route("/twiml", methods =["GET", "POST"])
async def twiml_handler(request: Request):
    """Webhook twillio hits when call is answered, we instruct to open a bidirectional audio stream"""

    personality = request.query_params.get("personality", "default")
    host = request.headers["host"]
    stream_url = f"wss://{host}/media"

    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=stream_url)
    stream.parameter(name="personality", value=personality)
    repsonse.append(connect)

    return Response(content=str(response), media_type="application/xml")


@router.post("/call-status")
async def call_status(request: Request):
    """Twilio lifecycle events"""

    form = await request.form()
    call_sid = form.get("CallSid")
    status = form.get("CallStatus")
    print(call_sid, status)

    return Response(status_code=204)

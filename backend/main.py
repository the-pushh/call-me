import os
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response
from dotenv import load_dotenv
from twilio.rest import Client
import json
import base64
from config import TWILLIO_SID, TWILLIO_AUTH_TOKEN, FROM_NUMBER, PUBLIC_BASE_URL

app = FastAPI()

load_dotenv()  # Load environment variables from .env file

@app.get("/")
def read_root():
    return {"message": "Welcome to the Call-Me API!"}

@app.post("/health")
def health_check():
    return {"status": "healthy"}

client = Client(TWILLIO_SID, TWILLIO_AUTH_TOKEN)

@app.post("/make-call")
async def make_call(to_number: str):
    call = client.calls.create(
        to=to_number,
        from_=FROM_NUMBER,
        twiml="<Response><Say>Hello, this is a test call.</Say></Response>"
    )
    return {"call_sid": call.sid}


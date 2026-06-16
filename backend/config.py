from dotenv import load_dotenv
import os

load_dotenv()

TWILLIO_SID = os.getenv("TWILLIO_SID")
TWILLIO_AUTH_TOKEN = os.getenv("TWILLIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("FROM_NUMBER")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

TWILLIO_RATE = 8000
PCM_RATE = 16000
SILENCE_TIMEOUT_MS = 500

# Hard cap on call length. Enforced CARRIER-SIDE by Twilio via the call's
# `time_limit` param, not by a backend timer — Twilio then fires `stop` +
# `completed`, giving us ONE teardown path for both hang-up and timeout.
CALL_TIME_LIMIT = 60   # seconds


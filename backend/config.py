from dotenv import load_dotenv
import os

load_dotenv()

TWILLIO_SID = os.getenv("TWILLIO_SID")
TWILLIO_AUTH_TOKEN = os.getenv("TWILLIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("FROM_NUMBER")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

# --- TTS backend selection (config-driven, not hardcoded) ------------------
# Which engine renders speech, and which one we fall back to. Swapping these is
# the whole point of the dispatcher in tts.py: set TTS_PRIMARY="kokoro" and the
# whole call path uses Kokoro, no code change. Voice ids per persona live in the
# backend modules (tts_cartesia.VOICES / tts_kokoro.VOICES).
TTS_PRIMARY = "cartesia"
TTS_FALLBACK = "kokoro"

CARTESIA_MODEL_ID = "sonic-3.5"        # current Sonic model — verify in docs
CARTESIA_BASELINE_EMOTION = "content"  # default emotion when a line has no tag

# Speech rate. BOTH engines take a multiplier where 1.0 is normal speed, so
# 0.6 ≈ 40% slower on each. Cartesia's generation_config.speed is documented as
# 0.6..1.5; Kokoro/OpenAI speech accepts 0.25..4.0. Keep them matched so the
# voice doesn't change pace when we fall back.
CARTESIA_SPEED = 0.85   # Cartesia valid range 0.6..1.5 — 0.6 is the slowest
KOKORO_SPEED = 0.95   # Kokoro valid range 0.25..4.0 — match Cartesia for consistency

# Fast-detection budget: how long to wait for Cartesia's connect / next audio
# chunk before treating it as a transient failure and switching to Kokoro for
# this utterance. A live call can't tolerate seconds of dead air, so keep short.
CARTESIA_FIRST_CHUNK_TIMEOUT = 3.0     # seconds

TWILLIO_RATE = 8000
PCM_RATE = 16000
SILENCE_TIMEOUT_MS = 700   # how long a pause must last before a turn is "done"

# Anything shorter than this is treated as a noise blip (cough, "uh", line
# crackle), not a real turn — too short to transcribe well and only makes the
# bot react to nothing. Dropped before speech-to-text.
MIN_UTTERANCE_MS = 400

# Hard cap on call length. Enforced CARRIER-SIDE by Twilio via the call's
# `time_limit` param, not by a backend timer — Twilio then fires `stop` +
# `completed`, giving us ONE teardown path for both hang-up and timeout.
CALL_TIME_LIMIT = 60   # seconds


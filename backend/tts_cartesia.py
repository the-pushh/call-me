"""Cartesia text-to-speech — the PRIMARY backend.

Cartesia's `pcm_mulaw` @ 8 kHz output IS Twilio's wire format, so this path
needs NO resample and NO codec step — the bytes Cartesia streams go straight on
the outbound queue. That's why it's primary; Kokoro (`tts_kokoro`) does a
24k->8k->mu-law conversion and is the always-on fallback for when Cartesia is
unreachable.

Shared contract with `tts_kokoro`: `synthesize(text, stop_event)` yields
ready-to-send mu-law @ 8 kHz bytes. mu-law is 1 byte per sample, so there is no
half-sample to carry across chunk boundaries (the int16 path has that problem;
this one doesn't).

Set CARTESIA_API_KEY in .env. If it's missing or the service errors, the request
fails and `tts.py` falls back to Kokoro — the app never goes silent.
"""

from cartesia import Cartesia

import config
import emotion_map

NAME = "cartesia"

# Model id is config-driven so it can be bumped without editing this file.
MODEL_ID = config.CARTESIA_MODEL_ID
SAMPLE_RATE = 8000     # mu-law 8 kHz == Twilio native; no resample needed

# Fast-detection budget for connect / first chunk — see config. The dispatcher
# treats a timeout as a transient failure and switches to Kokoro for this turn.
FIRST_CHUNK_TIMEOUT = config.CARTESIA_FIRST_CHUNK_TIMEOUT

# Per-persona voice. Each persona gets a distinct Cartesia voice id (from the
# Cartesia voice library). Add a row here when a new persona is added. These ids
# are Cartesia-specific — the Kokoro fallback keeps its OWN map (different
# namespace), so a persona can sound similar on both engines.
VOICES = {
    "eve": "62ae83ad-4f6a-430b-af41-a9bede9286ca",
}
# Used when a persona has no voice mapped yet, so a new persona never crashes
# the call path before its voice is chosen.
DEFAULT_VOICE = VOICES["eve"]


def _voice_for(persona: str) -> str:
    return VOICES.get(persona, DEFAULT_VOICE)

# Constructing with a None key does not raise — the error (if any) surfaces at
# request time, where tts.py catches it and falls back. So import never crashes
# the app even when the key is unset.
_client = Cartesia(api_key=config.CARTESIA_API_KEY)

_OUTPUT_FORMAT = {
    "container": "raw",
    "encoding": "pcm_mulaw",
    "sample_rate": SAMPLE_RATE,
}


def synthesize(text: str, stop_event=None, persona: str = "eve"):
    """Generator: synthesise `text` in `persona`'s voice, yield phone-ready
    mu-law @ 8 kHz bytes.

    Uses the REST byte stream (`tts.bytes`), which returns an iterator of audio
    chunks as they're generated — first sound comes back well before the whole
    sentence is synthesised, same streaming shape as the Kokoro path.

    Expressiveness: a LEADING emotion tag becomes a generation_config.emotion
    PARAMETER (it shapes the delivery, it is NOT spoken) and is removed from the
    text. An inline [laughter] is LEFT in the text — Cartesia performs it. Speed
    is set per call from config so the whole call keeps one pace.
    """
    if not text or not text.strip():
        return

    emotion, spoken = emotion_map.parse_leading_emotion(text)
    if not spoken.strip():
        return   # the line was only a tag — nothing to say
    generation_config = {
        "speed": config.CARTESIA_SPEED,
        "emotion": emotion or config.CARTESIA_BASELINE_EMOTION,
    }

    # timeout covers connect AND the gap between chunks, so a dead/slow Cartesia
    # is detected fast (httpx raises -> dispatcher falls back) instead of leaving
    # the caller in dead air. Raised exceptions propagate to tts.py by design.
    stream = _client.tts.bytes(
        model_id=MODEL_ID,
        transcript=spoken,
        voice={"mode": "id", "id": _voice_for(persona)},
        output_format=_OUTPUT_FORMAT,
        generation_config=generation_config,
        timeout=FIRST_CHUNK_TIMEOUT,
    )
    for chunk in stream:
        # barge-in: stop the instant the user starts talking
        if stop_event is not None and stop_event.is_set():
            break
        if chunk:
            yield chunk


def speak(text: str, stop_event=None, persona: str = "eve"):
    """Synthesise `text` and play it locally — offline test for THIS backend.

    synthesize() emits mu-law 8 kHz, so we decode it back to int16 for the
    speaker (telephone quality — exactly what the caller hears).
    """
    import numpy as np
    import sounddevice as sd

    from twilio_audio import mulaw_to_pcm16

    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as out:
        for mulaw in synthesize(text, stop_event=stop_event, persona=persona):
            samples = np.frombuffer(mulaw_to_pcm16(mulaw), dtype=np.int16)
            out.write(samples.reshape(-1, 1))


# ---------------------------------------------------------------------------
# STANDALONE TEST — `python tts_cartesia.py` speaks a line through Cartesia.
# Needs CARTESIA_API_KEY set. Verifies the primary path in isolation.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    speak("hi there, this is the cartesia voice... "
          "if you hear me, the primary path works.")

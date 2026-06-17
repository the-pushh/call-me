"""Speech-to-text.

Turn-based, so we use BATCH transcription: send the whole captured utterance
once, get the full text back. The utterance arrives from VADGate as float32
samples; the job here is the format pipeline at the boundary:

    float32 (VAD)  ->  int16  ->  WAV bytes  ->  base64  ->  JSON body  ->  text

OpenRouter's STT endpoint takes base64 audio inside an `input_audio` object and
returns JSON {text, usage}. We post it directly with httpx so the wire format
is explicit (the OpenAI SDK defaults to a multipart upload, a different shape).
"""

import base64
import httpx
import numpy as np

from config import OPENROUTER_API_KEY
from audio_formatting import float_to_int16, pcm16_to_wav_bytes, SAMPLE_RATE

STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"
STT_MODEL = "openai/whisper-large-v3-turbo"   # confirm exact slug on the Models page

# A short hint to steady the transcriber. Whisper uses this as the "text that
# came just before" — it nudges spelling/style toward casual conversation and
# makes it less likely to invent formal phrasing from noisy 8kHz phone audio.
# It is NOT a command; it just biases the decoder.
STT_PROMPT = "A casual, friendly phone conversation."

# Whisper hallucinates these on near-silence — they are NOT things the user
# said. Same guard as in brains.clean_stt; we drop them at the source too.
SILENCE_ARTIFACTS = {
    "", "you", ".", "...", "thank you.", "thanks for watching.",
    "thank you for watching.",
}


def transcribe(audio_f32: np.ndarray, language: str = "en",
               prompt: str = STT_PROMPT) -> str | None:
    """Transcribe a float32 utterance. Returns text, or None if empty/junk."""
    if audio_f32 is None or len(audio_f32) == 0:
        return None

    # float32 -> int16 -> WAV-in-memory -> base64 (raw bytes, NOT a data URI)
    wav_bytes = pcm16_to_wav_bytes(float_to_int16(audio_f32), sample_rate=SAMPLE_RATE)
    b64 = base64.b64encode(wav_bytes).decode("ascii")

    resp = httpx.post(
        STT_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model": STT_MODEL,
            "input_audio": {"data": b64, "format": "wav"},
            "language": language,        # skip auto-detect -> a bit faster/steadier
            "temperature": 0,            # deterministic; no creative transcription
            "prompt": prompt,            # bias toward casual speech (see STT_PROMPT)
        },
        timeout=30,   # upstream caps audio at 60s anyway; our turns are short
    )
    resp.raise_for_status()

    text = (resp.json().get("text") or "").strip()
    if text.lower() in SILENCE_ARTIFACTS:
        return None
    return text


# ---------------------------------------------------------------------------
# STANDALONE TEST — `python stt.py` records ~4s from the mic and prints the
# transcript. Verifies the format pipeline end to end, in isolation.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sounddevice as sd

    seconds = 4
    print(f"recording {seconds}s — say something...")
    # sd.rec returns float32 shape (N, channels); we want mono 1-D
    recording = sd.rec(int(seconds * SAMPLE_RATE),
                       samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()   # block until the recording finishes
    audio = recording[:, 0]

    print("transcribing...")
    print("  ->", transcribe(audio))
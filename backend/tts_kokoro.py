"""Kokoro text-to-speech — the FALLBACK backend (always works).

Kokoro (via OpenRouter's OpenAI-compatible speech endpoint) returns int16 PCM at
the MODEL's rate (24 kHz). The phone wants mu-law at 8 kHz, so this module does
the 24k->8k resample + mu-law encode INTERNALLY and yields mu-law bytes — the
same shape `tts_cartesia` yields natively. That shared contract is what lets
`tts.py` swap one backend for the other with no caller changes.

Why kokoro is the fallback, not the primary: Cartesia emits mu-law 8k directly
(no resample, no codec step), so it's the faster, cleaner phone path. Kokoro is
the safety net — it has always worked here, so when Cartesia is down we degrade
to this instead of going silent.

Boundary details that are pure correctness:
  * SAMPLE ALIGNMENT: network chunks don't land on 2-byte (int16) boundaries, so
    a sample can split across two chunks. We carry the leftover byte.
  * RESAMPLE STATE: one Resampler per synthesize() call keeps ratecv's filter
    state continuous across the chunks of THIS sentence (no clicks). State resets
    between sentences — acceptable on the fallback path.
  * BARGE-IN: this runs WHILE the VAD keeps listening, so the loop checks
    stop_event every chunk and cuts out instantly if the user speaks.
"""

import numpy as np
import sounddevice as sd
from openai import OpenAI

import config
import emotion_map
from config import OPENROUTER_API_KEY
from twilio_audio import Resampler, pcm16_to_mulaw, mulaw_to_pcm16

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

NAME = "kokoro"
TTS_MODEL = "hexgrad/kokoro-82m"
MODEL_RATE = 24000     # Kokoro & OpenAI-family PCM are 24 kHz. VERIFY per model.
SAMPLE_RATE = 8000     # what we EMIT: mu-law 8 kHz (Twilio's wire rate)
CHUNK_BYTES = 4096

# Per-persona voice. Kokoro voice NAMES (af_bella etc), a different namespace
# from Cartesia's ids — each backend maps the same persona to its own voice.
# Add a row when a new persona is added.
VOICES = {
    "eve": "af_bella",
}
DEFAULT_VOICE = VOICES["eve"]


def _voice_for(persona: str) -> str:
    return VOICES.get(persona, DEFAULT_VOICE)


def synthesize(text: str, stop_event=None, persona: str = "eve"):
    """Generator: synthesise `text` in `persona`'s voice, yield ready-to-send
    mu-law @ 8 kHz bytes.

    Shared contract with `tts_cartesia.synthesize`: the caller gets phone-ready
    mu-law and just queues it — no resample or codec step downstream. mu-law is
    1 byte per sample, so unlike the 24k int16 stream there's no half-sample to
    carry on the OUTPUT side; the leftover carry below is on the int16 INPUT.

    Expressiveness: Kokoro can't render emotion tags, so we STRIP every [tag]
    (emotion and [laughter] alike) and speak the plain words — graceful degrade,
    never an error. speed comes from config so fallback keeps the same pace.
    """
    spoken = emotion_map.strip_all_tags(text)
    if not spoken.strip():
        return

    rs = Resampler(MODEL_RATE, SAMPLE_RATE)   # per-call; state continuous here
    leftover = b""   # bytes carried over when a network chunk ends mid-sample

    # with_streaming_response gives us the raw byte stream as it arrives, rather
    # than buffering the whole audio file first.
    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=_voice_for(persona),
        input=spoken,
        speed=config.KOKORO_SPEED,
        response_format="pcm",       # raw int16 samples @ 24 kHz
    ) as response:
        for chunk in response.iter_bytes(chunk_size=CHUNK_BYTES):
            # barge-in: stop the instant the user starts talking
            if stop_event is not None and stop_event.is_set():
                break
            if not chunk:
                continue

            data = leftover + chunk
            # int16 chunks don't land on 2-byte boundaries, so a sample can
            # straddle two chunks. Resample only whole samples and carry the
            # trailing odd byte forward — dropping it desyncs every following
            # sample by one byte and turns the rest into noise.
            usable = len(data) - (len(data) % 2)
            leftover = data[usable:]
            if usable == 0:
                continue

            # 24k int16 -> 8k int16 (stateful) -> mu-law. Phone-ready.
            yield pcm16_to_mulaw(rs.process(data[:usable]))


def speak(text: str, stop_event=None, persona: str = "eve"):
    """Synthesise `text` and play it through the default output device.

    Offline-test wrapper. Since synthesize() now emits mu-law 8 kHz, we decode
    it back to int16 for the speaker — telephone quality, which is exactly what
    the caller hears, so it doubles as a fidelity check of the phone path.
    """
    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=1,
                         dtype="int16") as out:
        for mulaw in synthesize(text, stop_event=stop_event, persona=persona):
            samples = np.frombuffer(mulaw_to_pcm16(mulaw), dtype=np.int16)
            out.write(samples.reshape(-1, 1))   # OutputStream wants (frames, channels)


# ---------------------------------------------------------------------------
# STANDALONE TEST — `python tts_kokoro.py` speaks a line through this backend.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    speak("hey, this is the kokoro fallback voice... "
          "if you hear me, the fallback path works.")

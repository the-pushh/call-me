"""Text-to-speech.

Takes one sentence (from brain.respond's stream) and speaks it. Streams PCM so
audio starts a fraction of a second after the request instead of after the
whole sentence is synthesised — that, stacked on the brain's sentence chunking,
is what makes the agent start talking almost immediately.

Boundary details that are pure correctness:
  * SAMPLE RATE: TTS returns audio at the MODEL's rate (Kokoro / OpenAI voices
    are 24 kHz), not the 16 kHz we capture at. Play at the wrong rate and the
    voice is chipmunked or sludgy. Verify per model.
  * SAMPLE ALIGNMENT: network chunks don't land on 2-byte (int16) boundaries,
    so a sample can be split across two chunks. We carry the leftover byte.
  * BARGE-IN: this plays WHILE the VAD keeps listening, so the playback loop
    checks stop_event every chunk and cuts out instantly if the user speaks.
"""

import numpy as np
import sounddevice as sd
from openai import OpenAI

from config import OPENROUTER_API_KEY

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

TTS_MODEL = "hexgrad/kokoro-82m"
TTS_VOICE = "af_bella"
TTS_SAMPLE_RATE = 24000    # Kokoro & OpenAI-family PCM are 24 kHz. VERIFY per model.
CHUNK_BYTES = 4096


def synthesize(text: str, stop_event=None):
    """Generator: synthesise `text`, yield raw int16 PCM @ 24 kHz as bytes.

    This is the synth CORE, with no output device attached — the Twilio path
    has no local speaker, it pipes these bytes through resample -> mu-law ->
    the phone. `speak()` (below) is the local-playback wrapper for offline
    testing. Yielding bytes (not numpy) keeps the boundary simple: the Twilio
    resampler (audioop) wants bytes, and `speak()` re-wraps them for sounddevice.

    Each yielded chunk is a WHOLE number of int16 samples — the leftover-byte
    carry below guarantees we never split a sample across two yields.
    """
    if not text or not text.strip():
        return

    leftover = b""   # bytes carried over when a network chunk ends mid-sample

    # with_streaming_response gives us the raw byte stream as it arrives,
    # rather than buffering the whole audio file first.
    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        response_format="pcm",       # raw int16 samples
    ) as response:
        for chunk in response.iter_bytes(chunk_size=CHUNK_BYTES):
            # barge-in: stop the instant the user starts talking
            if stop_event is not None and stop_event.is_set():
                break
            if not chunk:
                continue

            data = leftover + chunk
            # network chunks don't land on 2-byte (int16) boundaries, so a
            # sample can straddle two chunks. Emit only whole samples and carry
            # the trailing odd byte forward — dropping it would desync every
            # following sample by one byte and turn the rest into noise.
            usable = len(data) - (len(data) % 2)
            leftover = data[usable:]
            if usable == 0:
                continue

            yield data[:usable]


def speak(text: str, stop_event=None):
    """Synthesise `text` and play it through the default output device.

    Thin wrapper around `synthesize()` for offline testing — opens a PortAudio
    output stream and writes each PCM chunk as it arrives. Honours stop_event.
    """
    # OutputStream is the speaker side of PortAudio. dtype int16 because that's
    # what PCM is; mono because the voice is mono.
    with sd.OutputStream(samplerate=TTS_SAMPLE_RATE, channels=1,
                         dtype="int16") as out:
        for pcm_bytes in synthesize(text, stop_event=stop_event):
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            out.write(samples.reshape(-1, 1))   # OutputStream wants (frames, channels)


# ---------------------------------------------------------------------------
# STANDALONE TEST — `python tts.py` speaks a line. If it sounds too fast/slow,
# it's a TTS_SAMPLE_RATE mismatch (the classic PCM bug), not a code bug.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    speak("hey, this is a streaming voice test... if i sound chipmunky, "
          "the sample rate is wrong — fix that first.")
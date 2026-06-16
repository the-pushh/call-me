"""Shared audio constants and format conversions.

The whole loop standardises on ONE capture format so the pieces fit together:
    16 kHz, mono, float32 in [-1.0, 1.0]
That's what the mic produces, what Silero VAD wants, and (after converting to
int16 + a WAV header) what the STT endpoint accepts. TTS output is separate —
it comes back at the model's own rate (see tts.py).
"""

import io
import wave
import numpy as np

# --- capture-side constants (mic -> VAD -> STT) ---------------------------
SAMPLE_RATE = 16000        # Hz. Speech standard; what Whisper + Silero expect.
CHANNELS = 1               # mono — one stream of numbers, not two
SAMPLE_WIDTH = 2           # bytes per int16 sample (16 bits / 8)

# Silero VAD v5 requires EXACTLY this many samples per inference call at 16kHz.
# Feed it a different size and it errors. 512 samples / 16000 Hz = 32 ms/frame.
VAD_FRAME_SAMPLES = 512
FRAME_MS = 1000 * VAD_FRAME_SAMPLES / SAMPLE_RATE   # = 32.0 ms


def float_to_int16(audio_f32: np.ndarray) -> np.ndarray:
    """float32 in [-1, 1]  ->  int16 in [-32768, 32767].

    The mic and VAD work in float32; WAV files and PCM streams use int16.
    np.clip guards against values slightly outside [-1, 1] (which would wrap
    around to huge negative numbers and produce loud clicks if not clamped).
    """
    clipped = np.clip(audio_f32, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def int16_to_float(audio_i16: np.ndarray) -> np.ndarray:
    """int16  ->  float32 in [-1, 1]. The inverse of the above."""
    return audio_i16.astype(np.float32) / 32767.0


def pcm16_to_wav_bytes(audio_i16: np.ndarray,
                       sample_rate: int = SAMPLE_RATE,
                       channels: int = CHANNELS) -> bytes:
    """Wrap raw int16 PCM samples in a WAV container, entirely in memory.

    PCM is just the bare numbers; a WAV file is those numbers preceded by a
    header describing rate/channels/width. STT wants a real file (it needs the
    header to know how to interpret the bytes), so we add one. We use an
    in-memory BytesIO buffer instead of writing to disk — no temp file needed.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_i16.tobytes())   # the raw PCM payload
    return buf.getvalue()
"""Pre-made audio, so the slow part (text->speech) happens BEFORE it's needed.

The text->speech service takes ~700ms just to start making sound. Two places
that hurts, and the same trick fixes both: make the audio ahead of time and keep
the ready-to-send phone bytes (mu-law) in memory.

  - FILLERS: short "umm.."/"yeah so.." clips, made once at server startup. When
    eve starts thinking we drop one in instantly, so the caller hears her voice
    while the real answer is still being synthesised — no dead silence.
  - GREETING: made during the RING (as soon as the call is requested), keyed by
    call id. By the time the callee picks up, the opener is already audio and
    plays with no wait.

Everything here is stored as a LIST of mu-law chunks — exactly what the sender
puts on the wire — so playing it is just "put each chunk on the outbound queue".
"""

import random
import threading

import tts
from twilio_audio import Resampler, pcm16_to_mulaw
from greetings import pick_greeting


def _synth_to_mulaw_chunks(text: str) -> list[bytes]:
    """Synthesise `text` and return it as ready-to-send mu-law chunks.

    Same outbound path the live loop uses (24k PCM -> resample 8k -> mu-law),
    just done ahead of time. One Resampler for the whole clip keeps its filter
    state continuous (no clicks)."""
    rs = Resampler(24000, 8000)
    return [pcm16_to_mulaw(rs.process(pcm24)) for pcm24 in tts.synthesize(text)]


# --- fillers (built once at startup) ---------------------------------------

# A mix of pure sounds and tiny phrases — variety so it doesn't feel canned.
FILLER_TEXTS = ["umm...", "hmm...", "uh...", "yeah so...", "okay so...", "right..."]

_filler_cache: list[list[bytes]] = []


def build_fillers():
    """Synthesise every filler once. Call at server startup (it's slow — it hits
    the TTS service once per filler — but it only runs at boot)."""
    global _filler_cache
    _filler_cache = [_synth_to_mulaw_chunks(t) for t in FILLER_TEXTS]
    print(f"[audio_cache] built {len(_filler_cache)} fillers")


def get_filler() -> list[bytes] | None:
    """A random pre-made filler's mu-law chunks, or None if not built yet."""
    if not _filler_cache:
        return None
    return random.choice(_filler_cache)


# --- greeting pre-warm (built during the ring, keyed by call id) ------------

_greeting_cache: dict[str, tuple[str, list[bytes]]] = {}
_lock = threading.Lock()


def prewarm_greeting(call_sid: str, persona: str):
    """Pick + synthesise the opener for this call and stash it. Run this in the
    background right after placing the call, so it finishes during the ring."""
    text = pick_greeting(persona)
    chunks = _synth_to_mulaw_chunks(text)
    with _lock:
        _greeting_cache[call_sid] = (text, chunks)
    print(f"[audio_cache] pre-warmed greeting for {call_sid}: {text!r}")


def take_greeting(call_sid: str) -> tuple[str, list[bytes]] | None:
    """Hand back (and remove) the pre-warmed opener, or None if it wasn't ready
    in time — in which case the caller falls back to synthesising it live."""
    with _lock:
        return _greeting_cache.pop(call_sid, None)

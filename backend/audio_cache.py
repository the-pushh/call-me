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
from greetings import GREETINGS, pick_greeting


def _synth_to_mulaw_chunks(text: str, persona: str) -> list[bytes]:
    """Synthesise `text` in `persona`'s voice, return ready-to-send mu-law chunks.

    tts.synthesize already yields phone-ready mu-law @ 8 kHz (the backend does
    any resample/codec), so this is just the live outbound path collected ahead
    of time into a list."""
    return list(tts.synthesize(text, persona=persona))


# --- fillers (built once at startup, PER PERSONA) --------------------------

# A mix of pure sounds and tiny phrases — variety so it doesn't feel canned.
FILLER_TEXTS = ["umm...", "hmm...", "uh...", "yeah so...", "okay so...", "right..."]

# persona -> list of filler clips (each clip a list of mu-law chunks). Keyed by
# persona because a filler must be in the SAME voice as the answer that follows
# it — otherwise the caller hears "umm" in one voice and the reply in another.
_filler_cache: dict[str, list[list[bytes]]] = {}


def build_fillers(personas=None):
    """Synthesise every filler for every persona once, at server startup. Slow
    (one TTS call per filler per persona) but boot-only. Defaults to all personas
    that have greetings defined."""
    global _filler_cache
    personas = personas or list(GREETINGS.keys())
    _filler_cache = {
        p: [_synth_to_mulaw_chunks(t, p) for t in FILLER_TEXTS]
        for p in personas
    }
    total = sum(len(v) for v in _filler_cache.values())
    print(f"[audio_cache] built {total} fillers across {len(_filler_cache)} personas")


def get_filler(persona: str) -> list[bytes] | None:
    """A random pre-made filler in `persona`'s voice, or None if not built yet."""
    clips = _filler_cache.get(persona)
    if not clips:
        return None
    return random.choice(clips)


# --- greeting pre-warm (built during the ring, keyed by call id) ------------

_greeting_cache: dict[str, tuple[str, list[bytes]]] = {}
_lock = threading.Lock()


def prewarm_greeting(call_sid: str, persona: str):
    """Pick + synthesise the opener for this call and stash it. Run this in the
    background right after placing the call, so it finishes during the ring."""
    text = pick_greeting(persona)
    chunks = _synth_to_mulaw_chunks(text, persona)
    with _lock:
        _greeting_cache[call_sid] = (text, chunks)
    print(f"[audio_cache] pre-warmed greeting for {call_sid}: {text!r}")


def take_greeting(call_sid: str) -> tuple[str, list[bytes]] | None:
    """Hand back (and remove) the pre-warmed opener, or None if it wasn't ready
    in time — in which case the caller falls back to synthesising it live."""
    with _lock:
        return _greeting_cache.pop(call_sid, None)

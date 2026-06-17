"""TTS dispatcher — picks the backend and applies the fallback policy.

Callers do `import tts; tts.synthesize(text, stop_event, persona)` and never care
which engine ran. Both backends honour ONE contract — yield ready-to-send mu-law
@ 8 kHz bytes — so they're interchangeable. Which is primary/fallback is
config-driven (config.TTS_PRIMARY / TTS_FALLBACK), so flipping to all-Kokoro is a
config change, not a code change.

    primary  = cartesia  (native mu-law 8k, no resample — fast, clean)
    fallback = kokoro    (24k -> 8k -> mu-law; "always works" safety net)

Two-tier fallback (the reason this file exists):

  * QUOTA / AUTH errors (bad key, credits exhausted) won't fix themselves
    mid-session. On the first one we set a STICKY flag and route THIS and every
    later utterance straight to Kokoro. Without the flag, every turn would
    re-attempt a dead Cartesia, fail, then fall back — paying that wasted
    latency on every single turn. The flag clears only on process restart.

  * TRANSIENT errors (timeout, dropped socket, one-off 5xx, rate-limit) might be
    gone next turn. Fall back for THIS utterance only; keep Cartesia primary.

  * MID-STREAM failure: if the primary already streamed some audio, we can't
    un-speak it, so we don't restart the sentence on a different voice — log and
    stop. (A sticky-class error mid-stream still trips the sticky flag so the
    NEXT turn skips Cartesia.)
"""

from cartesia import AuthenticationError, PermissionDeniedError

import config
import tts_cartesia
import tts_kokoro

_BACKENDS = {"cartesia": tts_cartesia, "kokoro": tts_kokoro}
PRIMARY = _BACKENDS[config.TTS_PRIMARY]
FALLBACK = _BACKENDS[config.TTS_FALLBACK]

# Set when the primary hits a non-recoverable (quota/auth) error. Process-wide,
# in-memory: stays set for the life of the server, cleared only by restart.
_primary_disabled = False


def _is_sticky(exc: Exception) -> bool:
    """True for errors that won't recover mid-session (bad key, no credits).

    Auth (401) and permission/credits (402/403) are sticky. Rate-limit (429),
    timeouts, connection drops and 5xx are TRANSIENT — they may clear next turn,
    so they are NOT sticky."""
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return True
    # Belt-and-suspenders: any 401/402/403 even if surfaced as a generic error.
    return getattr(exc, "status_code", None) in (401, 402, 403)


def synthesize(text: str, stop_event=None, persona: str = "eve"):
    """Yield phone-ready mu-law @ 8 kHz bytes in `persona`'s voice, applying the
    primary→fallback policy above."""
    global _primary_disabled

    # Straight to fallback when primary is known-dead (sticky) or when config
    # makes primary and fallback the same backend (e.g. TTS_PRIMARY="kokoro").
    if _primary_disabled or PRIMARY is FALLBACK:
        yield from FALLBACK.synthesize(text, stop_event=stop_event, persona=persona)
        return

    produced = False
    try:
        for chunk in PRIMARY.synthesize(text, stop_event=stop_event, persona=persona):
            produced = True
            yield chunk
        return
    except Exception as e:
        sticky = _is_sticky(e)
        if sticky:
            _primary_disabled = True   # every future turn skips the dead primary
        tag = "STICKY quota/auth" if sticky else "transient"
        if produced:
            # Already streamed audio — can't cleanly restart on another voice.
            print(f"[tts] {PRIMARY.NAME} failed mid-stream [{tag}]: {e}")
            return
        print(f"[tts] {PRIMARY.NAME} failed before first chunk [{tag}] "
              f"-> falling back to {FALLBACK.NAME}: {e}")

    # Reached only when the primary errored with no audio emitted yet.
    yield from FALLBACK.synthesize(text, stop_event=stop_event, persona=persona)


def speak(text: str, stop_event=None, persona: str = "eve"):
    """Local-playback test via the same primary/fallback selection."""
    try:
        PRIMARY.speak(text, stop_event=stop_event, persona=persona)
    except Exception as e:
        print(f"[tts] {PRIMARY.NAME} speak failed; using {FALLBACK.NAME}: {e}")
        FALLBACK.speak(text, stop_event=stop_event, persona=persona)


if __name__ == "__main__":
    speak("this is the active text to speech backend, "
          "whichever one answered first.")

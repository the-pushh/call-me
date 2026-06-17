"""Emotion tags + emoji — the single source of truth for the expressiveness layer.

The brain emits ONE canonical, richest-form sentence (with `[tag]` markers); each
consumer translates it into its own dialect:

  * Cartesia adapter : leading emotion tag -> generation_config.emotion (a PARAM,
    not spoken); strips it from the text. [laughter] is left IN the text because
    Cartesia *performs* it inline.
  * Kokoro adapter   : strips ALL tags (emotion + nonverbalism). Words kept,
    expressiveness lost — graceful degrade, the call never breaks.
  * Frontend/emit    : replaces known tags with emoji, strips unknown. Use
    to_display() so a raw `[tag]` never reaches the screen.

Two tag kinds behave differently:
  - LEADING emotion tag (`[excited] ...`)  : describes the whole line -> a per-
    call emotion parameter. Consumed (removed) from the spoken text.
  - INLINE nonverbalism (`... [laughter]`) : happens at a point -> Cartesia
    performs it; stays in the text for Cartesia, stripped for Kokoro.

Tokens are the brain's vocabulary (the `[token]` it writes). The `cartesia` value
is the corresponding name from Cartesia's emotion enum (verified against the SDK)
— note `amused` maps to `happy` because the enum has no "joking/comedic".
"""

import re

EMOTION_MAP = {
    "excited":     {"cartesia": "excited",     "emoji": "🤩"},   # primary (strong)
    "content":     {"cartesia": "content",     "emoji": "🙂"},   # primary (baseline)
    "sad":         {"cartesia": "sad",         "emoji": "😔"},   # primary
    "curious":     {"cartesia": "curious",     "emoji": "🤔"},   # extended
    "nostalgic":   {"cartesia": "nostalgic",   "emoji": "🥹"},   # extended
    "amused":      {"cartesia": "happy",       "emoji": "😄"},   # extended (no "joking" enum)
    "sympathetic": {"cartesia": "sympathetic", "emoji": "🤗"},   # extended
}

# Inline — Cartesia performs it, no generation_config involved. Kept in the text
# on the Cartesia path, stripped on Kokoro and replaced by emoji on screen.
NONVERBALISMS = {
    "laughter": {"emoji": "😂"},
}

# Any [token] of letters/underscore. Used to strip/replace anywhere in a line.
_TAG = re.compile(r"\[([a-zA-Z_]+)\]")
# A LEADING tag only (start of line, optional surrounding space).
_LEADING = re.compile(r"^\s*\[([a-zA-Z_]+)\]\s*")


def _tidy(text: str) -> str:
    """Collapse the double spaces / leading space a removed tag leaves behind."""
    return re.sub(r"\s{2,}", " ", text).strip()


def parse_leading_emotion(text: str):
    """Split a LEADING emotion tag off `text`.

    Returns (cartesia_emotion | None, spoken_text). Only a leading EMOTION tag is
    consumed:
      - known emotion  -> (its cartesia value, text without the tag)
      - leading [laughter] / other nonverbalism -> (None, text UNCHANGED) so the
        adapter can still perform it inline
      - unknown leading tag -> (None, text with the tag stripped) — fail safe,
        caller uses the baseline emotion
    """
    m = _LEADING.match(text)
    if not m:
        return None, text
    token = m.group(1).lower()
    if token in EMOTION_MAP:
        return EMOTION_MAP[token]["cartesia"], _tidy(text[m.end():])
    if token in NONVERBALISMS:
        return None, text          # leave the nonverbalism in place
    return None, _tidy(text[m.end():])   # unknown -> strip, baseline emotion


def strip_all_tags(text: str) -> str:
    """Remove EVERY [tag] — emotion and nonverbalism alike. For the Kokoro path,
    which can't render expressiveness, so it just speaks the plain words."""
    return _tidy(_TAG.sub("", text))


def to_display(text: str) -> str:
    """Replace known tags with their emoji and drop everything else bracketed —
    for the frontend / any on-screen consumer, so a raw `[tag]` is never shown.

    Matches ANY `[...]` (not just single-word tokens) so a multi-word or off-map
    tag the model improvises — `[so nostalgic]`, `[soft laugh]` — gets emoji'd if
    its first word is known, else dropped. A bare bracket must never hit screen.
    """
    def repl(m: re.Match) -> str:
        for word in m.group(1).strip().lower().split():
            if word in EMOTION_MAP:
                return EMOTION_MAP[word]["emoji"]
            if word in NONVERBALISMS:
                return NONVERBALISMS[word]["emoji"]
        return ""
    return _tidy(re.sub(r"\[([^\]]*)\]", repl, text))

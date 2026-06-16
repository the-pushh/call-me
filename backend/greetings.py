"""Per-persona opening lines.

The bot speaks first (see the greeting-then-echo worker in media_socket.py).
The greeting is SYNTHESISED through the persona's own TTS voice, never Twilio
`<Say>` — so the voice is consistent from the very first word.

A *set* per persona, picked at random each call, so repeat callers don't hear
the same opener every time. Lines are written in the persona's voice (eve:
lowercase, casual, music-obsessed — see personas/eve.md) so the greeting feels
like the same character who's about to carry the conversation.
"""

import random

GREETINGS = {
    "eve": [
        "hey hey... oh nice, you actually called. ok what's up",
        "yooo there you are. i was just sitting here with a song stuck in my head, talk to me",
        "hey you... perfect timing honestly. what's going on",
        "oh hi!! ok i'm here, i'm listening — what's on your mind",
    ],
}

# Spoken if a persona has no greeting set yet — generic but still warm, so a
# new persona never crashes the call path before its lines are written.
_FALLBACK = "hey there... i'm here. what's up"


def pick_greeting(persona: str) -> str:
    """One random opening line for `persona`, or the fallback if none exist."""
    lines = GREETINGS.get(persona)
    if not lines:
        return _FALLBACK
    return random.choice(lines)

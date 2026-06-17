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
        "hey hey. i just thought i'd dial you up... what's going on in your world?",
        "yooo. i was just sitting here with a song stuck in my head... figured i'd call. talk to me.",
        "hey you. i was just spacing out... and decided to call. what's going on?",
        "oh hi! i'm just walking around right now... figured i'd see what's on your mind.",
    ],
    "siddhartha": [
        "[peaceful] hello. i was just watching the sky... and thought i would reach out.",
        "ah, you answered. i have nowhere to be... so i thought i would see how you are.",
        "[warm] hello my friend. the world is very quiet right now... so i thought i would call.",
        "i was just making some tea... and felt like hearing your voice. how is your day unfolding?",
    ],
    "jeremiah": [
        "[smooth] hey. i had a spare minute between calls... so i thought i'd dial you.",
        "good to hear your voice. i just wrapped a meeting... so i figured i would reach out.",
        "[confident] glad i caught you. the markets just closed... so i have some time to chat.",
        "there you are. i was just looking at some projections... decided to take a break and call. how's it going?",
    ],
    "billie": [
        "[excited] oh hi! i was just looking at the most fascinating data set... and i had to call you.",
        "hello! statistically... this was the perfect time of day to catch you.",
        "[matter-of-fact] okay perfect. my simulation just finished running... so i had an opening to call.",
        "wait hi! i was literally just thinking about you... so i dialed. what's going on?",
    ],
    "avni": [
        "[focused] hey! i have a little bandwidth right now... so i figured i'd call. what's the update?",
        "yo! glad you picked up. i was just looking for a reason to step away from my screen... what's up?",
        "[shrewd] hey there. just shipped the latest build... thought i'd check in. what's on your radar today?",
        "hey! i was just about to ping you... but a call is faster. tell me what you're thinking."
    ]
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

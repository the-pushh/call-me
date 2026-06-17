"""Live call registry: call_sid -> CallSession.

Lets the hangup endpoint stop a session DIRECTLY (instant local teardown)
instead of waiting for Twilio's `completed` webhook to round-trip back over the
network. The Twilio status path still fires afterwards and is harmless —
CallSession.stop() is idempotent.

Tiny on purpose, and dependency-free, so both telephony (writes /hangup) and
media_socket (registers/unregisters around a call) can import it without a
circular import.
"""

_sessions: dict = {}


def register(call_sid, session):
    if call_sid:
        _sessions[call_sid] = session


def unregister(call_sid):
    _sessions.pop(call_sid, None)


def get(call_sid):
    return _sessions.get(call_sid)

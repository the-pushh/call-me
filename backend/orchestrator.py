"""Per-call orchestration — the CallSession state machine.

This is the brain-stem of a call: one CallSession per phone call, owning the
whole turn-taking loop. It replaces the Step 1 echo worker. The realtime
speech-to-speech model you used before handled all of this internally
(endpointing, turn-taking, interruption); here we own it explicitly, which is
the whole point of the build — you can see every piece.

The loop runs on ONE worker thread, draining inbound audio and walking a small
state machine:

    greeting ─► LISTENING ──utterance──► THINKING ──text──► SPEAKING ─► LISTENING

  LISTENING : feed every 512-sample frame to the VAD until it hands back a
              completed utterance (the caller paused).
  THINKING  : transcribe that utterance; if there are real words, ask the Brain.
  SPEAKING  : stream the Brain's sentences through TTS to the phone.

Step 2 has NO barge-in (that's Step 5): while SPEAKING we ignore the mic, then
discard whatever piled up before listening again. The per-turn `turn_stop`
Event is wired through now so Step 5 can flip it mid-turn without re-plumbing.
"""

import queue
import threading
import time

from config import SILENCE_TIMEOUT_MS, MIN_UTTERANCE_MS
import numpy as np

from audio_formatting import int16_to_float, float_to_int16, SAMPLE_RATE
from twilio_audio import mulaw_to_pcm16, Resampler, FrameAccumulator
from brains import Brain
from stt import transcribe
import tts
from greetings import pick_greeting
import audio_cache

# Pushed onto a queue to mean "shut down". Shared with media_socket's sender so
# both the inbound (worker) and outbound (sender) sides unwind on teardown.
STOP = object()


def _default_emit(event, **data):
    """Stand-in for the Step 3 watch-socket emitter — just logs the events the
    frontend will eventually render, so we can watch the state machine now."""
    print(f"[emit] {event} {data}")


class CallSession:
    """Owns one call: queues, audio state, the Brain, and the loop thread."""

    def __init__(self, persona: str, call_sid: str | None = None, emit=None):
        self.persona = persona
        self.call_sid = call_sid     # used to pick up the pre-warmed greeting
        self.emit = emit or _default_emit

        # Audio transport queues (filled/drained by media_socket).
        self.inbound_q: queue.Queue = queue.Queue()
        self.outbound_q: queue.Queue = queue.Queue()

        # session-level teardown vs. per-turn interrupt (Step 5 sets turn_stop).
        self.stop_event = threading.Event()
        self.turn_stop = threading.Event()

        self.brain = Brain(persona)

        # Inbound resampler: ONE instance, reused for the whole call so ratecv's
        # filter state stays continuous (no clicks at chunk boundaries). The
        # outbound side needs no resampler now — tts.synthesize hands back
        # mu-law 8 kHz already (Cartesia native; Kokoro converts internally).
        self.in_rs = Resampler(8000, 16000)    # phone -> stack rate (for VAD/STT)

        self.acc = FrameAccumulator()

        # VAD is loaded lazily on the worker thread (see _run) — load_silero_vad
        # is heavy and must never run on the asyncio event loop.
        self.capture_vad = None

        self.state = "connected"
        self.stream_sid = None        # set by media_socket on the `start` event
        self._thread: threading.Thread | None = None

    # --- lifecycle (called from media_socket) ------------------------------

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed_inbound(self, raw: bytes):
        self.inbound_q.put(raw)

    def stop(self):
        """Tear the session down (hang-up, timeout, or disconnect)."""
        self.stop_event.set()
        self.turn_stop.set()
        self.inbound_q.put(STOP)     # unblock a LISTENING get()

    # --- the loop ----------------------------------------------------------

    def _run(self):
        # Load the VAD on a SIDE thread so it loads WHILE the greeting plays,
        # instead of making the caller wait for it before hearing anything.
        # load_silero_vad is heavy and must never touch the asyncio event loop.
        vad_ready = threading.Event()

        def _load_vad():
            from vad import VADGate
            self.capture_vad = VADGate(silence_ms=SILENCE_TIMEOUT_MS)
            vad_ready.set()

        threading.Thread(target=_load_vad, daemon=True).start()

        # Greeting: the bot speaks first, then REMEMBERS it said so, so its first
        # real reply follows on from the opener. Prefer the version pre-warmed
        # during the ring (instant); fall back to live synthesis if it wasn't
        # ready in time.
        self._set_state("speaking")
        prewarmed = audio_cache.take_greeting(self.call_sid) if self.call_sid else None
        if prewarmed is not None:
            text, chunks = prewarmed
            for chunk in chunks:
                if self.stop_event.is_set():
                    break
                self.outbound_q.put(chunk)
            self.brain.add_assistant_message(text)
        else:
            greeting = pick_greeting(self.persona)
            self._speak(greeting)
            self.brain.add_assistant_message(greeting)

        # Must have the VAD before we can listen.
        vad_ready.wait()

        while not self.stop_event.is_set():
            self._set_state("listening")
            utterance = self._capture()
            if utterance is None:
                break   # teardown

            # Ignore blips too short to be a real sentence — keeps eve from
            # reacting to coughs/line noise (and they transcribe to junk anyway).
            if len(utterance) < (MIN_UTTERANCE_MS / 1000) * SAMPLE_RATE:
                continue

            self._set_state("thinking")
            # t_turn marks the instant the caller's turn ended (VAD released the
            # utterance). Everything timed below is measured from here, because
            # this is when the wait the caller actually feels begins.
            t_turn = time.monotonic()
            text = transcribe(utterance)
            stt_ms = (time.monotonic() - t_turn) * 1000
            if not text:
                print(f"[timing] stt={stt_ms:.0f}ms (no speech)")
                continue   # silence/hallucination — keep listening
            self.emit("user_transcript", text=text)

            # Drop a pre-made filler in eve's voice NOW, while the real reply is
            # still being thought up and synthesised. The caller hears "umm..."
            # within ~0ms instead of dead silence; the answer follows seamlessly
            # because the queue plays filler-then-reply in order. Only after we
            # know there are real words, so silence never triggers a stray umm.
            self._queue_filler()

            self._set_state("speaking")
            self._respond(text, t_turn, stt_ms)

            # No barge-in in Step 2: drop the audio that arrived while we talked
            # so the next turn starts from a clean mic, not a stale backlog.
            self._drain_inbound()

    def _capture(self) -> np.ndarray | None:
        """Block until the VAD reports a completed utterance, or teardown."""
        while not self.stop_event.is_set():
            raw = self.inbound_q.get()
            if raw is STOP:
                return None

            pcm16 = self.in_rs.process(mulaw_to_pcm16(raw))
            f32 = int16_to_float(np.frombuffer(pcm16, dtype=np.int16))

            for frame in self.acc.feed(f32):
                result = self.capture_vad.process(frame)
                # ndarray = utterance done. "start" is barge-in (Step 5) — here
                # the caller is just beginning their turn, nothing to do yet.
                if isinstance(result, np.ndarray):
                    return result
        return None

    def _respond(self, text: str, t_turn: float, stt_ms: float):
        """Stream the Brain's reply sentence-by-sentence into the phone.

        Times the FIRST sentence only — that's the gap the caller feels (the
        silence between finishing their turn and hearing eve start). Later
        sentences stream while she's already talking, so they don't add to the
        perceived wait.
        """
        self.turn_stop.clear()
        t_brain_start = time.monotonic()
        q = self.brain.respond_async(text, stop_event=self.turn_stop)

        first = True
        brain_first_ms = None
        while True:
            sentence = q.get()
            if sentence is None:
                break
            if isinstance(sentence, tuple) and sentence and sentence[0] == "__error__":
                print(f"[brain error] {sentence[1]}")
                break

            if first:
                brain_first_ms = (time.monotonic() - t_brain_start) * 1000

            self.emit("assistant_sentence", text=sentence)

            if first:
                # Capture how long synthesis takes to produce its first audio,
                # and the full stop-talking -> first-sound-out total.
                timing = {}
                t_synth = time.monotonic()

                def _on_first_audio():
                    timing["tts_ms"] = (time.monotonic() - t_synth) * 1000
                    timing["total_ms"] = (time.monotonic() - t_turn) * 1000

                self._speak(sentence, on_first_audio=_on_first_audio)
                print(
                    f"[timing] stt={stt_ms:.0f}ms "
                    f"brain_first={brain_first_ms:.0f}ms "
                    f"tts_first={timing.get('tts_ms', 0):.0f}ms "
                    f"total={timing.get('total_ms', 0):.0f}ms"
                )
            else:
                self._speak(sentence)

            first = False
            if self.stop_event.is_set():
                break

    def _speak(self, text: str, on_first_audio=None):
        """Synthesise one piece of text and push it to the phone.

        tts.synthesize already yields phone-ready mu-law @ 8 kHz (the backend
        does any resample/codec), so we just queue each chunk as-is.

        If given, on_first_audio() is called the moment the first audio chunk is
        queued — used to time how fast sound starts coming out.
        """
        for mulaw in tts.synthesize(text, stop_event=self.turn_stop, persona=self.persona):
            if self.stop_event.is_set():
                break
            self.outbound_q.put(mulaw)
            if on_first_audio is not None:
                on_first_audio()
                on_first_audio = None

    def _queue_filler(self):
        """Queue one pre-made filler clip, if any are built yet."""
        chunks = audio_cache.get_filler(self.persona)
        if not chunks:
            return
        for chunk in chunks:
            self.outbound_q.put(chunk)

    def _drain_inbound(self):
        try:
            while True:
                self.inbound_q.get_nowait()
        except queue.Empty:
            pass
        # Partial frame left in the accumulator is stale now — clear it so it
        # can't prepend old samples onto the next turn's first frame.
        self.acc = FrameAccumulator()

    def _set_state(self, state: str):
        self.state = state
        self.emit("state", value=state)

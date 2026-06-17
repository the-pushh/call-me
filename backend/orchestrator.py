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

Barge-in (Step 5): while SPEAKING, a side thread (`_monitor_barge`) watches the
caller's mic; if they cut in, it flips the per-turn `turn_stop` Event, drops the
unsent audio, and tells Twilio to flush its buffer, then the loop jumps straight
back to LISTENING. If the bot finishes uninterrupted, we discard whatever piled
up on the mic before listening again.
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
import emotion_map
from greetings import pick_greeting
import audio_cache

# Pushed onto a queue to mean "shut down". Shared with media_socket's sender so
# both the inbound (worker) and outbound (sender) sides unwind on teardown.
STOP = object()

# Pushed onto outbound_q to mean "tell Twilio to flush its playback buffer NOW"
# (barge-in). The sender turns it into Twilio's {"event":"clear"} message. We
# clear the queue first, but Twilio has already buffered some audio downstream;
# only the `clear` message stops THAT from playing over the caller cutting in.
CLEAR = object()

# How far ahead of real-time playback the worker is allowed to feed audio. A
# small lead absorbs synthesis/network jitter so the bot doesn't stutter; small
# enough that Twilio's playback buffer stays shallow, so a barge-in `clear` cuts
# the bot off fast. mu-law @ 8 kHz = 1 byte per sample, so a chunk's duration in
# seconds is just len(chunk) / 8000.
PREBUFFER_S = 0.3
PLAY_RATE = 8000


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

        # Barge-in (Step 5) reads the SAME inbound stream while the bot speaks,
        # but never at the same time as _capture (capture runs in LISTENING, the
        # monitor only in SPEAKING), so it gets its own resampler + accumulator
        # to keep each path's filter/frame state independent and click-free.
        self.barge_rs = Resampler(8000, 16000)
        self.barge_acc = FrameAccumulator()

        # VAD is loaded lazily on the worker thread (see _run) — load_silero_vad
        # is heavy and must never run on the asyncio event loop. Two gates:
        # capture_vad does endpointing (utterance end); barge_vad only watches
        # for the START of caller speech while the bot is talking.
        self.capture_vad = None
        self.barge_vad = None

        # Set by the barge monitor when the caller cuts in mid-reply, so the loop
        # knows to jump straight back to LISTENING without draining their speech.
        self._barge_fired = False

        # Outbound pacing clock. TTS synthesises far faster than real time; left
        # unpaced, the worker dumps the WHOLE reply onto outbound_q in ~1s and
        # Twilio buffers it all — so _respond (and the barge monitor that lives
        # only as long as it) finish long before the caller actually hears the
        # reply, and a barge-in mid-playback can't fire. We hold the feed to real
        # time (keeping just PREBUFFER_S ahead) so SPEAKING lasts as long as the
        # audio actually plays, and Twilio's buffer stays shallow enough that a
        # `clear` cuts the bot off near-instantly.
        self._play_deadline = 0.0

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
            # Barge gate: a touch stricter (higher threshold, needs a few speech
            # frames) so the bot's own audio echoing back through the caller's
            # line can't false-trigger an interrupt. silence_ms is irrelevant —
            # the monitor only ever reads its "start" signal.
            self.barge_vad = VADGate(threshold=0.6, speech_start_frames=3)
            vad_ready.set()

        threading.Thread(target=_load_vad, daemon=True).start()

        # The call is now live (Twilio bridged the audio). Tell the screen so it
        # leaves the "calling" ring and shows the in-call view.
        self._set_state("connected")

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
        else:
            text = pick_greeting(self.persona)
            self._speak(text)
        # The greeting is the bot's first line — show it in the transcript too
        # (emoji-ised, never a raw tag), and remember it so the first reply
        # follows on from the opener.
        self.emit("assistant_sentence", text=emotion_map.to_display(text))
        self.brain.add_assistant_message(text)

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
            # Barge-in: while the bot speaks, a side thread watches the caller's
            # mic. If they cut in, it fires the interrupt and sets _barge_fired.
            self._barge_fired = False
            barge_thread = threading.Thread(target=self._monitor_barge, daemon=True)
            barge_thread.start()
            self._respond(text, t_turn, stt_ms)
            # Reply finished (or was cut short) — release the monitor either way
            # and wait for it to unwind before touching shared audio state.
            self.turn_stop.set()
            barge_thread.join(timeout=1.0)

            if self._barge_fired:
                # Caller is mid-sentence — do NOT drain. Drop straight back to
                # LISTENING so _capture catches the rest of what they're saying.
                continue
            # Bot finished uninterrupted: drop the audio that piled up while it
            # talked so the next turn starts from a clean mic, not a stale backlog.
            self._drain_inbound()

        # Loop exited — teardown (hang-up, timeout, or disconnect). Tell the
        # screen so it resets home. Best-effort: if the browser already closed
        # its watch socket, push() just drops this.
        self._set_state("ended")

    def _capture(self) -> np.ndarray | None:
        """Block until the VAD reports a completed utterance, or teardown.

        While listening we also push the caller's live mic LEVEL to the screen so
        the waveform reacts to their actual voice (loud -> tall bars, silence ->
        flat). Throttled so it doesn't flood the socket.
        """
        lvl_skip = 0
        while not self.stop_event.is_set():
            raw = self.inbound_q.get()
            if raw is STOP:
                return None

            pcm16 = self.in_rs.process(mulaw_to_pcm16(raw))
            f32 = int16_to_float(np.frombuffer(pcm16, dtype=np.int16))

            for frame in self.acc.feed(f32):
                # RMS = loudness of this 512-sample frame. Gain + clamp maps
                # speech into a usable 0..1 for the bars. ~every 3rd frame (~100ms).
                lvl_skip += 1
                if lvl_skip % 3 == 0:
                    rms = float(np.sqrt(np.mean(frame * frame)))
                    self.emit("level", value=min(1.0, rms * 6.0))

                result = self.capture_vad.process(frame)
                # ndarray = utterance done. "start" here just means the caller
                # is beginning their turn normally (barge-in — cutting in while
                # the bot talks — is handled by _monitor_barge, not here).
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

            # Emoji-ise tags for the screen ([nostalgic] -> 🥹); a raw [tag] must
            # never reach the transcript. The SPOKEN copy (sentence) keeps its tag
            # so TTS can still act on it.
            self.emit("assistant_sentence", text=emotion_map.to_display(sentence))

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
            # stop_event = session teardown; turn_stop = barge-in cut this reply
            # short. Either way, stop pulling more sentences for this turn.
            if self.stop_event.is_set() or self.turn_stop.is_set():
                break

    def _monitor_barge(self):
        """Run on a side thread WHILE the bot speaks. Drains the caller's mic and
        watches barge_vad for the START of speech; the moment they cut in, fire
        the interrupt and stop. Exits on its own when turn_stop/stop_event is set
        (the reply finished without an interruption)."""
        self.barge_vad.reset()
        self.barge_acc = FrameAccumulator()
        while not self.turn_stop.is_set() and not self.stop_event.is_set():
            try:
                raw = self.inbound_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if raw is STOP:
                self.inbound_q.put(STOP)   # put back for capture/teardown
                return

            pcm16 = self.barge_rs.process(mulaw_to_pcm16(raw))
            f32 = int16_to_float(np.frombuffer(pcm16, dtype=np.int16))
            for frame in self.barge_acc.feed(f32):
                # In IDLE the gate only ever returns None or "start" (never an
                # utterance array), so the string compare is safe here.
                if self.barge_vad.process(frame) == "start":
                    self._barge_in()
                    return

    def _barge_in(self):
        """The caller cut in. Three steps, in order, to make the bot go quiet
        FAST: (1) stop generating/synthesising this turn, (2) drop the audio we
        haven't sent yet, (3) tell Twilio to flush what it has already buffered
        downstream — without (3) the caller would keep hearing the bot for a
        second over their own voice."""
        print("[barge] caller cut in — interrupting reply")
        self._barge_fired = True
        self.turn_stop.set()           # 1. halt Brain + TTS for this turn
        self._clear_outbound()         # 2. drop queued-but-unsent audio
        self.outbound_q.put(CLEAR)     # 3. flush Twilio's playback buffer
        # Mark the cut on the transcript so the bot's half-spoken reply reads as
        # interrupted, not just abandoned mid-sentence.
        self.emit("interrupted")

    def _clear_outbound(self):
        try:
            while True:
                self.outbound_q.get_nowait()
        except queue.Empty:
            pass

    def _speak(self, text: str, on_first_audio=None):
        """Synthesise one piece of text and push it to the phone.

        tts.synthesize already yields phone-ready mu-law @ 8 kHz (the backend
        does any resample/codec), so we just queue each chunk as-is.

        If given, on_first_audio() is called the moment the first audio chunk is
        queued — used to time how fast sound starts coming out.
        """
        for mulaw in tts.synthesize(text, stop_event=self.turn_stop, persona=self.persona):
            # turn_stop = barge-in; stop queueing immediately so we don't push
            # audio AFTER the CLEAR the monitor just sent (it would play over the
            # caller). stop_event = session teardown.
            if self.stop_event.is_set() or self.turn_stop.is_set():
                break
            self.outbound_q.put(mulaw)
            if on_first_audio is not None:
                on_first_audio()
                on_first_audio = None
            # Hold to real time so SPEAKING lasts as long as the audio plays —
            # this is what keeps the barge monitor alive across the whole reply.
            self._pace(len(mulaw) / PLAY_RATE)

    def _pace(self, duration: float):
        """Block until the audio already queued is within PREBUFFER_S of being
        fully played, advancing the play clock by `duration`. Sleeps in short
        slices so a barge-in (turn_stop) or teardown breaks out within ~20 ms."""
        now = time.monotonic()
        if self._play_deadline < now:
            # We fell behind (or this is the first chunk of a fresh utterance) —
            # restart the clock from now so we don't sleep off stale lead.
            self._play_deadline = now
        self._play_deadline += duration
        while not self.turn_stop.is_set() and not self.stop_event.is_set():
            ahead = self._play_deadline - time.monotonic()
            if ahead <= PREBUFFER_S:
                break
            time.sleep(min(0.02, ahead - PREBUFFER_S))

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

"""Voice Activity Detection + endpointing.

Silero answers a per-frame question ("is there speech in these 32 ms?").
This module builds the state machine that turns that into the two events the
loop actually needs:
    "start"      -> the user began talking   (used for barge-in)
    <utterance>  -> the user stopped talking  (the audio to send to STT)

The interesting part is the timing, not the model. Two knobs define the whole
feel of the agent:
    silence_ms  -> how long a pause must last before we call the turn "done".
                   Too low  = we cut people off mid-thought.
                   Too high = every reply feels laggy.
    threshold   -> how confident Silero must be to count a frame as speech.
"""

import numpy as np
import torch
from silero_vad import load_silero_vad

from audio_formatting import SAMPLE_RATE, VAD_FRAME_SAMPLES, FRAME_MS


class VADGate:
    """A small state machine sitting on top of the raw Silero model."""

    def __init__(self, threshold=0.5, silence_ms=850,
                 speech_start_frames=2, preroll_ms=200):
        self.model = load_silero_vad()
        self.threshold = threshold
        self.silence_frames_needed = int(silence_ms / FRAME_MS)
        self.speech_start_frames = speech_start_frames
        self.preroll_frames = int(preroll_ms / FRAME_MS)
        self.reset()

    def reset(self):
        """Clear all per-turn state. Called at construction and again every
        time an utterance finishes, so the gate is ready to detect the next
        one from a clean slate."""

        self.in_speech = False
        self.silence_count = 0
        self.speech_count = 0
        self.utterance = []
        self.preroll = []

    def process(self, frame_f32: np.ndarray):
        """Feed exactly one VAD_FRAME_SAMPLES-long float32 frame.

        This is the only method the caller drives — every frame of incoming
        audio, in order, goes through here exactly once. The method itself
        contains the whole turn-taking state machine as a simple two-branch
        if/else keyed on `self.in_speech`.

        Returns one of:
            None          -> nothing notable this frame
            "start"       -> speech just began
            np.ndarray    -> the turn just ended; this is the captured utterance
        """

        prob = self.model(torch.from_numpy(frame_f32), SAMPLE_RATE).item()
        is_speech = prob >= self.threshold

        if not self.in_speech:
            # --- IDLE: waiting for the user to start talking ---
            # just in case
            self.preroll.append(frame_f32)
            if len(self.preroll) > self.preroll_frames:
                self.preroll.pop(0)

            if is_speech:
                self.speech_count += 1
                if self.speech_count >= self.speech_start_frames:
                    self.in_speech = True        # flip the state machine
                    self.silence_count = 0       # start the silence-streak fresh
                    self.utterance = list(self.preroll)
                    self.preroll = []
                    return "start"
            else:
                self.speech_count = 0
            return None

        else:
            # --- IN SPEECH: actively recording the utterance, watching for the silence that ends it ---

            self.utterance.append(frame_f32)

            if is_speech:
                self.silence_count = 0
            else:
                self.silence_count += 1
                if self.silence_count >= self.silence_frames_needed:
                    # np.concatenate stitches the list of separate
                    # VAD_FRAME_SAMPLES-long frames into one single
                    # contiguous 1-D float32 array — this is the full
                    # utterance audio, ready to hand to STT.
                    audio = np.concatenate(self.utterance)
                    self.reset()
                    return audio
            return None


# ---------------------------------------------------------------------------
# STANDALONE TEST — run `python vad.py`, talk, pause, and watch it detect your
# turns. This is the foundation of the whole loop, so prove it feels right
# (tune silence_ms) BEFORE wiring STT/TTS on top.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import queue
    import sounddevice as sd

    gate = VADGate(silence_ms=850)   # try 500 vs 900 to feel the tradeoff

    # A thread-safe FIFO queue used purely to hand frames from PortAudio's
    # callback thread over to this main thread. Queue.put/get are the
    # synchronized, blocking-friendly primitives for exactly that handoff.
    frames = queue.Queue()

    # PortAudio calls this from its OWN thread every time `blocksize` samples
    # are ready. We copy the data out (PortAudio reuses the buffer) and hand it
    # to the main thread via a queue — the same producer/consumer pattern as
    # the brain's streaming. indata has shape (frames, channels); [:, 0] is the
    # mono channel.
    def callback(indata, n, time_info, status):
        # indata is reused by PortAudio after this callback returns, so we
        # MUST copy it (`.copy()`) — storing a reference to the original
        # would later read garbage/overwritten data once PortAudio recycles
        # the buffer for the next frame.
        frames.put(indata[:, 0].copy())

    print("listening — talk, then pause. ctrl-c to quit.\n")
    with sd.InputStream(samplerate=SAMPLE_RATE,
                        blocksize=VAD_FRAME_SAMPLES,   # exactly one VAD frame per callback
                        channels=1,
                        dtype="float32",
                        callback=callback):
        try:
            while True:
                # Blocks until the callback thread has put a frame in the
                # queue — this is what paces the loop to "once per 32ms
                # frame" instead of spinning.
                frame = frames.get()
                result = gate.process(frame)

                # IMPORTANT: check the np.ndarray case FIRST, not last.
                # `result` is one of: None, the string "start", or an
                # np.ndarray. If we tested `result == "start"` while result
                # is an ndarray, numpy does an ELEMENTWISE comparison against
                # the string instead of a single True/False — comparing each
                # number in the array to "start" — and hands back an array of
                # results, not one bool. Putting that array straight into an
                # `if` then raises:
                #   ValueError: The truth value of an array with more than
                #   one element is ambiguous. Use a.any() or a.all()
                # because Python's `if` needs exactly one True/False, not a
                # whole array of them. isinstance() is a type check, so it's
                # always a clean bool regardless of what `result` holds —
                # checking that first avoids ever running `== "start"`
                # against an array.
                if isinstance(result, np.ndarray):
                    secs = len(result) / SAMPLE_RATE
                    print(f"  << turn ended  ({secs:.1f}s captured)\n")
                elif result == "start":
                    print("  >> speech started")
                # else result is None: nothing notable this frame, loop again.
        except KeyboardInterrupt:
            print("\nstopped.")
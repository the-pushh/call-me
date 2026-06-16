"""Twilio audio transcode boundary.

Twilio speaks mu-law at 8 kHz over its media WebSocket. The rest of the stack
speaks float32 PCM at 16 kHz (the capture format everything in
audio_formatting.py assumes) on the way in, and int16 PCM at 24 kHz (TTS's
native rate) on the way out. Three different formats meet here, and nothing
past this module should ever see a mu-law byte or know Twilio exists.

    Inbound  (phone -> VAD):  mu-law 8k -> PCM16 8k -> resample 16k -> float32 -> 512-frame
    Outbound (TTS -> phone):  PCM16 24k -> resample 8k -> mu-law 8k

mu-law is a logarithmic 8-bit-per-sample encoding telephone networks have used
since the analog era: one byte per sample instead of two, because phone trunks
were bandwidth-starved for most of the last century. Modern code still has to
speak it only because that's the wire format Twilio's media stream uses;
audioop's ulaw2lin/lin2ulaw do the byte-for-byte conversion to/from the linear
PCM16 the rest of this codebase already understands.
"""

import audioop
import numpy as np

from audio_formatting import VAD_FRAME_SAMPLES


def mulaw_to_pcm16(data: bytes) -> bytes:
    """8-bit mu-law bytes -> 16-bit linear PCM bytes, same sample rate."""
    return audioop.ulaw2lin(data, 2)


def pcm16_to_mulaw(data: bytes) -> bytes:
    """16-bit linear PCM bytes -> 8-bit mu-law bytes, same sample rate."""
    return audioop.lin2ulaw(data, 2)


class Resampler:
    """Stateful wrapper around audioop.ratecv for one direction of one call.

    ratecv is a small interpolation filter, not a stateless per-chunk formula
    -- it carries an internal history between calls so the samples at a chunk
    boundary continue smoothly from the chunk before. Twilio hands us audio in
    ~20ms pieces, so every chunk is a boundary; passing state=None each time
    (the call that looks "stateless" and therefore simpler) restarts the
    filter from scratch every 20ms and produces an audible click at every
    boundary. Keeping one Resampler instance alive for the life of a call (one
    per direction) keeps one continuous filter state instead.
    """

    def __init__(self, in_rate: int, out_rate: int, width: int = 2, channels: int = 1):
        self.in_rate = in_rate
        self.out_rate = out_rate
        self.width = width
        self.channels = channels
        self._state = None

    def process(self, data: bytes) -> bytes:
        converted, self._state = audioop.ratecv(
            data, self.width, self.channels, self.in_rate, self.out_rate, self._state
        )
        return converted


class FrameAccumulator:
    """Buffers float32 samples, yielding exactly `frame_size` samples at a time.

    Silero VAD errors on any input that isn't exactly VAD_FRAME_SAMPLES (512).
    Twilio's 20ms frames are 160 samples at 8kHz, 320 after resampling to
    16kHz -- never 512, and not a clean divisor of it either (two frames is
    640 samples: one full 512 frame plus 128 left over for next time). Without
    this accumulator, frame size drifts in and out of alignment with VAD calls
    and the gate looks "flaky" when the real bug is a size mismatch, not the
    model or the threshold.
    """

    def __init__(self, frame_size: int = VAD_FRAME_SAMPLES):
        self.frame_size = frame_size
        self._buffer = np.empty(0, dtype=np.float32)

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        """Accept any number of new samples; return all complete frames now available."""
        self._buffer = np.concatenate([self._buffer, samples])
        frames = []
        while len(self._buffer) >= self.frame_size:
            frames.append(self._buffer[: self.frame_size])
            self._buffer = self._buffer[self.frame_size:]
        return frames


# ---------------------------------------------------------------------------
# STANDALONE TEST — `python twilio_audio.py`. No mic, no network, no Twilio:
# everything here runs on synthetic data so the transcode boundary can be
# proven correct in isolation, before any of it touches a real phone call.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    def make_tone(seconds: float, rate: int, freq: float = 440.0) -> np.ndarray:
        t = np.arange(int(seconds * rate)) / rate
        return (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)

    failures = 0

    # --- check 1: mu-law round-trip fidelity -------------------------------
    # mu-law is lossy by design (8 bits standing in for 16) -- bound the
    # error instead of expecting bit-exactness.
    tone = make_tone(1.0, 8000)
    roundtripped = np.frombuffer(mulaw_to_pcm16(pcm16_to_mulaw(tone.tobytes())), dtype=np.int16)
    mean_abs_error = np.mean(np.abs(tone.astype(np.int64) - roundtripped.astype(np.int64)))
    print(f"[1] mu-law round-trip mean abs error: {mean_abs_error:.1f} (full scale 32767)")
    if mean_abs_error >= 500:
        print("    FAIL: error too large for a correct mu-law codec")
        failures += 1
    else:
        print("    pass")

    # --- check 2: accumulator emits only 512-sample frames, no loss --------
    # Feed it in 320-sample pieces (one resampled Twilio frame each) and
    # confirm: every frame is exactly 512 long, and the concatenation of all
    # output frames + final leftover reconstructs the input exactly.
    rng = np.random.default_rng(0)
    acc = FrameAccumulator()
    pieces = [rng.standard_normal(320).astype(np.float32) for _ in range(50)]
    all_frames = []
    for piece in pieces:
        all_frames.extend(acc.feed(piece))

    sizes_ok = all(len(f) == VAD_FRAME_SAMPLES for f in all_frames)
    reconstructed = np.concatenate(all_frames + [acc._buffer]) if all_frames else acc._buffer
    original = np.concatenate(pieces)
    no_loss = np.array_equal(reconstructed, original)
    print(f"[2] accumulator: {len(all_frames)} frames emitted, all size 512: {sizes_ok}, "
          f"no sample loss: {no_loss}")
    if not (sizes_ok and no_loss):
        print("    FAIL")
        failures += 1
    else:
        print("    pass")

    # --- check 3: resampler state persistence -------------------------------
    # A stateful Resampler fed many small chunks should reconstruct the same
    # output as one single ratecv call over the whole signal. A "stateless"
    # resampler (state reset to None every call -- the bug being avoided)
    # should NOT match, demonstrating why persisting state matters.
    pcm_8k = tone.tobytes()
    chunk_bytes = 320  # 80 samples/chunk, an arbitrarily small piece size

    oneshot, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

    stateful = Resampler(8000, 16000)
    streamed_stateful = b"".join(
        stateful.process(pcm_8k[i:i + chunk_bytes])
        for i in range(0, len(pcm_8k), chunk_bytes)
    )

    stateless_state = None
    streamed_stateless_parts = []
    for i in range(0, len(pcm_8k), chunk_bytes):
        part, stateless_state = audioop.ratecv(pcm_8k[i:i + chunk_bytes], 2, 1, 8000, 16000, None)
        streamed_stateless_parts.append(part)
    streamed_stateless = b"".join(streamed_stateless_parts)

    stateful_matches = streamed_stateful == oneshot
    stateless_matches = streamed_stateless == oneshot
    print(f"[3] stateful Resampler matches one-shot call: {stateful_matches} "
          f"(expected True)")
    print(f"    stateless (state=None every call) matches one-shot: {stateless_matches} "
          f"(expected False -- this is the click bug constraint #3 warns about)")
    if not stateful_matches or stateless_matches:
        print("    FAIL")
        failures += 1
    else:
        print("    pass")

    if failures:
        print(f"\n{failures} check(s) failed.")
        sys.exit(1)
    print("\nall checks passed.")

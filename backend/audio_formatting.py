import audioop


def mulawToPcm(raw_mulaw: bytes) -> bytes:
    """Converts the raw mulaw (8kHz) audio signal to PCM (16KHz) signal"""
    pcm_8k = audioop.ulaw2lin(raw_mulaw, 2)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k 


def PcmToMulaw(raw_pcm: bytes) -> bytes:
    """Converts the raw PCM (16kHz) audio signal to mulaw (8kHz) signal """
    pcm_8k, _ = audioop.ratecv(pcm, 2, 1, src_rate, 8000, None)
    mulaw_8k = audioop.lin2ulaw(pcm_8k, 2)
    return mulaw_8k


def VAD():
    """detects user interruption to then abandon the current processing and add on to the user prompt before starting processing again"""
    pass

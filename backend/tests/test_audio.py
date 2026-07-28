import audioop
import math
import struct

from app.audio import (
    SpeechActivity,
    mulaw_8k_to_pcm16_16k,
    pcm16_24k_to_mulaw_8k,
    pcm16_rms_db,
)


def sine_pcm(sample_rate: int, duration: float = 0.1) -> bytes:
    values = [
        int(8_000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        for i in range(round(sample_rate * duration))
    ]
    return struct.pack(f"<{len(values)}h", *values)


def test_twilio_audio_round_trip_has_expected_lengths():
    pcm_24k = sine_pcm(24_000)
    mulaw_8k = pcm16_24k_to_mulaw_8k(pcm_24k)
    pcm_16k = mulaw_8k_to_pcm16_16k(mulaw_8k)
    assert 790 <= len(mulaw_8k) <= 810
    assert 3_180 <= len(pcm_16k) <= 3_220
    assert audioop.rms(pcm_16k, 2) > 1_000


def test_rms_db_silence_and_signal():
    assert pcm16_rms_db(b"\x00\x00" * 160) <= -89
    assert -20 < pcm16_rms_db(sine_pcm(16_000)) < -5


def test_speech_activity_reports_one_latency_per_phrase():
    meter = SpeechActivity()
    assert meter.update(-20, 1.0)
    assert not meter.update(-18, 1.1)
    assert meter.consume_latency(1.5) == 500
    assert meter.consume_latency(1.6) is None


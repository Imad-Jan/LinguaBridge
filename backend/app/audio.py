from __future__ import annotations

import audioop
import math
import struct
from dataclasses import dataclass


def mulaw_8k_to_pcm16_16k(payload: bytes) -> bytes:
    """Decode Twilio G.711 μ-law/8k and resample to Gemini PCM16/16k."""
    if not payload:
        return b""
    pcm_8k = audioop.ulaw2lin(payload, 2)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8_000, 16_000, None)
    return pcm_16k


def pcm16_24k_to_mulaw_8k(payload: bytes) -> bytes:
    """Resample Gemini PCM16/24k output and encode for Twilio."""
    if not payload:
        return b""
    pcm_8k, _ = audioop.ratecv(payload, 2, 1, 24_000, 8_000, None)
    return audioop.lin2ulaw(pcm_8k, 2)


def mulaw_rms_db(payload: bytes) -> float:
    if not payload:
        return -90.0
    return pcm16_rms_db(audioop.ulaw2lin(payload, 2))


def pcm16_rms_db(payload: bytes) -> float:
    if len(payload) < 2:
        return -90.0
    sample_count = len(payload) // 2
    samples = struct.unpack(f"<{sample_count}h", payload[: sample_count * 2])
    rms = math.sqrt(sum(sample * sample for sample in samples) / sample_count)
    if rms <= 1:
        return -90.0
    return max(-90.0, 20 * math.log10(rms / 32768.0))


@dataclass
class SpeechActivity:
    threshold_db: float = -44.0
    active: bool = False
    phrase_started_at: float | None = None
    most_recent_start: float | None = None
    waiting_for_audio: bool = False

    def update(self, level_db: float, now: float) -> bool:
        """Return True only when a new speech phrase begins."""
        if level_db >= self.threshold_db and not self.active:
            self.active = True
            self.phrase_started_at = now
            self.most_recent_start = now
            self.waiting_for_audio = True
            return True
        if level_db < self.threshold_db - 8:
            self.active = False
        return False

    def consume_latency(self, now: float) -> int | None:
        if not self.waiting_for_audio or self.most_recent_start is None:
            return None
        self.waiting_for_audio = False
        return max(0, round((now - self.most_recent_start) * 1000))


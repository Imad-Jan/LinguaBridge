from __future__ import annotations

import asyncio
import audioop
import base64
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from .audio import (
    SpeechActivity,
    mulaw_8k_to_pcm16_16k,
    mulaw_rms_db,
    pcm16_24k_to_mulaw_8k,
    pcm16_rms_db,
)
from .config_store import StoredConfig
from .models import CallPrepareInput, CallSnapshot, ProviderName
from .providers.base import TranslationDirection
from .providers.gemini import GeminiDirection
from .providers.soniox import SonioxDirection

logger = logging.getLogger(__name__)


CALLER_TO_CALLEE = "caller_to_callee"
CALLEE_TO_CALLER = "callee_to_caller"


@dataclass
class CallSession:
    call_id: str
    browser_token: str
    stream_token: str
    config: StoredConfig
    request: CallPrepareInput
    started_at: float = field(default_factory=time.time)
    status: str = "prepared"
    twilio_call_sid: str | None = None
    twilio_stream_sid: str | None = None
    browser_ws: WebSocket | None = None
    twilio_ws: WebSocket | None = None
    browser_send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    twilio_send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    twilio_ready: asyncio.Event = field(default_factory=asyncio.Event)
    providers_ready: asyncio.Event = field(default_factory=asyncio.Event)
    directions: dict[str, TranslationDirection] = field(default_factory=dict)
    transcript_events: int = 0
    latency_samples_ms: list[int] = field(default_factory=list)
    meters: dict[str, SpeechActivity] = field(
        default_factory=lambda: {
            CALLER_TO_CALLEE: SpeechActivity(),
            CALLEE_TO_CALLER: SpeechActivity(),
        }
    )
    last_meter_emit: dict[str, float] = field(default_factory=dict)
    twilio_audio_sequence: int = 0
    closed: bool = False

    async def attach_browser(self, ws: WebSocket) -> None:
        self.browser_ws = ws
        self.status = "warming"
        await self.emit(
            {
                "type": "call_status",
                "message": "Preparing translation sessions",
                "status": self.status,
            }
        )

    async def start_providers(self) -> None:
        if self.directions:
            return
        value = self.config.value
        if self.request.provider == ProviderName.GEMINI:
            if not value.gemini_api_key:
                raise RuntimeError("Gemini API key is not configured")
            self.directions = {
                CALLER_TO_CALLEE: GeminiDirection(
                    api_key=value.gemini_api_key,
                    direction=CALLER_TO_CALLEE,
                    target_language=self.request.callee_language,
                    echo_target_language=self.request.echo_target_language,
                    audio_sink=self._audio_to_twilio,
                    event_sink=self._provider_event,
                ),
                CALLEE_TO_CALLER: GeminiDirection(
                    api_key=value.gemini_api_key,
                    direction=CALLEE_TO_CALLER,
                    target_language=self.request.caller_language,
                    echo_target_language=self.request.echo_target_language,
                    audio_sink=self._audio_to_browser,
                    event_sink=self._provider_event,
                ),
            }
        else:
            if not value.soniox_api_key:
                raise RuntimeError("Soniox API key is not configured")
            self.directions = {
                CALLER_TO_CALLEE: SonioxDirection(
                    api_key=value.soniox_api_key,
                    direction=CALLER_TO_CALLEE,
                    source_language=self.request.caller_language,
                    target_language=self.request.callee_language,
                    input_format="pcm_s16le",
                    output_format="pcm_mulaw",
                    voice=self.request.callee_voice,
                    context_text=self.request.soniox_context,
                    audio_sink=self._audio_to_twilio,
                    event_sink=self._provider_event,
                ),
                CALLEE_TO_CALLER: SonioxDirection(
                    api_key=value.soniox_api_key,
                    direction=CALLEE_TO_CALLER,
                    source_language=self.request.callee_language,
                    target_language=self.request.caller_language,
                    input_format="mulaw",
                    output_format="pcm_s16le",
                    voice=self.request.caller_voice,
                    context_text=self.request.soniox_context,
                    audio_sink=self._audio_to_browser,
                    event_sink=self._provider_event,
                ),
            }
        try:
            await asyncio.gather(
                *(direction.start() for direction in self.directions.values())
            )
        except Exception:
            await asyncio.gather(
                *(direction.close() for direction in self.directions.values()),
                return_exceptions=True,
            )
            self.directions.clear()
            raise
        self.providers_ready.set()
        self.status = "ready"
        await self.emit(
            {
                "type": "providers_ready",
                "message": f"{self.request.provider.value.title()} is ready",
                "status": self.status,
            }
        )

    async def attach_twilio(
        self, ws: WebSocket, *, stream_sid: str, call_sid: str | None
    ) -> None:
        self.twilio_ws = ws
        self.twilio_stream_sid = stream_sid
        self.twilio_call_sid = call_sid or self.twilio_call_sid
        self.twilio_ready.set()
        self.status = "in-progress"
        await self.emit(
            {
                "type": "twilio_connected",
                "message": "Callee answered; live translation is active",
                "status": self.status,
            }
        )

    async def handle_browser_audio(self, payload: bytes) -> None:
        if self.closed or CALLER_TO_CALLEE not in self.directions:
            return
        now = time.monotonic()
        level = pcm16_rms_db(payload)
        await self._meter(CALLER_TO_CALLEE, level, now)
        await self.directions[CALLER_TO_CALLEE].send_audio(payload)

    async def handle_twilio_audio(self, payload: bytes) -> None:
        if self.closed or CALLEE_TO_CALLER not in self.directions:
            return
        now = time.monotonic()
        try:
            level = mulaw_rms_db(payload)
            provider_payload = (
                mulaw_8k_to_pcm16_16k(payload)
                if self.request.provider == ProviderName.GEMINI
                else payload
            )
        except audioop.error:
            logger.warning("Dropping malformed Twilio audio frame for call %s", self.call_id)
            return
        await self._meter(CALLEE_TO_CALLER, level, now)
        await self.directions[CALLEE_TO_CALLER].send_audio(provider_payload)

    async def _meter(self, direction: str, level: float, now: float) -> None:
        self.meters[direction].update(level, now)
        if now - self.last_meter_emit.get(direction, 0) >= 0.1:
            self.last_meter_emit[direction] = now
            await self.emit(
                {
                    "type": "audio_level",
                    "direction": direction,
                    "value": round(level, 1),
                }
            )

    async def _audio_to_twilio(self, payload: bytes) -> None:
        if not self.twilio_ready.is_set() or self.twilio_ws is None:
            return
        now = time.monotonic()
        await self._record_latency(CALLER_TO_CALLEE, now)
        twilio_audio = (
            pcm16_24k_to_mulaw_8k(payload)
            if self.request.provider == ProviderName.GEMINI
            else payload
        )
        if not twilio_audio:
            return
        async with self.twilio_send_lock:
            await self.twilio_ws.send_json(
                {
                    "event": "media",
                    "streamSid": self.twilio_stream_sid,
                    "media": {
                        "payload": base64.b64encode(twilio_audio).decode("ascii")
                    },
                }
            )
            self.twilio_audio_sequence += 1
            if self.twilio_audio_sequence % 8 == 0:
                await self.twilio_ws.send_json(
                    {
                        "event": "mark",
                        "streamSid": self.twilio_stream_sid,
                        "mark": {"name": f"audio-{self.twilio_audio_sequence}"},
                    }
                )

    async def _audio_to_browser(self, payload: bytes) -> None:
        if self.browser_ws is None or not payload:
            return
        await self._record_latency(CALLEE_TO_CALLER, time.monotonic())
        async with self.browser_send_lock:
            await self.browser_ws.send_bytes(payload)

    async def _record_latency(self, direction: str, now: float) -> None:
        latency = self.meters[direction].consume_latency(now)
        if latency is None:
            return
        self.latency_samples_ms.append(latency)
        self.latency_samples_ms = self.latency_samples_ms[-100:]
        await self.emit(
            {
                "type": "latency",
                "direction": direction,
                "value": latency,
                "message": "Speech onset to first translated audio",
            }
        )

    async def _provider_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "transcript":
            self.transcript_events += 1
        await self.emit(event)

    async def emit(self, event: dict[str, Any]) -> None:
        if self.browser_ws is None:
            return
        payload = {**event, "timestamp": time.time()}
        try:
            async with self.browser_send_lock:
                await self.browser_ws.send_json(payload)
        except Exception:
            return

    async def clear_twilio_playback(self) -> None:
        if self.twilio_ws is None or not self.twilio_ready.is_set():
            return
        async with self.twilio_send_lock:
            await self.twilio_ws.send_json(
                {"event": "clear", "streamSid": self.twilio_stream_sid}
            )

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.status = "completed"
        await asyncio.gather(
            *(direction.close() for direction in self.directions.values()),
            return_exceptions=True,
        )
        self.directions.clear()
        call_registry.remove(self.call_id)

    def snapshot(self) -> CallSnapshot:
        return CallSnapshot(
            call_id=self.call_id,
            provider=self.request.provider,
            status=self.status,
            from_number=self.request.from_number,
            to_number=self.request.to_number,
            caller_language=self.request.caller_language,
            callee_language=self.request.callee_language,
            twilio_call_sid=self.twilio_call_sid,
            started_at=self.started_at,
            transcript_events=self.transcript_events,
            latency_samples_ms=self.latency_samples_ms,
        )


class CallRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    def create(self, config: StoredConfig, request: CallPrepareInput) -> CallSession:
        call_id = uuid4().hex
        session = CallSession(
            call_id=call_id,
            browser_token=secrets.token_urlsafe(32),
            stream_token=secrets.token_urlsafe(32),
            config=config,
            request=request,
        )
        self._sessions[call_id] = session
        return session

    def get(self, call_id: str) -> CallSession | None:
        return self._sessions.get(call_id)

    def all(self) -> list[CallSession]:
        return list(self._sessions.values())

    def remove(self, call_id: str) -> None:
        self._sessions.pop(call_id, None)


call_registry = CallRegistry()


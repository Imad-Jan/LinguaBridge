from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Literal
from uuid import uuid4

import websockets

from .base import AudioSink, DirectionName, EventSink, TranslationDirection


SONIOX_STT_WS = "wss://stt-rt.soniox.com/transcribe-websocket"
SONIOX_TTS_WS = "wss://tts-rt.soniox.com/tts-websocket"

InputFormat = Literal["pcm_s16le", "mulaw"]
OutputFormat = Literal["pcm_s16le", "pcm_mulaw"]


def soniox_stt_config(
    *,
    api_key: str,
    target_language: str,
    input_format: InputFormat,
    source_language: str | None = None,
    context_text: str = "",
) -> dict[str, Any]:
    sample_rate = 16_000 if input_format == "pcm_s16le" else 8_000
    config: dict[str, Any] = {
        "api_key": api_key,
        "model": "stt-rt-v5",
        "audio_format": input_format,
        "sample_rate": sample_rate,
        "num_channels": 1,
        "enable_endpoint_detection": True,
        "max_endpoint_delay_ms": 500,
        "endpoint_sensitivity": 0.35,
        "enable_language_identification": True,
        "translation": {
            "type": "one_way",
            "target_language": target_language,
        },
    }
    if source_language:
        config["language_hints"] = [source_language]
    if context_text.strip():
        config["context"] = {"text": context_text.strip()}
    return config


def soniox_tts_config(
    *,
    api_key: str,
    stream_id: str,
    language: str,
    voice: str,
    output_format: OutputFormat,
) -> dict[str, Any]:
    return {
        "api_key": api_key,
        "stream_id": stream_id,
        "model": "tts-rt-v1",
        "language": language,
        "voice": voice,
        "audio_format": output_format,
        "sample_rate": 8_000 if output_format == "pcm_mulaw" else 24_000,
    }


class SonioxDirection(TranslationDirection):
    def __init__(
        self,
        *,
        api_key: str,
        direction: DirectionName,
        source_language: str,
        target_language: str,
        input_format: InputFormat,
        output_format: OutputFormat,
        voice: str,
        context_text: str,
        audio_sink: AudioSink,
        event_sink: EventSink,
    ) -> None:
        super().__init__(
            direction=direction,
            target_language=target_language,
            audio_sink=audio_sink,
            event_sink=event_sink,
        )
        self.api_key = api_key
        self.source_language = source_language
        self.input_format = input_format
        self.output_format = output_format
        self.voice = voice
        self.context_text = context_text
        self.stt_ws: Any = None
        self.tts_ws: Any = None
        self.tasks: list[asyncio.Task[None]] = []
        self.tts_queue: asyncio.Queue[tuple[str, str | None] | None] = asyncio.Queue()
        self.tts_idle = asyncio.Event()
        self.tts_idle.set()
        self.current_stream_id: str | None = None
        self.current_stream_used = False
        self.stream_counter = 0
        self._closed = False

    async def start(self) -> None:
        self.stt_ws = await websockets.connect(
            SONIOX_STT_WS, max_size=4 * 1024 * 1024, ping_interval=20
        )
        await self.stt_ws.send(
            json.dumps(
                soniox_stt_config(
                    api_key=self.api_key,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    input_format=self.input_format,
                    context_text=self.context_text,
                )
            )
        )
        self.tts_ws = await websockets.connect(
            SONIOX_TTS_WS, max_size=4 * 1024 * 1024, ping_interval=20
        )
        self.current_stream_id = f"prewarm-{uuid4().hex[:10]}"
        await self.tts_ws.send(
            json.dumps(
                soniox_tts_config(
                    api_key=self.api_key,
                    stream_id=self.current_stream_id,
                    language=self.target_language,
                    voice=self.voice,
                    output_format=self.output_format,
                )
            )
        )
        self.tts_idle.clear()
        self.tasks = [
            asyncio.create_task(self._receive_stt()),
            asyncio.create_task(self._send_tts()),
            asyncio.create_task(self._receive_tts()),
            asyncio.create_task(self._keepalive_tts()),
        ]
        await self.event_sink(
            {
                "type": "provider_status",
                "direction": self.direction,
                "message": "Soniox STT and TTS sessions ready",
            }
        )

    async def send_audio(self, payload: bytes) -> None:
        if self._closed or not payload or self.stt_ws is None:
            return
        await self.stt_ws.send(payload)

    async def _receive_stt(self) -> None:
        try:
            async for raw in self.stt_ws:
                data = json.loads(raw)
                if data.get("error_code") is not None:
                    await self.event_sink(
                        {
                            "type": "error",
                            "direction": self.direction,
                            "message": (
                                f"Soniox STT {data.get('error_type')}: "
                                f"{data.get('error_message')}"
                            ),
                        }
                    )
                    break
                for token in data.get("tokens", []):
                    text = token.get("text", "")
                    if not text:
                        continue
                    if text == "<end>":
                        await self.tts_queue.put(("end", None))
                        continue
                    status = token.get("translation_status")
                    if status in {"original", "none"}:
                        await self.event_sink(
                            {
                                "type": "transcript",
                                "direction": self.direction,
                                "stage": "source",
                                "text": text,
                                "language": token.get("language"),
                                "is_final": bool(token.get("is_final")),
                            }
                        )
                    elif status == "translation":
                        await self.event_sink(
                            {
                                "type": "transcript",
                                "direction": self.direction,
                                "stage": "translation",
                                "text": text,
                                "language": token.get("language"),
                                "is_final": bool(token.get("is_final")),
                            }
                        )
                        # This mirrors Soniox's official STS reference:
                        # translation tokens are streamed to TTS and <end>
                        # closes one utterance.
                        await self.tts_queue.put(("text", text))
                if data.get("finished"):
                    break
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._closed:
                await self.event_sink(
                    {
                        "type": "error",
                        "direction": self.direction,
                        "message": f"Soniox STT connection closed: {exc}",
                    }
                )
        finally:
            await self.tts_queue.put(("end", None))

    async def _send_tts(self) -> None:
        try:
            while True:
                item = await self.tts_queue.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "text":
                    if self.current_stream_id is None:
                        await self.tts_idle.wait()
                        self.stream_counter += 1
                        self.current_stream_id = (
                            f"{self.direction}-{self.stream_counter}-{uuid4().hex[:6]}"
                        )
                        await self.tts_ws.send(
                            json.dumps(
                                soniox_tts_config(
                                    api_key=self.api_key,
                                    stream_id=self.current_stream_id,
                                    language=self.target_language,
                                    voice=self.voice,
                                    output_format=self.output_format,
                                )
                            )
                        )
                    await self.tts_ws.send(
                        json.dumps(
                            {
                                "stream_id": self.current_stream_id,
                                "text": payload,
                                "text_end": False,
                            }
                        )
                    )
                    self.current_stream_used = True
                elif (
                    kind == "end"
                    and self.current_stream_id is not None
                    and self.current_stream_used
                ):
                    self.tts_idle.clear()
                    stream_id = self.current_stream_id
                    await self.tts_ws.send(
                        json.dumps(
                            {"stream_id": stream_id, "text": "", "text_end": True}
                        )
                    )
                    self.current_stream_id = None
                    self.current_stream_used = False
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._closed:
                await self.event_sink(
                    {
                        "type": "error",
                        "direction": self.direction,
                        "message": f"Soniox TTS sender closed: {exc}",
                    }
                )

    async def _receive_tts(self) -> None:
        try:
            async for raw in self.tts_ws:
                data = json.loads(raw)
                if data.get("error_code") is not None:
                    await self.event_sink(
                        {
                            "type": "error",
                            "direction": self.direction,
                            "message": (
                                f"Soniox TTS {data.get('error_type')}: "
                                f"{data.get('error_message')}"
                            ),
                        }
                    )
                    continue
                if data.get("audio"):
                    await self.audio_sink(base64.b64decode(data["audio"]))
                if data.get("terminated"):
                    self.tts_idle.set()
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._closed:
                await self.event_sink(
                    {
                        "type": "error",
                        "direction": self.direction,
                        "message": f"Soniox TTS receiver closed: {exc}",
                    }
                )

    async def _keepalive_tts(self) -> None:
        try:
            while True:
                await asyncio.sleep(20)
                await self.tts_ws.send(json.dumps({"keep_alive": True}))
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed:
            return

    async def close(self) -> None:
        self._closed = True
        if self.stt_ws is not None:
            try:
                await self.stt_ws.send(b"")
            except Exception:
                pass
        if (
            self.tts_ws is not None
            and self.current_stream_id is not None
            and self.current_stream_used
        ):
            try:
                await self.tts_ws.send(
                    json.dumps(
                        {
                            "stream_id": self.current_stream_id,
                            "text": "",
                            "text_end": True,
                        }
                    )
                )
            except Exception:
                pass
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.stt_ws is not None:
            await self.stt_ws.close()
        if self.tts_ws is not None:
            await self.tts_ws.close()


async def probe_soniox(api_key: str) -> None:
    ws = await websockets.connect(
        SONIOX_STT_WS, open_timeout=8, close_timeout=3, ping_interval=None
    )
    try:
        await ws.send(
            json.dumps(
                soniox_stt_config(
                    api_key=api_key,
                    target_language="en",
                    input_format="pcm_s16le",
                    source_language="ur",
                )
            )
        )
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
        except TimeoutError:
            return
        data = json.loads(raw)
        if data.get("error_code"):
            raise RuntimeError(data.get("error_message", "Soniox rejected the key"))
    finally:
        try:
            await ws.send(b"")
        except Exception:
            pass
        await ws.close()


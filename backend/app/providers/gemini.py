from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from urllib.parse import quote

import websockets

from .base import AudioSink, DirectionName, EventSink, TranslationDirection


GEMINI_MODEL = "gemini-3.5-live-translate-preview"
GEMINI_WS = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)


def gemini_setup_payload(
    target_language: str, echo_target_language: bool = True
) -> dict[str, Any]:
    return {
        "setup": {
            "model": f"models/{GEMINI_MODEL}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "translationConfig": {
                    "targetLanguageCode": target_language,
                    "echoTargetLanguage": echo_target_language,
                },
            },
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
    }


class GeminiDirection(TranslationDirection):
    def __init__(
        self,
        *,
        api_key: str,
        direction: DirectionName,
        target_language: str,
        audio_sink: AudioSink,
        event_sink: EventSink,
        echo_target_language: bool,
    ) -> None:
        super().__init__(
            direction=direction,
            target_language=target_language,
            audio_sink=audio_sink,
            event_sink=event_sink,
        )
        self.api_key = api_key
        self.echo_target_language = echo_target_language
        self.ws: Any = None
        self.receiver_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start(self) -> None:
        url = f"{GEMINI_WS}?key={quote(self.api_key)}"
        self.ws = await websockets.connect(
            url, max_size=8 * 1024 * 1024, ping_interval=20, ping_timeout=20
        )
        await self.ws.send(
            json.dumps(
                gemini_setup_payload(
                    self.target_language, self.echo_target_language
                )
            )
        )
        try:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=12)
        except TimeoutError as exc:
            raise RuntimeError("Gemini did not acknowledge the Live session") from exc
        message = json.loads(raw)
        if "setupComplete" not in message:
            error = message.get("error", {}).get("message") or str(message)
            raise RuntimeError(f"Gemini setup failed: {error}")
        await self.event_sink(
            {
                "type": "provider_status",
                "direction": self.direction,
                "message": "Gemini Live session ready",
            }
        )
        self.receiver_task = asyncio.create_task(self._receive())

    async def send_audio(self, payload: bytes) -> None:
        if self._closed or not payload or self.ws is None:
            return
        await self.ws.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "audio": {
                            "data": base64.b64encode(payload).decode("ascii"),
                            "mimeType": "audio/pcm;rate=16000",
                        }
                    }
                }
            )
        )

    async def _receive(self) -> None:
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "error" in data:
                    message = data["error"].get("message", "Unknown Gemini error")
                    await self.event_sink(
                        {
                            "type": "error",
                            "direction": self.direction,
                            "message": f"Gemini: {message}",
                        }
                    )
                    continue
                content = data.get("serverContent") or {}
                input_tx = content.get("inputTranscription")
                if input_tx and input_tx.get("text"):
                    await self.event_sink(
                        {
                            "type": "transcript",
                            "direction": self.direction,
                            "stage": "source",
                            "text": input_tx["text"],
                            "language": input_tx.get("languageCode"),
                            "is_final": False,
                        }
                    )
                output_tx = content.get("outputTranscription")
                if output_tx and output_tx.get("text"):
                    await self.event_sink(
                        {
                            "type": "transcript",
                            "direction": self.direction,
                            "stage": "translation",
                            "text": output_tx["text"],
                            "language": output_tx.get("languageCode"),
                            "is_final": False,
                        }
                    )
                for part in (content.get("modelTurn") or {}).get("parts", []):
                    inline = part.get("inlineData")
                    if inline and inline.get("data"):
                        await self.audio_sink(base64.b64decode(inline["data"]))
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._closed:
                await self.event_sink(
                    {
                        "type": "error",
                        "direction": self.direction,
                        "message": f"Gemini connection closed: {exc}",
                    }
                )
        except Exception as exc:
            if not self._closed:
                await self.event_sink(
                    {
                        "type": "error",
                        "direction": self.direction,
                        "message": f"Gemini receiver error: {exc}",
                    }
                )

    async def close(self) -> None:
        self._closed = True
        if self.receiver_task:
            self.receiver_task.cancel()
            await asyncio.gather(self.receiver_task, return_exceptions=True)
        if self.ws is not None:
            await self.ws.close()


async def probe_gemini(api_key: str) -> None:
    ws = await websockets.connect(
        f"{GEMINI_WS}?key={quote(api_key)}",
        open_timeout=8,
        close_timeout=3,
    )
    try:
        await ws.send(json.dumps(gemini_setup_payload("en", True)))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        message = json.loads(raw)
        if "setupComplete" not in message:
            error = message.get("error", {}).get("message") or str(message)
            raise RuntimeError(error)
    finally:
        await ws.close()


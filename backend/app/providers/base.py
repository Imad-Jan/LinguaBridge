from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Literal


DirectionName = Literal["caller_to_callee", "callee_to_caller"]
AudioSink = Callable[[bytes], Awaitable[None]]
EventSink = Callable[[dict[str, Any]], Awaitable[None]]


class TranslationDirection(ABC):
    def __init__(
        self,
        *,
        direction: DirectionName,
        target_language: str,
        audio_sink: AudioSink,
        event_sink: EventSink,
    ) -> None:
        self.direction = direction
        self.target_language = target_language
        self.audio_sink = audio_sink
        self.event_sink = event_sink

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_audio(self, payload: bytes) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


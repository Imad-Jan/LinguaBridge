from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .models import RuntimeConfigInput


@dataclass(frozen=True)
class StoredConfig:
    config_id: str
    value: RuntimeConfigInput


class ConfigStore:
    """In-memory secret store. Keys never go into browser storage or source files."""

    def __init__(self) -> None:
        self._configs: dict[str, StoredConfig] = {}

    def put(self, value: RuntimeConfigInput) -> StoredConfig:
        stored = StoredConfig(config_id=uuid4().hex, value=value)
        self._configs[stored.config_id] = stored
        return stored

    def get(self, config_id: str) -> StoredConfig | None:
        return self._configs.get(config_id)

    def delete(self, config_id: str) -> None:
        self._configs.pop(config_id, None)


config_store = ConfigStore()


from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class ProviderName(str, Enum):
    GEMINI = "gemini"
    SONIOX = "soniox"


class RuntimeConfigInput(BaseModel):
    public_base_url: str = Field(min_length=8)
    twilio_account_sid: str = Field(min_length=34, max_length=34)
    twilio_auth_token: str = Field(min_length=8)
    gemini_api_key: str | None = None
    soniox_api_key: str | None = None
    validate_credentials: bool = True

    @field_validator("public_base_url")
    @classmethod
    def normalize_public_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("Public URL must start with https:// or http://")
        return value

    @field_validator(
        "twilio_account_sid",
        "twilio_auth_token",
        "gemini_api_key",
        "soniox_api_key",
        mode="before",
    )
    @classmethod
    def strip_secrets(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ProviderCheck(BaseModel):
    configured: bool
    valid: bool | None = None
    message: str


class ConfigResponse(BaseModel):
    config_id: str
    twilio: ProviderCheck
    gemini: ProviderCheck
    soniox: ProviderCheck
    numbers: list[str] = []


class CallPrepareInput(BaseModel):
    config_id: str
    provider: ProviderName
    from_number: str
    to_number: str
    caller_language: str = Field(min_length=2, max_length=12)
    callee_language: str = Field(min_length=2, max_length=12)
    caller_voice: str = "Maya"
    callee_voice: str = "Adrian"
    echo_target_language: bool = True
    soniox_context: str = Field(default="", max_length=8_000)

    @field_validator("from_number", "to_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip().replace(" ", "")
        if not E164_PATTERN.fullmatch(value):
            raise ValueError("Use E.164 format, for example +14155552671")
        return value

    @field_validator("caller_language", "callee_language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return value.strip()


class CallPrepareResponse(BaseModel):
    call_id: str
    browser_token: str
    websocket_path: str


class DialResponse(BaseModel):
    call_id: str
    twilio_call_sid: str
    status: str


class CallSnapshot(BaseModel):
    call_id: str
    provider: ProviderName
    status: str
    from_number: str
    to_number: str
    caller_language: str
    callee_language: str
    twilio_call_sid: str | None = None
    started_at: float
    transcript_events: int
    latency_samples_ms: list[int]


class DashboardEvent(BaseModel):
    type: str
    direction: Literal["caller_to_callee", "callee_to_caller"] | None = None
    message: str | None = None
    text: str | None = None
    stage: str | None = None
    is_final: bool | None = None
    language: str | None = None
    value: float | int | None = None
    timestamp: float


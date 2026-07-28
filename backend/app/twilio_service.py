from __future__ import annotations

import asyncio
from dataclasses import dataclass

from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from .models import RuntimeConfigInput


@dataclass(frozen=True)
class TwilioCallResult:
    sid: str
    status: str


def websocket_public_url(public_base_url: str) -> str:
    if public_base_url.startswith("https://"):
        return "wss://" + public_base_url.removeprefix("https://")
    if public_base_url.startswith("http://"):
        return "ws://" + public_base_url.removeprefix("http://")
    raise ValueError("Public URL must use http:// or https://")


def build_stream_twiml(
    *, public_base_url: str, call_id: str, stream_token: str
) -> str:
    response = VoiceResponse()
    connect: Connect = response.connect()
    stream = connect.stream(url=f"{websocket_public_url(public_base_url)}/ws/twilio")
    stream.parameter(name="call_id", value=call_id)
    stream.parameter(name="token", value=stream_token)
    return str(response)


def _client(config: RuntimeConfigInput) -> Client:
    return Client(config.twilio_account_sid, config.twilio_auth_token)


async def validate_and_list_numbers(config: RuntimeConfigInput) -> list[str]:
    def operation() -> list[str]:
        numbers = _client(config).incoming_phone_numbers.list(limit=100)
        return [item.phone_number for item in numbers if item.phone_number]

    return await asyncio.to_thread(operation)


async def create_outbound_call(
    *,
    config: RuntimeConfigInput,
    call_id: str,
    stream_token: str,
    from_number: str,
    to_number: str,
) -> TwilioCallResult:
    twiml = build_stream_twiml(
        public_base_url=config.public_base_url,
        call_id=call_id,
        stream_token=stream_token,
    )

    def operation() -> TwilioCallResult:
        call = _client(config).calls.create(
            to=to_number,
            from_=from_number,
            twiml=twiml,
            status_callback=f"{config.public_base_url}/api/twilio/status/{call_id}",
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
        return TwilioCallResult(sid=call.sid, status=call.status or "queued")

    return await asyncio.to_thread(operation)


async def end_twilio_call(config: RuntimeConfigInput, call_sid: str) -> None:
    def operation() -> None:
        _client(config).calls(call_sid).update(status="completed")

    await asyncio.to_thread(operation)


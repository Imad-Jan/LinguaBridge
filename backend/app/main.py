from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from .config_store import config_store
from .models import (
    CallPrepareInput,
    CallPrepareResponse,
    CallSnapshot,
    ConfigResponse,
    DialResponse,
    ProviderCheck,
    ProviderName,
    RuntimeConfigInput,
)
from .providers.gemini import probe_gemini
from .providers.soniox import probe_soniox
from .sessions import call_registry
from .twilio_service import (
    create_outbound_call,
    end_twilio_call,
    validate_and_list_numbers,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await asyncio.gather(
        *(session.close() for session in call_registry.all()),
        return_exceptions=True,
    )


app = FastAPI(
    title="LinguaBridge API",
    version="0.1.0",
    description="Bidirectional browser-to-PSTN voice translation prototype",
    lifespan=lifespan,
)
cors_origins = [
    origin.strip()
    for origin in os.getenv("LINGUABRIDGE_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "linguabridge-api"}


async def _check_provider(
    name: str, key: str | None, validate: bool
) -> ProviderCheck:
    if not key:
        return ProviderCheck(
            configured=False, valid=None, message=f"{name} key not supplied"
        )
    if not validate:
        return ProviderCheck(
            configured=True, valid=None, message="Configured; validation skipped"
        )
    try:
        if name == "Gemini":
            await probe_gemini(key)
        else:
            await probe_soniox(key)
        return ProviderCheck(
            configured=True, valid=True, message="Credential accepted"
        )
    except Exception as exc:
        return ProviderCheck(
            configured=True, valid=False, message=str(exc)[:240]
        )


@app.post("/api/config", response_model=ConfigResponse)
async def save_config(payload: RuntimeConfigInput) -> ConfigResponse:
    stored = config_store.put(payload)
    numbers: list[str] = []
    if payload.validate_credentials:
        try:
            numbers = await validate_and_list_numbers(payload)
            twilio_check = ProviderCheck(
                configured=True,
                valid=True,
                message=f"Connected; {len(numbers)} voice number(s) found",
            )
        except Exception as exc:
            twilio_check = ProviderCheck(
                configured=True, valid=False, message=str(exc)[:240]
            )
    else:
        twilio_check = ProviderCheck(
            configured=True, valid=None, message="Configured; validation skipped"
        )
    gemini_check, soniox_check = await asyncio.gather(
        _check_provider(
            "Gemini", payload.gemini_api_key, payload.validate_credentials
        ),
        _check_provider(
            "Soniox", payload.soniox_api_key, payload.validate_credentials
        ),
    )
    return ConfigResponse(
        config_id=stored.config_id,
        twilio=twilio_check,
        gemini=gemini_check,
        soniox=soniox_check,
        numbers=numbers,
    )


@app.get("/api/config/{config_id}/numbers")
async def list_numbers(config_id: str) -> dict[str, list[str]]:
    stored = config_store.get(config_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Configuration expired")
    try:
        numbers = await validate_and_list_numbers(stored.value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"numbers": numbers}


@app.delete("/api/config/{config_id}")
async def delete_config(config_id: str) -> dict[str, bool]:
    config_store.delete(config_id)
    return {"deleted": True}


@app.post("/api/calls/prepare", response_model=CallPrepareResponse)
async def prepare_call(payload: CallPrepareInput) -> CallPrepareResponse:
    stored = config_store.get(payload.config_id)
    if not stored:
        raise HTTPException(
            status_code=404,
            detail="Configuration expired. Save your credentials again.",
        )
    if payload.provider == ProviderName.GEMINI and not stored.value.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini key is missing")
    if payload.provider == ProviderName.SONIOX and not stored.value.soniox_api_key:
        raise HTTPException(status_code=400, detail="Soniox key is missing")
    session = call_registry.create(stored, payload)
    return CallPrepareResponse(
        call_id=session.call_id,
        browser_token=session.browser_token,
        websocket_path=f"/ws/browser/{session.call_id}",
    )


@app.post("/api/calls/{call_id}/dial", response_model=DialResponse)
async def dial_call(call_id: str) -> DialResponse:
    session = call_registry.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    if session.browser_ws is None:
        raise HTTPException(
            status_code=409, detail="Browser audio connection is not ready"
        )
    try:
        await asyncio.wait_for(session.providers_ready.wait(), timeout=20)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=503, detail="Translation provider did not become ready"
        ) from exc
    try:
        result = await create_outbound_call(
            config=session.config.value,
            call_id=session.call_id,
            stream_token=session.stream_token,
            from_number=session.request.from_number,
            to_number=session.request.to_number,
        )
    except Exception as exc:
        await session.emit(
            {"type": "error", "message": f"Twilio could not start the call: {exc}"}
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.twilio_call_sid = result.sid
    session.status = result.status
    await session.emit(
        {
            "type": "call_status",
            "message": "Twilio is dialing the destination",
            "status": result.status,
        }
    )
    return DialResponse(
        call_id=call_id, twilio_call_sid=result.sid, status=result.status
    )


@app.post("/api/calls/{call_id}/end")
async def end_call(call_id: str) -> dict[str, str]:
    session = call_registry.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    if session.twilio_call_sid:
        try:
            await end_twilio_call(session.config.value, session.twilio_call_sid)
        except Exception as exc:
            await session.emit(
                {"type": "error", "message": f"Twilio hangup warning: {exc}"}
            )
    await session.emit(
        {"type": "call_status", "message": "Call ended", "status": "completed"}
    )
    await session.close()
    return {"status": "completed"}


@app.post("/api/calls/{call_id}/clear")
async def clear_playback(call_id: str) -> dict[str, str]:
    session = call_registry.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    await session.clear_twilio_playback()
    return {"status": "cleared"}


@app.get("/api/calls/{call_id}", response_model=CallSnapshot)
async def call_snapshot(call_id: str) -> CallSnapshot:
    session = call_registry.get(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Call session not found")
    return session.snapshot()


@app.websocket("/ws/browser/{call_id}")
async def browser_audio_socket(
    websocket: WebSocket, call_id: str, token: str = Query(...)
) -> None:
    session = call_registry.get(call_id)
    await websocket.accept()
    if not session or not secrets_compare(token, session.browser_token):
        await websocket.close(code=4403, reason="Invalid browser token")
        return
    await session.attach_browser(websocket)
    try:
        await session.start_providers()
        while True:
            message = await websocket.receive()
            if message.get("bytes") is not None:
                await session.handle_browser_audio(message["bytes"])
            elif message.get("text"):
                command = json.loads(message["text"])
                if command.get("type") == "clear_playback":
                    await session.clear_twilio_playback()
                elif command.get("type") == "ping":
                    await session.emit({"type": "pong", "value": command.get("value")})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await session.emit(
            {"type": "error", "message": f"Browser media connection: {exc}"}
        )
    finally:
        session.browser_ws = None
        if not session.closed:
            if session.twilio_call_sid:
                try:
                    await end_twilio_call(
                        session.config.value, session.twilio_call_sid
                    )
                except Exception:
                    pass
            await session.close()


@app.websocket("/ws/twilio")
async def twilio_media_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    session = None
    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            event = data.get("event")
            if event == "start":
                start = data.get("start") or {}
                params = start.get("customParameters") or {}
                candidate = call_registry.get(params.get("call_id", ""))
                if not candidate or not secrets_compare(
                    params.get("token", ""), candidate.stream_token
                ):
                    await websocket.close(code=4403, reason="Invalid stream token")
                    return
                session = candidate
                await session.attach_twilio(
                    websocket,
                    stream_sid=start.get("streamSid") or data.get("streamSid"),
                    call_sid=start.get("callSid"),
                )
            elif event == "media" and session is not None:
                payload = base64.b64decode(data["media"]["payload"])
                await session.handle_twilio_audio(payload)
            elif event == "mark" and session is not None:
                await session.emit(
                    {
                        "type": "playback_mark",
                        "message": data.get("mark", {}).get("name", "played"),
                    }
                )
            elif event == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if session is not None:
            await session.emit(
                {"type": "error", "message": f"Twilio media connection: {exc}"}
            )
    finally:
        if session is not None:
            session.twilio_ready.clear()
            session.twilio_ws = None
            if session.status not in {"completed", "failed"}:
                session.status = "media-disconnected"
                await session.emit(
                    {
                        "type": "call_status",
                        "message": "Twilio media stream disconnected",
                        "status": session.status,
                    }
                )


@app.post("/api/twilio/status/{call_id}")
async def twilio_status(
    call_id: str,
    CallStatus: str = Form(...),
    CallSid: str = Form(...),
) -> dict[str, bool]:
    session = call_registry.get(call_id)
    if session:
        session.twilio_call_sid = CallSid
        session.status = CallStatus
        await session.emit(
            {
                "type": "call_status",
                "message": f"Twilio status: {CallStatus}",
                "status": CallStatus,
            }
        )
        if CallStatus in {"completed", "failed", "busy", "no-answer", "canceled"}:
            await session.close()
    return {"ok": True}


def secrets_compare(left: str, right: str) -> bool:
    import secrets

    return secrets.compare_digest(left, right)

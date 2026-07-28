# LinguaBridge Call Console

LinguaBridge is a complete browser-to-phone voice-translation prototype. Person A
uses this web dashboard and a microphone. Twilio calls Person B on an ordinary
telephone; Person B installs nothing.

The application supports two interchangeable translation providers:

- **Gemini:** `gemini-3.5-live-translate-preview`, continuous speech-to-speech.
- **Soniox:** `stt-rt-v5` translation streamed into `tts-rt-v1`.

Both directions are independent:

1. Person A microphone → translation into Person B's language → Twilio playback.
2. Person B phone → translation into Person A's language → browser playback.

## What is included

- A responsive React/Vinext dashboard.
- A Python FastAPI backend.
- Twilio outbound calling and bidirectional Media Streams.
- Gemini and Soniox provider adapters.
- Browser microphone capture at PCM16/16 kHz.
- Twilio G.711 μ-law/8 kHz audio handling.
- Live source and translated transcripts.
- Audio-level, status, latency and playback telemetry.
- Provider toggle, language selectors and Soniox voice/context controls.
- Credential preflight and automatic loading of owned Twilio numbers.
- One-click call start, mute, clear queued audio and hangup.
- Automated frontend, backend, protocol and audio-conversion tests.
- Windows scripts, Linux/macOS scripts and Docker Compose.

## Prerequisites

### Accounts

You need:

1. A Twilio account with a voice-enabled Twilio phone number.
2. A Gemini API key, a Soniox API key, or both.
3. A public HTTPS URL pointing to backend port `8000`.

Twilio trial accounts can call only verified destination numbers. Outbound voice
permissions must also allow the destination country.

### Software

For the normal setup:

- Python 3.11 or 3.12
- Node.js 22 or newer
- npm

Docker Desktop is an alternative.

## Quick start on Windows

1. Extract the ZIP.
2. Open the extracted folder.
3. Double-click `setup.bat` once.
4. Double-click `start.bat`.
5. Open `http://localhost:3000`.

The backend runs at `http://localhost:8000`, and interactive API documentation is
available at `http://localhost:8000/docs`.

## Quick start on Linux or macOS

From the extracted directory:

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Open `http://localhost:3000`.

## Docker start

```bash
docker compose up --build
```

Then open `http://localhost:3000`.

## Create the public backend URL

Twilio cannot connect to `localhost`. It must be able to reach the Python backend
through public HTTPS/WSS.

### Development using ngrok

Start the app, then in a second terminal:

```bash
ngrok http 8000
```

Copy the HTTPS forwarding address, for example:

```text
https://example-name.ngrok-free.app
```

Paste that value into **Public backend URL** in the dashboard. Do not add
`/ws/twilio`; the application adds the correct path.

### VM or production-like testing

Point a domain such as `calls.example.com` to the VM. Put Caddy, Nginx or another
TLS reverse proxy in front of backend port 8000 and allow WebSocket upgrades.
Paste `https://calls.example.com` into the dashboard.

Example Caddyfile:

```caddy
calls.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Open inbound TCP port 443 on the VM. You do not need to configure a Twilio voice
webhook manually: the backend supplies inline TwiML when it creates the outbound
call.

## Configure the dashboard

Enter:

1. **Public backend URL** — the HTTPS tunnel or VM domain for port 8000.
2. **Twilio Account SID** — starts with `AC`.
3. **Twilio Auth Token**.
4. **Gemini API key** and/or **Soniox API key**.

If the dashboard and API are on different machines, expand **Frontend runtime**
and set **Backend address used by this browser** to the API address. The default
is `http://localhost:8000`.

Click **Save & test**. The preflight:

- Authenticates with Twilio.
- Loads voice-enabled numbers owned by the account.
- Opens a short Gemini Live session when a Gemini key is supplied.
- Opens a short Soniox STT session when a Soniox key is supplied.

Credentials are held only in Python process memory. They are not written to
source code, `.env`, browser local storage or a database. Restarting the backend
clears them.

## Place a call

1. Select Gemini or Soniox.
2. Choose Person A's spoken/listening language.
3. Choose Person B's spoken/listening language.
4. Select a Twilio number under **Call from**.
5. Enter Person B's number in E.164 format, such as `+14155552671`.
6. For Soniox, optionally select voices and add names or domain vocabulary.
7. Click **Start interpreted call** and allow microphone access.
8. Wait for the dashboard to show **Live**.

Do not speak until the call is live. Person B hears translated audio through the
normal phone call. Person A hears Person B's translated audio through the
computer speakers or headset.

Use a headset during testing. Speakers can feed translated playback back into
the microphone and cause an acoustic echo loop.

## How provider switching works

The dialer and Twilio transport stay unchanged. The backend constructs two
provider-specific translation directions:

| Direction | Gemini | Soniox |
| --- | --- | --- |
| Browser → phone | PCM16/16k → Gemini → PCM16/24k → μ-law/8k | PCM16/16k → STT translation → TTS μ-law/8k |
| Phone → browser | μ-law/8k → PCM16/16k → Gemini → PCM16/24k | μ-law/8k → STT translation → TTS PCM16/24k |

Gemini requires transcoding at the Twilio boundary. Soniox accepts and emits
Twilio-native μ-law for the telephone direction.

## Run the tests

Activate the virtual environment, then:

### Windows

```bat
.venv\Scripts\python.exe -m pytest backend\tests -q
npm test
```

### Linux or macOS

```bash
.venv/bin/python -m pytest backend/tests -q
npm test
```

## Troubleshooting

### The call does not start

- Confirm both telephone numbers include `+` and country code.
- Confirm the selected Twilio number supports outbound voice.
- Check Twilio geographic voice permissions.
- On a trial account, verify Person B's number in Twilio first.
- Click **Save & test** and read the provider status.

### The call connects but no audio appears

- Confirm the public URL points to backend port 8000, not frontend port 3000.
- Confirm the public URL supports WebSockets (`wss://`).
- Confirm microphone permission is granted.
- Check the live event panel and backend terminal.
- Use Chrome or Edge for the first prototype test.

### Person B hears distorted audio

- Do not add a WAV header to Twilio playback.
- Confirm the deployed code was not changed to send PCM directly to Twilio.
- Twilio playback must remain raw base64-encoded μ-law at 8 kHz.

### Gemini fails during setup

- Confirm the model is available for the Google account and region.
- Confirm the model remains named `gemini-3.5-live-translate-preview`.
- Preview-model availability and quota can change.

### Soniox fails after several calls

- Check STT/TTS concurrency and project limits in the Soniox Console.
- The default TTS concurrency can be lower than STT concurrency.

## Prototype limitations

- A real call cannot be verified without your private credentials, active Twilio
  number and external destination.
- Credentials and active sessions are in memory; this is intentional for a
  single-VM prototype, not a multi-instance production secret store.
- The API allows cross-origin dashboard requests by default so VM and tunnel
  testing works without another setting. Set `LINGUABRIDGE_CORS_ORIGINS` to the
  exact dashboard origin before exposing a production-like deployment.
- Gemini Live Translate is a preview model and its behavior or availability can
  change.
- The displayed live response metric is speech-onset to first translated audio.
  It is operational telemetry, not a provider SLA.
- The frontend uses `ScriptProcessorNode` for broad prototype compatibility.
  A production release should replace it with an AudioWorklet.
- Session resumption, horizontal scaling, persistent call records and
  organization-level authentication are production follow-up work.
- Do not use the prototype for medical, legal, financial or emergency
  interpretation.

## Privacy and legal checklist

Before real customer testing:

- Obtain consent for AI processing and any recording.
- Confirm call-recording and biometric/voice rules in all relevant jurisdictions.
- Use a paid provider tier whose data-use terms fit the product.
- Add authentication to the dashboard.
- Put provider keys in a managed secret store.
- Restrict network access and enable TLS.
- Define transcript retention and deletion policies.

The prototype does not record calls or write transcripts to disk.

## Project layout

```text
app/                         React dashboard
backend/app/main.py          FastAPI routes and WebSockets
backend/app/sessions.py      Two-direction call orchestration
backend/app/audio.py         PCM, μ-law and resampling utilities
backend/app/providers/       Gemini and Soniox adapters
backend/tests/               Automated backend tests
docs/ARCHITECTURE.md         Protocol and sequence documentation
launcher.py                  Starts frontend and backend
setup.bat / setup.sh         One-time dependency setup
start.bat / start.sh         Normal startup
docker-compose.yml           Container startup
```

## Documentation basis

The implementation was checked against the official documentation listed in
`docs/ARCHITECTURE.md`, current as of 28 July 2026.

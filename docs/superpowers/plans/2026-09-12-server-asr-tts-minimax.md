# Server ASR/TTS MiniMax Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first server-side ASR/TTS voice loop where the Raspberry Pi records and plays audio while the server transcribes, runs the Agent, synthesizes speech through MiniMax, and supports voice IDs for future cloning.

**Architecture:** Robot Protocol v1 remains the only Pi/server boundary. Server media handling lives under `src/agent_hub/voice/`; Pi recording/playback lives under `cube-robot-runtime/`. MiniMax API keys stay server-side and are accessed only through provider classes.

**Tech Stack:** FastAPI WebSocket, Pydantic, stdlib base64/tempfile/subprocess on Pi, MiniMax Speech APIs over HTTP, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-12-server-asr-tts-minimax-design.md`

## Global Constraints

- Pi runtime must remain isolated under `cube-robot-runtime/` and must not import or mention `agent_hub`, `cognition`, or `hermes`.
- The Pi must never store or receive `MINIMAX_API_KEY`; MiniMax credentials live only in server environment or server settings.
- Robot Protocol v1 is the only Pi/server application protocol boundary.
- Voice clone must require explicit consent before provider calls.
- Do not log raw audio, cloned voice samples, API keys, robot device tokens, or long raw transcripts.
- First implementation can use non-streaming MiniMax TTS and return one `tts.audio.chunk`; keep chunked protocol for future streaming.
- Default TTS model is `speech-2.8-turbo`; default output format is `mp3`.
- Max decoded audio per turn is 10 MB; max chunks per turn is 256; max TTS input is 2,000 characters.

---

## File Structure

- `src/agent_hub/voice/media.py`: provider protocols, media dataclasses, `VoiceMediaService`, audio session buffering, TTS envelope construction.
- `src/agent_hub/voice/minimax.py`: MiniMax HTTP provider implementation for STT/TTS/voice clone with injectable HTTP transport.
- `src/agent_hub/voice/gateway.py`: route `audio.start`, `audio.chunk`, and `audio.end` messages through `VoiceMediaService`.
- `src/agent_hub/app.py`: wire default media service/provider from settings/environment.
- `src/agent_hub/settings.py`: add MiniMax speech settings using server-side environment variables.
- `cube-robot-runtime/cube_robot_runtime/audio/capture.py`: Pi record/play command helpers.
- `cube-robot-runtime/cube_robot_runtime/voice_once.py`: one-turn voice command implementation.
- `cube-robot-runtime/cube_robot_runtime/main.py`: add `voice-once` CLI command and config fields.
- `cube-robot-runtime/config/robot.toml.example`: add `[audio]` and `[voice]` examples.
- `docs/robot-system-manual.md`: update real voice interaction and MiniMax key setup instructions.

---

### Task 1: Server Voice Media Service

**Files:**
- Create: `src/agent_hub/voice/media.py`
- Modify: `src/agent_hub/voice/gateway.py`
- Test: `tests/unit/voice/test_media.py`
- Test: `tests/api/test_robot_voice_gateway.py`

**Interfaces:**
- Consumes: `RobotEnvelope`, `RobotMessageType`, `build_envelope`, `RobotSessionRegistry.record_async`.
- Produces:
  - `VoiceAudio(codec: str, sample_rate_hz: int, data: bytes, language: str | None)`
  - `SpeechTranscript(text: str, confidence: float | None = None)`
  - `VoiceSynthesisOptions(voice_id: str | None, model: str, audio_format: str)`
  - `SynthesizedAudio(codec: str, data: bytes, sample_rate_hz: int | None = None)`
  - `VoiceMediaService.handle(envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]`

- [ ] **Step 1: Write failing media service tests**

Add to `tests/unit/voice/test_media.py`:

```python
from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.voice.media import (
    SpeechTranscript,
    SynthesizedAudio,
    VoiceMediaService,
)


class FakeStt:
    def __init__(self) -> None:
        self.audio_sizes: list[int] = []

    async def transcribe(self, audio):
        self.audio_sizes.append(len(audio.data))
        return SpeechTranscript(text="你好，机器人", confidence=0.9)


class FakeTts:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None]] = []

    async def synthesize(self, text, options):
        self.requests.append((text, options.voice_id))
        return SynthesizedAudio(codec="mp3", data=b"mp3-bytes", sample_rate_hz=32000)


async def fake_responder(envelope):
    return (
        build_envelope(
            message_type=RobotMessageType.ASSISTANT_TEXT_DONE,
            device_id=envelope.device_id,
            session_id=envelope.session_id,
            payload={"text": "收到，我来回答。"},
        ),
    )


async def test_audio_end_transcribes_runs_agent_and_returns_tts_audio() -> None:
    stt = FakeStt()
    tts = FakeTts()
    service = VoiceMediaService(stt_provider=stt, tts_provider=tts, responder=fake_responder)
    start = build_envelope(
        message_type=RobotMessageType.AUDIO_START,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={
            "codec": "wav",
            "sample_rate_hz": 16000,
            "channels": 1,
            "language": "zh",
            "voice_id": "female-shaonv",
            "tts_model": "speech-2.8-turbo",
        },
    )
    chunk = build_envelope(
        message_type=RobotMessageType.AUDIO_CHUNK,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={
            "codec": "wav",
            "sample_rate_hz": 16000,
            "sequence": 1,
            "chunk_b64": "QUJD",
        },
    )
    end = build_envelope(
        message_type=RobotMessageType.AUDIO_END,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"total_chunks": 1, "voice_id": "female-shaonv"},
    )

    assert await service.handle(start) == ()
    assert await service.handle(chunk) == ()
    responses = await service.handle(end)

    assert [response.type for response in responses] == [
        RobotMessageType.ASSISTANT_TEXT_DONE,
        RobotMessageType.TTS_AUDIO_CHUNK,
        RobotMessageType.TTS_AUDIO_DONE,
    ]
    assert responses[0].payload["text"] == "收到，我来回答。"
    assert responses[1].payload["codec"] == "mp3"
    assert responses[1].payload["chunk_b64"] == "bXAzLWJ5dGVz"
    assert tts.requests == [("收到，我来回答。", "female-shaonv")]
```

Add a bounded error test:

```python
async def test_audio_chunk_without_start_returns_error() -> None:
    service = VoiceMediaService(stt_provider=FakeStt(), tts_provider=FakeTts(), responder=fake_responder)
    chunk = build_envelope(
        message_type=RobotMessageType.AUDIO_CHUNK,
        device_id="pi-lab-01",
        session_id="missing",
        payload={"codec": "wav", "sample_rate_hz": 16000, "sequence": 1, "chunk_b64": "QUJD"},
    )

    responses = await service.handle(chunk)

    assert len(responses) == 1
    assert responses[0].type == RobotMessageType.ERROR
    assert responses[0].payload["code"] == "audio_session_missing"
```

- [ ] **Step 2: Run tests to verify RED**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\unit\voice\test_media.py -q -p no:cacheprovider`

Expected: import failure for `agent_hub.voice.media`.

- [ ] **Step 3: Implement `media.py`**

Create focused dataclasses/protocols and implement buffering:

```python
@dataclass(frozen=True)
class VoiceAudio:
    codec: str
    sample_rate_hz: int
    data: bytes
    language: str | None = None

@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    confidence: float | None = None

@dataclass(frozen=True)
class VoiceSynthesisOptions:
    voice_id: str | None
    model: str = "speech-2.8-turbo"
    audio_format: str = "mp3"

@dataclass(frozen=True)
class SynthesizedAudio:
    codec: str
    data: bytes
    sample_rate_hz: int | None = None
```

`VoiceMediaService.handle()` must:

- Store audio metadata on `audio.start`.
- Decode and append chunks on `audio.chunk`.
- On `audio.end`, call STT, build final `speech.partial` with `is_final=true`, call the injected responder, synthesize the first `assistant.text.done` response text, append `tts.audio.chunk` and `tts.audio.done`, and clear the buffer.
- Return `error` envelope instead of raising for expected audio session errors.

- [ ] **Step 4: Wire gateway**

Modify `create_robot_voice_router(...)` to accept `media_service: VoiceMediaService | None = None`. In the WebSocket loop:

```python
if active_media_service is not None and envelope.type in {
    RobotMessageType.AUDIO_START,
    RobotMessageType.AUDIO_CHUNK,
    RobotMessageType.AUDIO_END,
}:
    responses = await active_media_service.handle(envelope)
else:
    responses = await active_registry.record_async(envelope)
```

Send every response as before.

- [ ] **Step 5: Add API gateway regression**

Add to `tests/api/test_robot_voice_gateway.py` a test that injects fake media service into `create_robot_voice_router` or app state and verifies `audio.start/chunk/end` over WebSocket produces `assistant.text.done`, `tts.audio.chunk`, and `tts.audio.done`.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\unit\voice\test_media.py tests\api\test_robot_voice_gateway.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/voice/media.py src/agent_hub/voice/gateway.py tests/unit/voice/test_media.py tests/api/test_robot_voice_gateway.py
git commit -m "feat: add robot voice media service"
```

---

### Task 2: Pi `voice-once` Recording And Playback

**Files:**
- Create: `cube-robot-runtime/cube_robot_runtime/audio/capture.py`
- Create: `cube-robot-runtime/cube_robot_runtime/voice_once.py`
- Modify: `cube-robot-runtime/cube_robot_runtime/main.py`
- Modify: `cube-robot-runtime/config/robot.toml.example`
- Test: `cube-robot-runtime/tests/test_voice_once.py`
- Test: `tests/unit/install/test_pi_runtime_assets.py`

**Interfaces:**
- Consumes: `cube_robot_runtime.network.client.open_connection`, `RobotEnvelope`, `RuntimeConfig`.
- Produces:
  - `AudioConfig(record_command: str, play_command: str, sample_rate_hz: int, channels: int, audio_format: str)`
  - `VoiceConfig(tts_voice_id: str | None, tts_model: str)`
  - `run_voice_once(runtime: RuntimeConfig, audio: AudioConfig, voice: VoiceConfig, seconds: int) -> VoiceOnceResult`

- [ ] **Step 1: Write failing Pi tests**

Create `cube-robot-runtime/tests/test_voice_once.py`:

```python
from pathlib import Path

from cube_robot_runtime.main import RuntimeConfig
from cube_robot_runtime.protocol.messages import RobotEnvelope
from cube_robot_runtime.voice_once import AudioConfig, VoiceConfig, run_voice_once


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[RobotEnvelope] = []
        self.received = [
            RobotEnvelope.new(
                message_type="assistant.text.done",
                device_id="pi-lab-01",
                session_id="voice-once-session",
                payload={"text": "你好，我听到了。"},
            ),
            RobotEnvelope.new(
                message_type="tts.audio.chunk",
                device_id="pi-lab-01",
                session_id="voice-once-session",
                payload={"codec": "wav", "sequence": 1, "chunk_b64": "UklGRg=="},
            ),
            RobotEnvelope.new(
                message_type="tts.audio.done",
                device_id="pi-lab-01",
                session_id="voice-once-session",
                payload={"codec": "wav", "total_chunks": 1},
            ),
        ]

    def send(self, envelope: RobotEnvelope) -> None:
        self.sent.append(envelope)

    def receive(self) -> RobotEnvelope:
        return self.received.pop(0)

    def close(self) -> None:
        return None


def test_voice_once_records_sends_audio_and_plays_tts(tmp_path, monkeypatch) -> None:
    recorded = tmp_path / "input.wav"
    played: list[Path] = []
    connection = FakeConnection()

    def fake_record(config, seconds, output_path):
        output_path.write_bytes(b"recorded-wav")
        return output_path

    def fake_play(config, input_path):
        played.append(input_path)

    monkeypatch.setattr("cube_robot_runtime.voice_once.record_audio", fake_record)
    monkeypatch.setattr("cube_robot_runtime.voice_once.play_audio", fake_play)
    monkeypatch.setattr("cube_robot_runtime.voice_once.open_connection", lambda *args, **kwargs: connection)

    result = run_voice_once(
        RuntimeConfig(
            server_url="ws://server/api/v1/robot/ws/pi-lab-01",
            device_id="pi-lab-01",
            session_id="voice-once-session",
            device_token="robot-token",
        ),
        AudioConfig(record_command="arecord", play_command="aplay", sample_rate_hz=16000, channels=1, audio_format="wav"),
        VoiceConfig(tts_voice_id="female-shaonv", tts_model="speech-2.8-turbo"),
        seconds=5,
    )

    assert [message.type for message in connection.sent] == ["audio.start", "audio.chunk", "audio.end"]
    assert connection.sent[0].payload["voice_id"] == "female-shaonv"
    assert connection.sent[1].payload["chunk_b64"] == "cmVjb3JkZWQtd2F2"
    assert result.assistant_text == "你好，我听到了。"
    assert played
```

- [ ] **Step 2: Run tests to verify RED**

Run: `$env:PYTHONPATH='cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest cube-robot-runtime\tests\test_voice_once.py -q -p no:cacheprovider`

Expected: import failure for `cube_robot_runtime.voice_once`.

- [ ] **Step 3: Implement audio command helpers**

`capture.py` should call `subprocess.run()` with argument lists, not shell strings:

```python
def record_audio(config: AudioConfig, seconds: int, output_path: Path) -> Path:
    command = [
        config.record_command,
        "-q",
        "-d",
        str(seconds),
        "-r",
        str(config.sample_rate_hz),
        "-c",
        str(config.channels),
        "-f",
        "S16_LE",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path
```

`play_audio()` should call `[config.play_command, str(input_path)]`.

- [ ] **Step 4: Implement `voice_once.py`**

Implement `run_voice_once()` with temporary files:

- Record to temp WAV.
- Read bytes and send one chunk for first version.
- Receive until `tts.audio.done`.
- Save returned TTS bytes to a temp file with codec suffix.
- Call `play_audio()`.
- Return `VoiceOnceResult(sent_types, assistant_text, played_audio_path)`.

- [ ] **Step 5: Add CLI and config parsing**

Extend `load_runtime_config()` to parse `[audio]` and `[voice]` through new helpers or a new `load_device_config()` while keeping existing dry-run compatible. Add:

```bash
cube-robot voice-once --config /etc/cube-robot/robot.toml --seconds 5
```

- [ ] **Step 6: Update config example and isolation test**

Add `[audio]` and `[voice]` sections to `cube-robot-runtime/config/robot.toml.example`. Extend `tests/unit/install/test_pi_runtime_assets.py` to assert `voice-once`, `arecord`, `aplay`, and `tts_voice_id` are documented in runtime assets.

- [ ] **Step 7: Verify GREEN**

Run:

```powershell
$env:PYTHONPATH='cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest cube-robot-runtime\tests\test_voice_once.py cube-robot-runtime\tests\test_runtime_dry_run.py -q -p no:cacheprovider
$env:PYTHONPATH='src;cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest tests\unit\install\test_pi_runtime_assets.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add cube-robot-runtime/cube_robot_runtime/audio/capture.py cube-robot-runtime/cube_robot_runtime/voice_once.py cube-robot-runtime/cube_robot_runtime/main.py cube-robot-runtime/config/robot.toml.example cube-robot-runtime/tests/test_voice_once.py tests/unit/install/test_pi_runtime_assets.py
git commit -m "feat: add pi voice once loop"
```

---

### Task 3: MiniMax Speech Providers

**Files:**
- Create: `src/agent_hub/voice/minimax.py`
- Modify: `src/agent_hub/settings.py`
- Modify: `src/agent_hub/app.py`
- Test: `tests/unit/voice/test_minimax.py`
- Test: `tests/unit/test_app_wiring.py`

**Interfaces:**
- Consumes: `VoiceAudio`, `VoiceSynthesisOptions`, `SynthesizedAudio`, `SpeechTranscript`, `VoiceCloneRequest`, `VoiceCloneResult`.
- Produces:
  - `MiniMaxSpeechClient`
  - `MiniMaxSpeechToTextProvider`
  - `MiniMaxTextToSpeechProvider`
  - `MiniMaxVoiceCloneProvider`

- [ ] **Step 1: Write failing MiniMax tests**

Create `tests/unit/voice/test_minimax.py`:

```python
from agent_hub.voice.media import VoiceSynthesisOptions
from agent_hub.voice.minimax import MiniMaxSpeechClient, MiniMaxTextToSpeechProvider


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        return {
            "data": {"audio": "52494646", "status": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }


async def test_minimax_tts_builds_t2a_payload_and_decodes_hex_audio() -> None:
    transport = FakeTransport()
    client = MiniMaxSpeechClient(api_key="test-key", transport=transport)
    provider = MiniMaxTextToSpeechProvider(client)

    audio = await provider.synthesize(
        "你好，我是机器人。",
        VoiceSynthesisOptions(voice_id="female-shaonv", model="speech-2.8-turbo", audio_format="mp3"),
    )

    assert audio.codec == "mp3"
    assert audio.data == b"RIFF"
    url, headers, payload, timeout = transport.calls[0]
    assert url == "https://api.minimax.io/v1/t2a_v2"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "speech-2.8-turbo"
    assert payload["text"] == "你好，我是机器人。"
    assert payload["stream"] is False
    assert payload["voice_setting"]["voice_id"] == "female-shaonv"
    assert payload["audio_setting"]["format"] == "mp3"
```

Add clone validation test:

```python
from pathlib import Path

import pytest

from agent_hub.voice.minimax import MiniMaxVoiceCloneProvider, VoiceCloneRequest


async def test_voice_clone_requires_consent_before_upload(tmp_path: Path) -> None:
    provider = MiniMaxVoiceCloneProvider(MiniMaxSpeechClient(api_key="test-key", transport=FakeTransport()))
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"wav")

    with pytest.raises(ValueError, match="consent"):
        await provider.clone_voice(
            VoiceCloneRequest(
                audio_path=sample,
                voice_id="RobotVoice01",
                owner="local-user",
                consent_confirmed=False,
            )
        )
```

- [ ] **Step 2: Run tests to verify RED**

Run: `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\unit\voice\test_minimax.py -q -p no:cacheprovider`

Expected: import failure for `agent_hub.voice.minimax`.

- [ ] **Step 3: Implement MiniMax client**

Implement:

- `MiniMaxHTTPTransport.post_json(...)`
- `MiniMaxHTTPTransport.post_multipart(...)`
- `MiniMaxSpeechClient(api_key, base_url="https://api.minimax.io", timeout_seconds=30.0, transport=None)`
- `MiniMaxTextToSpeechProvider.synthesize(...)`
- `MiniMaxVoiceCloneProvider.clone_voice(...)`

Use the official T2A shape:

```python
{
    "model": options.model,
    "text": bounded_text,
    "stream": False,
    "language_boost": "auto",
    "output_format": "hex",
    "voice_setting": {"voice_id": options.voice_id or default_voice_id, "speed": 1, "vol": 1, "pitch": 0},
    "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": options.audio_format, "channel": 1},
}
```

Decode `response["data"]["audio"]` with `bytes.fromhex(...)`.

- [ ] **Step 4: Implement STT provider behind same client**

Use MiniMax Speech to Text API path from docs/OpenAPI. The provider must accept `VoiceAudio`, upload or submit audio as required by MiniMax docs, and return `SpeechTranscript`. If the exact response contains multiple transcript fields, prefer the final full text field and keep provider parsing covered by fixtures.

- [ ] **Step 5: Add settings and app wiring**

Add server settings:

- `minimax_api_key: SecretStr | None`
- `minimax_base_url: str = "https://api.minimax.io"`
- `robot_tts_provider: str = "mock"`
- `robot_tts_voice_id: str = "female-shaonv"`
- `robot_tts_model: str = "speech-2.8-turbo"`

Wire `app.py` so MiniMax media service is created only when provider is configured and key exists. Otherwise keep text-only behavior.

- [ ] **Step 6: Verify GREEN**

Run:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\unit\voice\test_minimax.py tests\unit\voice\test_media.py tests\unit\test_app_wiring.py -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/agent_hub/voice/minimax.py src/agent_hub/settings.py src/agent_hub/app.py tests/unit/voice/test_minimax.py tests/unit/test_app_wiring.py
git commit -m "feat: add minimax speech providers"
```

---

### Task 4: Docs, Probe, Deployment, And Field Validation

**Files:**
- Modify: `docs/robot-system-manual.md`
- Modify: `docs/robot-field-test.md`
- Modify: `tools/robot_voice_probe.py`
- Test: `tests/unit/install/test_pi_runtime_assets.py`

**Interfaces:**
- Consumes: Pi `voice-once`, server `MINIMAX_API_KEY`, existing robot probe.
- Produces: documented MiniMax setup and a repeatable field-test path.

- [ ] **Step 1: Write docs asset test**

Extend `tests/unit/install/test_pi_runtime_assets.py` with assertions that:

- `docs/robot-system-manual.md` mentions `MINIMAX_API_KEY`.
- It states the key is server-side only.
- It documents `cube-robot voice-once`.
- It documents `[voice] tts_voice_id`.

- [ ] **Step 2: Run test to verify RED**

Run: `$env:PYTHONPATH='src;cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest tests\unit\install\test_pi_runtime_assets.py -q -p no:cacheprovider`

Expected: fail until docs are updated.

- [ ] **Step 3: Update manuals**

Update `docs/robot-system-manual.md`:

- Server `/etc/agent-hub/secrets.env`:
  ```bash
  MINIMAX_API_KEY=...
  AGENT_HUB_ROBOT_TTS_PROVIDER=minimax
  AGENT_HUB_ROBOT_TTS_VOICE_ID=female-shaonv
  AGENT_HUB_ROBOT_TTS_MODEL=speech-2.8-turbo
  ```
- Pi config:
  ```toml
  [voice]
  tts_voice_id = "female-shaonv"
  tts_model = "speech-2.8-turbo"
  ```
- Field command:
  ```bash
  sudo /usr/local/lib/cube-robot/.venv/bin/cube-robot voice-once --config /etc/cube-robot/robot.toml --seconds 5
  ```
- Voice clone consent and privacy rules.

Update `docs/robot-field-test.md` with a `voice-once` checklist.

- [ ] **Step 4: Update probe if useful**

If `tools/robot_voice_probe.py` remains text-only, document it as text probe. Do not make it require MiniMax or hardware.

- [ ] **Step 5: Verify**

Run:

```powershell
$env:PYTHONPATH='src;cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest tests\unit\install\test_pi_runtime_assets.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check --no-cache src tests cube-robot-runtime tools --exclude cube-robot-runtime/scripts
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Deploy and field-test**

Deploy runtime-affecting server changes to `prod-web-02`:

- Create release from `HEAD`.
- Copy existing `.venv` and web assets.
- Switch `/opt/agent-hub/current`.
- Restart `agent-hub-api` and `agent-hub-worker`.
- Reload Caddy.
- Remove temp package and prune old releases while preserving current and recent rollback releases.

Verify:

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

From Windows:

```powershell
curl.exe --noproxy * -sS -o NUL -w "http_code=%{http_code} content_type=%{content_type}\n" http://103.236.93.62:32020/login
```

On Pi:

```bash
sudo /usr/local/lib/cube-robot/.venv/bin/cube-robot voice-once --config /etc/cube-robot/robot.toml --seconds 5
```

- [ ] **Step 7: Commit**

```bash
git add docs/robot-system-manual.md docs/robot-field-test.md tools/robot_voice_probe.py tests/unit/install/test_pi_runtime_assets.py
git commit -m "docs: add robot voice media runbook"
```

---

## Final Verification

Run:

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests\unit\voice tests\api\test_robot_voice_gateway.py tests\unit\robot -q -p no:cacheprovider
$env:PYTHONPATH='cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest cube-robot-runtime\tests -q -p no:cacheprovider
$env:PYTHONPATH='src;cube-robot-runtime'; .\.venv\Scripts\python.exe -m pytest tests\unit\install\test_pi_runtime_assets.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check --no-cache src tests cube-robot-runtime tools --exclude cube-robot-runtime/scripts
git diff --check
```

Deploy to `prod-web-02`, run server health checks, run text robot probe, and run Pi `voice-once`.

Push to GitHub and check commit statuses/workflow runs. If checks fail, fetch details, fix, verify, commit, push again.

## Self-Review

- Spec coverage: Tasks cover server media service, Pi single-turn loop, MiniMax provider/voice clone interfaces, documentation, deployment, and field validation.
- Placeholder scan: No `TBD` or unspecified error handling remains; provider parsing for MiniMax STT is intentionally tied to docs/OpenAPI in Task 3.
- Type consistency: `VoiceAudio`, `SpeechTranscript`, `VoiceSynthesisOptions`, `SynthesizedAudio`, `VoiceMediaService`, `AudioConfig`, `VoiceConfig`, and `run_voice_once` are consistently named across tasks.

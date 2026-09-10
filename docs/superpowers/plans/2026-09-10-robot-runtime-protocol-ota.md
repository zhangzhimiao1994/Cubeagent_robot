# Robot Runtime Protocol OTA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first isolated voice robot runtime slice: a server-side Robot Protocol v1 contract and gateway, plus a separate Raspberry Pi runtime package with dry-run connection, provisioning, and OTA foundations.

**Architecture:** Server code stays under `src/agent_hub/robot/` and `src/agent_hub/voice/`; Raspberry Pi code stays under top-level `cube-robot-runtime/` with its own package metadata and tests. The Pi runtime must not import `agent_hub`, `cognition`, Hermes, Memory, DB models, or server internals; both sides communicate only through Robot Protocol v1 JSON envelopes and published schema files.

**Tech Stack:** Python 3.12 for server; Python 3.11+ compatible isolated Pi runtime; FastAPI/WebSocket on the server; standard-library-first Pi runtime with optional `websockets` dependency; pytest; ruff.

**Spec:** `docs/superpowers/specs/2026-09-10-long-term-companion-robot-v2-design.md`

## Global Constraints

- Local project root is `E:\code_x\cubeagent_robot`.
- GitHub repository is `https://github.com/zhangzhimiao1994/Cubeagent_robot`.
- Production/debug host is `prod-web-02`; Web debug URL is `http://<prod-web-02-ip>:32020/login`; do not use a proxy for that URL.
- Preserve Hermes, Memory, Skill, authentication, model configuration, run history, settings, database migrations, security, observability, Docker/native deployment foundations.
- Raspberry Pi is not the Agent Brain. It is a device runtime for audio capture, playback, display/status, reconnect, local safety, provisioning, and OTA.
- Pi runtime code must be isolated in `cube-robot-runtime/` and must not import `src/agent_hub`, `agent_hub.cognition`, Hermes, Memory, SQLAlchemy models, or server runtime code.
- Shared behavior between server and Pi must be expressed through Robot Protocol v1 JSON messages and generated/published schema files, not through shared Python implementation imports.
- Robot Protocol v1 envelopes include `protocol_version`, `message_id`, `session_id`, `device_id`, `timestamp`, `type`, and `payload`.
- Phase 1 must support a hardware-free dry-run path: simulated utterance or status from the Pi runtime reaches a mock/server gateway, returns assistant text or playback command, and records status.
- Runtime-affecting changes must be deployed to `prod-web-02` and receive a real feature probe before GitHub push.
- Target-machine old temporary deployment packages, stale build archives, obsolete extracted release directories, stale cache directories, and other clearly disposable files may be cleaned without asking; do not remove databases, uploads, secrets, current release pointers, active volumes, active runtime data, or unclear files.

---

## File Structure

- `src/agent_hub/robot/protocol.py`: server-side Robot Protocol v1 Pydantic message contracts, payload types, validation helpers, and JSON Schema export.
- `src/agent_hub/robot/session.py`: server-side in-memory device/session state for MVP heartbeat and mock utterance handling.
- `src/agent_hub/robot/ota.py`: server-side OTA manifest models and compatibility/checksum validation helpers.
- `src/agent_hub/voice/gateway.py`: FastAPI router for robot WebSocket, device status, mock voice utterance, and OTA manifest endpoints.
- `src/agent_hub/voice/companion.py`: small server bridge that turns text utterances into a companion response through a pluggable responder; MVP default is deterministic for tests and mock Pi.
- `cube-robot-runtime/pyproject.toml`: isolated Pi runtime package metadata and dependencies.
- `cube-robot-runtime/cube_robot_runtime/protocol/messages.py`: Pi-side dataclass/stdlib message envelope validator mirroring the JSON contract without importing server code.
- `cube-robot-runtime/cube_robot_runtime/network/client.py`: reconnecting WebSocket client interface and dry-run mock loop.
- `cube-robot-runtime/cube_robot_runtime/audio/playback.py`: dry-run playback abstraction with command recording; later replaceable with ALSA/PulseAudio implementation.
- `cube-robot-runtime/cube_robot_runtime/device/identity.py`: local identity/config loading that preserves device token and runtime config outside OTA release directories.
- `cube-robot-runtime/cube_robot_runtime/ota/updater.py`: OTA metadata validation, checksum verification, staged release selection, rollback pointer logic.
- `cube-robot-runtime/cube_robot_runtime/main.py`: CLI entry point for dry-run connect, heartbeat, simulated utterance, and updater check.
- `cube-robot-runtime/config/robot.toml.example`: Pi runtime config template.
- `cube-robot-runtime/scripts/cube-robot.service`: systemd unit template for the Pi runtime.
- `cube-robot-runtime/scripts/cube-robot-updater.service`: systemd oneshot OTA checker.
- `cube-robot-runtime/scripts/cube-robot-updater.timer`: systemd timer.
- `cube-robot-runtime/scripts/first-boot-register.sh`: idempotent provisioning script with `--dry-run`.
- `cube-robot-runtime/scripts/ota-update.sh`: wrapper for updater check/install with `--dry-run`.
- `tests/unit/robot/test_protocol.py`: server protocol schema and validation tests.
- `tests/unit/robot/test_session.py`: server session heartbeat/mock utterance tests.
- `tests/unit/robot/test_ota.py`: server OTA manifest validation tests.
- `tests/api/test_robot_voice_gateway.py`: FastAPI REST/WebSocket robot gateway tests.
- `cube-robot-runtime/tests/test_protocol_messages.py`: Pi protocol contract tests.
- `cube-robot-runtime/tests/test_runtime_dry_run.py`: Pi dry-run loop tests.
- `cube-robot-runtime/tests/test_ota_updater.py`: Pi OTA verification and rollback tests.
- `tests/unit/install/test_pi_runtime_assets.py`: repository-level checks for Pi scripts, systemd units, dry-run flags, and isolation contract.
- `HANDOFF.md`: local-only current-state update after durable verification/deploy results.

### Task 1: Robot Protocol v1 And OTA Contracts

**Files:**
- Create: `src/agent_hub/robot/__init__.py`
- Create: `src/agent_hub/robot/protocol.py`
- Create: `src/agent_hub/robot/ota.py`
- Test: `tests/unit/robot/test_protocol.py`
- Test: `tests/unit/robot/test_ota.py`

**Interfaces:**
- Produces: `RobotEnvelope.model_validate_json(raw: str) -> RobotEnvelope`
- Produces: `build_envelope(*, message_type: RobotMessageType | str, device_id: str, session_id: str, payload: Mapping[str, object], timestamp: datetime | None = None) -> RobotEnvelope`
- Produces: `export_robot_protocol_schema() -> dict[str, object]`
- Produces: `OtaManifest`, `OtaArtifact`, and `validate_manifest_for_device(manifest: OtaManifest, *, protocol_version: str, current_version: str) -> OtaDecision`

- [ ] **Step 1: Write failing protocol tests**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_hub.robot.protocol import (
    ROBOT_PROTOCOL_VERSION,
    AudioChunkPayload,
    RobotEnvelope,
    RobotMessageType,
    build_envelope,
    export_robot_protocol_schema,
)


def test_robot_envelope_requires_v1_contract_fields() -> None:
    envelope = build_envelope(
        message_type=RobotMessageType.DEVICE_HEARTBEAT,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"battery": 82, "network_rssi": -55},
        timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    )

    assert envelope.protocol_version == ROBOT_PROTOCOL_VERSION
    assert envelope.device_id == "pi-lab-01"
    assert envelope.session_id == "voice-session-1"
    assert envelope.type is RobotMessageType.DEVICE_HEARTBEAT
    assert envelope.payload["battery"] == 82


def test_robot_envelope_rejects_unknown_message_type() -> None:
    with pytest.raises(ValidationError):
        RobotEnvelope.model_validate(
            {
                "protocol_version": "1",
                "message_id": "msg-1",
                "session_id": "voice-session-1",
                "device_id": "pi-lab-01",
                "timestamp": "2026-09-10T12:00:00Z",
                "type": "unknown.kind",
                "payload": {},
            }
        )


def test_audio_chunk_payload_bounds_sequence_and_base64() -> None:
    payload = AudioChunkPayload(codec="pcm16", sample_rate_hz=16000, sequence=1, chunk_b64="AQID")
    assert payload.codec == "pcm16"
    assert payload.sample_rate_hz == 16000
    with pytest.raises(ValidationError):
        AudioChunkPayload(codec="pcm16", sample_rate_hz=16000, sequence=0, chunk_b64="not base64!!")


def test_protocol_schema_exports_envelope_and_message_types() -> None:
    schema = export_robot_protocol_schema()
    assert schema["protocol_version"] == ROBOT_PROTOCOL_VERSION
    assert "device.heartbeat" in schema["message_types"]
    assert "tts.audio.chunk" in schema["message_types"]
```

- [ ] **Step 2: Write failing OTA tests**

```python
from agent_hub.robot.ota import OtaArtifact, OtaManifest, OtaStatus, validate_manifest_for_device


def test_ota_manifest_accepts_compatible_stable_update() -> None:
    manifest = OtaManifest(
        version="2026.09.10+001",
        channel="stable",
        min_protocol_version="1",
        artifact=OtaArtifact(
            url="https://updates.example.com/cube-robot-runtime-2026.09.10.tgz",
            sha256="a" * 64,
            size_bytes=12345,
        ),
        signature="sig-test",
        rollback_version="2026.09.01+001",
    )

    decision = validate_manifest_for_device(
        manifest,
        protocol_version="1",
        current_version="2026.09.01+001",
    )

    assert decision.status is OtaStatus.UPDATE_AVAILABLE
    assert decision.target_version == "2026.09.10+001"


def test_ota_manifest_rejects_incompatible_protocol() -> None:
    manifest = OtaManifest(
        version="2026.09.10+001",
        channel="stable",
        min_protocol_version="2",
        artifact=OtaArtifact(url="https://updates.example.com/runtime.tgz", sha256="b" * 64, size_bytes=1),
        signature="sig-test",
    )

    decision = validate_manifest_for_device(manifest, protocol_version="1", current_version="2026.09.01+001")

    assert decision.status is OtaStatus.INCOMPATIBLE
    assert "protocol" in decision.reason
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/robot/test_protocol.py tests/unit/robot/test_ota.py -q`

Expected: import failures for `agent_hub.robot.protocol` and `agent_hub.robot.ota`.

- [ ] **Step 4: Implement minimal contracts**

Implement strict Pydantic models. Message types must include at least `device.register`, `device.heartbeat`, `device.status`, `audio.start`, `audio.chunk`, `audio.end`, `speech.partial`, `interaction.event`, `playback.started`, `playback.finished`, `playback.interrupted`, `screen.event`, `button.event`, `session.accepted`, `assistant.text.delta`, `assistant.text.done`, `tts.audio.chunk`, `tts.audio.done`, `avatar.state`, `screen.show`, `device.command`, `playback.stop`, `conversation.end`, and `error`.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/robot/test_protocol.py tests/unit/robot/test_ota.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agent_hub/robot tests/unit/robot/test_protocol.py tests/unit/robot/test_ota.py
git commit -m "feat: add robot protocol contracts"
```

### Task 2: Server Voice Gateway MVP

**Files:**
- Create: `src/agent_hub/robot/session.py`
- Create: `src/agent_hub/voice/__init__.py`
- Create: `src/agent_hub/voice/companion.py`
- Create: `src/agent_hub/voice/gateway.py`
- Modify: `src/agent_hub/app.py`
- Test: `tests/unit/robot/test_session.py`
- Test: `tests/api/test_robot_voice_gateway.py`

**Interfaces:**
- Consumes: `RobotEnvelope`, `RobotMessageType`, `build_envelope`, `OtaManifest`
- Produces: `RobotSessionRegistry.record(envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]`
- Produces: `RobotSessionRegistry.status(device_id: str | None = None) -> RobotStatusSnapshot`
- Produces: `CompanionResponder.respond_text(utterance: str, *, device_id: str, session_id: str) -> str`
- Produces: `create_robot_voice_router(registry: RobotSessionRegistry | None = None, responder: CompanionResponder | None = None) -> APIRouter`

- [ ] **Step 1: Write failing session tests**

```python
from datetime import UTC, datetime

from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.robot.session import RobotSessionRegistry, RobotSessionState


def test_registry_accepts_heartbeat_and_reports_online_status() -> None:
    registry = RobotSessionRegistry(clock=lambda: datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    response = registry.record(build_envelope(
        message_type=RobotMessageType.DEVICE_HEARTBEAT,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"runtime_version": "0.1.0", "latency_ms": 18},
    ))

    snapshot = registry.status("pi-lab-01")

    assert response == ()
    assert snapshot.devices[0].device_id == "pi-lab-01"
    assert snapshot.devices[0].state is RobotSessionState.IDLE
    assert snapshot.devices[0].runtime_version == "0.1.0"


def test_registry_turns_speech_partial_into_assistant_text_done() -> None:
    registry = RobotSessionRegistry()
    response = registry.record(build_envelope(
        message_type=RobotMessageType.SPEECH_PARTIAL,
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"text": "你好", "is_final": True},
    ))

    assert [item.type for item in response] == [RobotMessageType.ASSISTANT_TEXT_DONE, RobotMessageType.CONVERSATION_END]
    assert "你好" in str(response[0].payload["text"])
```

- [ ] **Step 2: Write failing API/WebSocket tests**

```python
from fastapi.testclient import TestClient

from agent_hub.app import create_app
from agent_hub.robot.protocol import RobotMessageType, build_envelope


def test_robot_status_endpoint_uses_runtime_registry() -> None:
    app = create_app(
        database_probe=lambda: None,
        redis_probe=lambda: None,
        session_factory=None,
        run_service=None,
    )
    client = TestClient(app)
    response = client.get("/api/v1/robot/devices")
    assert response.status_code == 200
    assert response.json()["devices"] == []


def test_robot_websocket_accepts_heartbeat_and_final_utterance() -> None:
    app = create_app(
        database_probe=lambda: None,
        redis_probe=lambda: None,
        session_factory=None,
        run_service=None,
    )
    client = TestClient(app)
    with client.websocket_connect("/api/v1/robot/ws/pi-lab-01") as ws:
        ws.send_json(build_envelope(
            message_type=RobotMessageType.DEVICE_HEARTBEAT,
            device_id="pi-lab-01",
            session_id="voice-session-1",
            payload={"runtime_version": "0.1.0"},
        ).model_dump(mode="json"))
        ws.send_json(build_envelope(
            message_type=RobotMessageType.SPEECH_PARTIAL,
            device_id="pi-lab-01",
            session_id="voice-session-1",
            payload={"text": "测试语音", "is_final": True},
        ).model_dump(mode="json"))
        message = ws.receive_json()
    assert message["type"] == "assistant.text.done"
    assert "测试语音" in message["payload"]["text"]
```

- [ ] **Step 3: Run tests to verify fail**

Run: `pytest tests/unit/robot/test_session.py tests/api/test_robot_voice_gateway.py -q`

Expected: missing modules/routes.

- [ ] **Step 4: Implement registry, companion responder, and router**

Keep this as an MVP bridge. The default responder may be deterministic: `我听到了：{utterance}`. It must be injectable so later tasks can call `RunService`/Direct/Hermes without changing the Pi protocol. `src/agent_hub/app.py` must instantiate `application.state.robot_session_registry` and mount `create_robot_voice_router().routes` before the catch-all Web UI route.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/robot/test_session.py tests/api/test_robot_voice_gateway.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/agent_hub/robot/session.py src/agent_hub/voice src/agent_hub/app.py tests/unit/robot/test_session.py tests/api/test_robot_voice_gateway.py
git commit -m "feat: add robot voice gateway"
```

### Task 3: Isolated Raspberry Pi Runtime Dry Run

**Files:**
- Create: `cube-robot-runtime/pyproject.toml`
- Create: `cube-robot-runtime/cube_robot_runtime/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/protocol/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/protocol/messages.py`
- Create: `cube-robot-runtime/cube_robot_runtime/network/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/network/client.py`
- Create: `cube-robot-runtime/cube_robot_runtime/audio/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/audio/playback.py`
- Create: `cube-robot-runtime/cube_robot_runtime/device/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/device/identity.py`
- Create: `cube-robot-runtime/cube_robot_runtime/main.py`
- Test: `cube-robot-runtime/tests/test_protocol_messages.py`
- Test: `cube-robot-runtime/tests/test_runtime_dry_run.py`
- Test: `tests/unit/install/test_pi_runtime_assets.py`

**Interfaces:**
- Consumes: Robot Protocol v1 envelope field names and message type strings.
- Produces: `cube_robot_runtime.protocol.messages.RobotEnvelope`
- Produces: `cube_robot_runtime.main.run_dry_run(config: RuntimeConfig, utterance: str) -> DryRunResult`
- Produces: CLI `python -m cube_robot_runtime.main dry-run --server-url ws://127.0.0.1:8000/api/v1/robot/ws/pi-lab-01 --device-id pi-lab-01 --utterance 你好`

- [ ] **Step 1: Write failing Pi runtime tests**

```python
from cube_robot_runtime.main import RuntimeConfig, run_dry_run
from cube_robot_runtime.protocol.messages import RobotEnvelope


def test_pi_protocol_has_no_agent_hub_dependency() -> None:
    import cube_robot_runtime.protocol.messages as messages

    assert "agent_hub" not in messages.__file__


def test_pi_envelope_round_trip_stdlib_only() -> None:
    envelope = RobotEnvelope.new(
        message_type="device.heartbeat",
        device_id="pi-lab-01",
        session_id="voice-session-1",
        payload={"runtime_version": "0.1.0"},
    )

    parsed = RobotEnvelope.from_json(envelope.to_json())

    assert parsed.protocol_version == "1"
    assert parsed.type == "device.heartbeat"
    assert parsed.payload["runtime_version"] == "0.1.0"


def test_dry_run_sends_heartbeat_and_utterance_to_mock_connection() -> None:
    result = run_dry_run(
        RuntimeConfig(server_url="mock://robot", device_id="pi-lab-01", session_id="voice-session-1"),
        utterance="你好",
    )

    assert result.sent_types == ("device.heartbeat", "speech.partial")
    assert result.received_texts == ("我听到了：你好",)
```

- [ ] **Step 2: Write failing repository isolation test**

```python
from pathlib import Path


def test_pi_runtime_is_isolated_from_agent_hub_imports() -> None:
    root = Path("cube-robot-runtime")
    assert (root / "pyproject.toml").exists()
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "agent_hub" in text or "cognition" in text or "hermes" in text:
            offenders.append(str(path))
    assert offenders == []
```

- [ ] **Step 3: Run tests to verify fail**

Run: `$env:PYTHONPATH='cube-robot-runtime'; pytest cube-robot-runtime/tests/test_protocol_messages.py cube-robot-runtime/tests/test_runtime_dry_run.py tests/unit/install/test_pi_runtime_assets.py -q`

Expected: missing `cube-robot-runtime` files.

- [ ] **Step 4: Implement isolated dry-run runtime**

Use stdlib dataclasses/json for message envelopes and a mock connection for `mock://robot`. Do not import Pydantic or `agent_hub` in Pi runtime code. Keep audio playback as a simple recorder class for this task.

- [ ] **Step 5: Run tests to verify pass**

Run: `$env:PYTHONPATH='cube-robot-runtime'; pytest cube-robot-runtime/tests/test_protocol_messages.py cube-robot-runtime/tests/test_runtime_dry_run.py tests/unit/install/test_pi_runtime_assets.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add cube-robot-runtime tests/unit/install/test_pi_runtime_assets.py
git commit -m "feat: add isolated pi runtime dry run"
```

### Task 4: Raspberry Pi Provisioning And OTA Scripts

**Files:**
- Create: `cube-robot-runtime/config/robot.toml.example`
- Create: `cube-robot-runtime/cube_robot_runtime/ota/__init__.py`
- Create: `cube-robot-runtime/cube_robot_runtime/ota/updater.py`
- Create: `cube-robot-runtime/scripts/cube-robot.service`
- Create: `cube-robot-runtime/scripts/cube-robot-updater.service`
- Create: `cube-robot-runtime/scripts/cube-robot-updater.timer`
- Create: `cube-robot-runtime/scripts/first-boot-register.sh`
- Create: `cube-robot-runtime/scripts/ota-update.sh`
- Test: `cube-robot-runtime/tests/test_ota_updater.py`
- Modify: `tests/unit/install/test_pi_runtime_assets.py`

**Interfaces:**
- Consumes: `cube_robot_runtime.protocol.messages.RobotEnvelope`
- Produces: `cube_robot_runtime.ota.updater.UpdateManifest`
- Produces: `verify_artifact(path: Path, expected_sha256: str) -> bool`
- Produces: `select_release(current: Path, candidate: Path, previous: Path | None) -> ReleaseSwitch`
- Produces: scripts with `--dry-run` support.

- [ ] **Step 1: Write failing OTA updater tests**

```python
from pathlib import Path

from cube_robot_runtime.ota.updater import UpdateManifest, select_release, verify_artifact


def test_verify_artifact_matches_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "runtime.tgz"
    artifact.write_bytes(b"runtime")
    assert verify_artifact(artifact, "d92c6a81b2ff50096bcda80885427d1f59a25b5f483f7055523504925d16ab23") is True
    assert verify_artifact(artifact, "a" * 64) is False


def test_manifest_rejects_protocol_too_new() -> None:
    manifest = UpdateManifest.from_dict(
        {
            "version": "2026.09.10+001",
            "channel": "stable",
            "min_protocol_version": "2",
            "artifact": {"url": "https://updates.example.com/runtime.tgz", "sha256": "a" * 64, "size_bytes": 10},
            "signature": "sig-test",
        }
    )
    assert manifest.compatible_with(protocol_version="1") is False


def test_select_release_preserves_previous_for_rollback(tmp_path: Path) -> None:
    current = tmp_path / "current"
    candidate = tmp_path / "releases" / "2026.09.10"
    previous = tmp_path / "releases" / "2026.09.01"
    candidate.mkdir(parents=True)
    previous.mkdir(parents=True)

    switch = select_release(current=current, candidate=candidate, previous=previous)

    assert switch.current == current
    assert switch.next_release == candidate
    assert switch.rollback_release == previous
```

- [ ] **Step 2: Extend script asset tests**

Add assertions that `cube-robot.service`, updater service/timer, `first-boot-register.sh`, and `ota-update.sh` exist, contain `--dry-run`, and keep state under `/etc/cube-robot` and `/var/lib/cube-robot` rather than release directories.

- [ ] **Step 3: Run tests to verify fail**

Run: `$env:PYTHONPATH='cube-robot-runtime'; pytest cube-robot-runtime/tests/test_ota_updater.py tests/unit/install/test_pi_runtime_assets.py -q`

Expected: missing OTA updater/scripts.

- [ ] **Step 4: Implement OTA and provisioning assets**

Scripts must be idempotent and shellcheck-friendly. `first-boot-register.sh --dry-run` must print intended paths and avoid network writes. `ota-update.sh --dry-run` must call the Python updater in dry-run mode. Systemd units must run as a dedicated `cube-robot` user and use `/etc/cube-robot/robot.toml`.

- [ ] **Step 5: Run tests to verify pass**

Run: `$env:PYTHONPATH='cube-robot-runtime'; pytest cube-robot-runtime/tests/test_ota_updater.py tests/unit/install/test_pi_runtime_assets.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add cube-robot-runtime/config cube-robot-runtime/scripts cube-robot-runtime/cube_robot_runtime/ota cube-robot-runtime/tests/test_ota_updater.py tests/unit/install/test_pi_runtime_assets.py
git commit -m "feat: add pi provisioning and ota assets"
```

### Task 5: Verification, Deployment Probe, And Handoff

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: verified local branch and deployed server probe result.

- [ ] **Step 1: Run focused backend tests**

Run: `pytest tests/unit/robot tests/api/test_robot_voice_gateway.py tests/unit/install/test_pi_runtime_assets.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run focused Pi runtime tests**

Run from repo root: `$env:PYTHONPATH='cube-robot-runtime'; pytest cube-robot-runtime/tests -q`

Expected: all tests pass without hardware.

- [ ] **Step 3: Run quality checks**

Run: `ruff check --no-cache src tests cube-robot-runtime`

Expected: pass.

Run: `git diff --check`

Expected: pass.

- [ ] **Step 4: Run build-impact smoke**

Run: `pytest tests/unit/test_app_wiring.py tests/integration/system/test_readiness.py -q`

Expected: pass or document inherited Windows runner limitation if it hangs after pass output.

- [ ] **Step 5: Deploy server-side route to prod-web-02**

Deploy after cleaning only disposable target-machine stale packages/caches/release garbage per project rules. Do not remove DB, secrets, uploads, current release pointer, active volumes, or unclear files.

- [ ] **Step 6: Probe production without proxy**

Probe:
- `GET http://<prod-web-02-ip>:32020/login` returns 200.
- `GET http://<prod-web-02-ip>:32020/api/v1/robot/devices` returns 200 or the expected auth/device policy response.
- A WebSocket or HTTP mock utterance probe reaches the robot gateway and returns deterministic assistant text.

- [ ] **Step 7: Update local handoff**

Update `HANDOFF.md` with branch, commit, deployment release, verification summary, known limitations, and next work. Keep it concise and current.

- [ ] **Step 8: Commit handoff only if tracked**

`HANDOFF.md` is local-only in this project. Do not commit it if ignored.

- [ ] **Step 9: Push and check GitHub status**

Push `robot-runtime-protocol`, then inspect GitHub checks. If checks fail, fetch details, fix, verify locally, commit, push, and repeat until checks pass or a real external blocker is identified.

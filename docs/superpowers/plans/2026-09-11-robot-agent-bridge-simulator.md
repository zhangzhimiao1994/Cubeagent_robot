# Robot Agent Bridge Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect robot final speech to the existing Agent Harness path without requiring Raspberry Pi hardware, and add a repeatable simulator probe for the 2026-09-12 field test.

**Architecture:** Keep Raspberry Pi runtime isolated in `cube-robot-runtime/`; all cognition, Hermes, run submission, and result extraction stay in server-side `src/agent_hub/voice/`. The robot WebSocket receives only Robot Protocol v1 messages, delegates final utterances to a pluggable server bridge, and sends back assistant text when the run completes or a bounded fallback when the run cannot produce a reply.

**Tech Stack:** Python 3.12 server, FastAPI/WebSocket, existing `RunService`/repository contracts, pytest, ruff, stdlib simulator entry points.

**Spec:** `docs/superpowers/specs/2026-09-10-long-term-companion-robot-v2-design.md`

## Global Constraints

- Local project root is `E:\code_x\cubeagent_robot`.
- GitHub repository is `https://github.com/zhangzhimiao1994/Cubeagent_robot`.
- Production/debug host is `prod-web-02`; Web debug URL is `http://103.236.93.62:32020/login`; do not use a proxy for that URL.
- Runtime-affecting changes must be deployed to `prod-web-02` and receive a real feature probe before GitHub push.
- Target-machine old temporary deployment packages, stale build archives, obsolete extracted release directories, stale cache directories, and other clearly disposable files may be cleaned without asking; do not remove databases, uploads, secrets, current release pointers, active volumes, active runtime data, or unclear files.
- Raspberry Pi is not the Agent Brain. It is a device runtime for audio capture, playback, display/status, reconnect, local safety, provisioning, and OTA.
- Pi runtime code must be isolated in `cube-robot-runtime/` and must not import `src/agent_hub`, `agent_hub.cognition`, Hermes, Memory, SQLAlchemy models, or server runtime code.
- Shared behavior between server and Pi must be expressed through Robot Protocol v1 JSON messages and published schema files, not through shared Python implementation imports.
- Server cognition/Hermes failures must degrade to a bounded voice fallback and be recorded through existing Hermes-backed cognition failure learning where available.

---

## File Structure

- `src/agent_hub/voice/companion.py`: add `RobotRunBridge`, result extraction, bounded fallback text, and protocols for submit/read dependencies.
- `src/agent_hub/voice/gateway.py`: accept an async robot responder and pass final speech into the bridge.
- `src/agent_hub/robot/session.py`: support async final-speech responders while preserving existing sync tests.
- `src/agent_hub/app.py`: wire `RobotRunBridge` from app state only when `run_service` and a run repository are available.
- `tests/api/test_robot_voice_gateway.py`: cover run submission metadata, terminal artifact extraction, and fallback behavior.
- `tools/robot_voice_probe.py`: hardware-free HTTP/WebSocket probe for production and local validation.
- `docs/robot-field-test.md`: Saturday field-test checklist for Pi runtime, server token, OTA dry-run, audio I/O, and bidirectional conversation.
- `HANDOFF.md`: local-only current-state update after verification/deploy.

### Task 1: Server Robot Run Bridge

**Files:**
- Modify: `src/agent_hub/voice/companion.py`
- Modify: `src/agent_hub/robot/session.py`
- Modify: `src/agent_hub/voice/gateway.py`
- Modify: `src/agent_hub/app.py`
- Test: `tests/api/test_robot_voice_gateway.py`

**Interfaces:**
- Produces: `RobotTextResponder = Callable[..., str | Awaitable[str]]`
- Produces: `RobotRunBridge.respond_text(utterance: str, *, device_id: str, session_id: str) -> str`
- Consumes: existing `run_service.submit(...)`, `run_service.execute(...)` when available, `run_repository.artifacts(...)` when available.

- [ ] **Step 1: Add failing API tests**

Add tests that inject a fake run service and fake run repository, send a final `speech.partial`, and assert:

```python
assert submitted["mode"].value == "auto"
assert submitted["conversation_id"] == "robot-pi-lab-01-voice-session-1"
assert submitted["channel_context"]["source_channel"] == "robot_voice"
assert submitted["channel_context"]["requested_channel_features"] == "voice,audio,robot"
assert response["type"] == "assistant.text.done"
assert response["payload"]["text"] == "服务端 Agent 回复"
```

Also add fallback tests for a waiting-choice/no-artifact path and for a bridge exception:

```python
assert "我已经收到你的语音" in response["payload"]["text"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src python -m pytest tests/api/test_robot_voice_gateway.py -q -p no:cacheprovider`

Expected: bridge-related tests fail because final speech still uses the deterministic echo responder.

- [ ] **Step 3: Implement async-compatible registry and bridge**

Implement `RobotRunBridge` with these exact policies:

```python
mode = TaskMode.AUTO
conversation_id = f"robot-{safe_device_id}-{safe_session_id}"
idempotency_key = f"robot:{device_id}:{session_id}:{sha256(utterance).hexdigest()}"
channel_context = {
    "source_channel": "robot_voice",
    "channel_tenant_external_id": tenant_id,
    "channel_sender_external_id": device_id,
    "channel_conversation_external_id": session_id,
    "channel_message_id": sha256(utterance).hexdigest()[:32],
    "channel_event_id": idempotency_key,
    "channel_conversation_type": "voice_chat",
    "channel_entry_policy": "main_agent_decides",
    "requested_channel_features": "voice,audio,robot",
}
```

The bridge should call `run_service.submit(...)`, call `run_service.execute(run_id)` if the service exposes it, then read text artifacts from `run_repository.artifacts(tenant_id, run_id)` if available. If no terminal text is available, return a short Chinese bounded fallback that includes the run id.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src python -m pytest tests/api/test_robot_voice_gateway.py tests/unit/robot/test_session.py -q -p no:cacheprovider`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/agent_hub/voice/companion.py src/agent_hub/robot/session.py src/agent_hub/voice/gateway.py src/agent_hub/app.py tests/api/test_robot_voice_gateway.py
git commit -m "feat: bridge robot speech to agent runs"
```

### Task 2: Hardware-Free Probe And Field-Test Checklist

**Files:**
- Create: `tools/robot_voice_probe.py`
- Create: `docs/robot-field-test.md`
- Modify: `tests/unit/install/test_pi_runtime_assets.py`

**Interfaces:**
- Produces CLI: `python tools/robot_voice_probe.py --base-url http://103.236.93.62:32020 --device-id pi-lab-01 --device-token <token> --utterance "你好"`
- Consumes Robot Protocol v1 WebSocket path `/api/v1/robot/ws/{device_id}` and OTA manifest path `/api/v1/robot/ota/manifest/{device_id}`.

- [ ] **Step 1: Add failing probe asset tests**

Add tests asserting the probe file exists, contains `--base-url`, `--device-id`, `--device-token`, `--utterance`, uses `/api/v1/robot/ws/`, and docs mention `2026-09-12`, `prod-web-02`, `32020`, OTA dry-run, audio capture, playback, and rollback.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src;cube-robot-runtime python -m pytest tests/unit/install/test_pi_runtime_assets.py -q -p no:cacheprovider`

Expected: fails because the probe and field-test doc do not exist.

- [ ] **Step 3: Implement probe and docs**

The probe must avoid external dependencies beyond Python stdlib plus optional `websocket-client` if installed. If WebSocket support is missing, it should still probe OTA/login HTTP paths and exit with a clear bounded error for WS.

- [ ] **Step 4: Run focused tests**

Run: `PYTHONPATH=src;cube-robot-runtime python -m pytest tests/unit/install/test_pi_runtime_assets.py -q -p no:cacheprovider`

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add tools/robot_voice_probe.py docs/robot-field-test.md tests/unit/install/test_pi_runtime_assets.py
git commit -m "test: add robot voice hardware-free probe"
```

### Task 3: Verification, Deployment, And Handoff

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes all previous task outputs.
- Produces verified local branch, production release on `prod-web-02`, GitHub push status, and concise handoff.

- [ ] **Step 1: Run focused suites**

Run:

```bash
PYTHONPATH=src;cube-robot-runtime python -m pytest tests/unit/robot tests/api/test_robot_voice_gateway.py tests/unit/install/test_pi_runtime_assets.py cube-robot-runtime/tests -q -p no:cacheprovider
```

Expected: pass.

- [ ] **Step 2: Run quality checks**

Run:

```bash
python -m ruff check --no-cache src tests cube-robot-runtime tools --exclude cube-robot-runtime/scripts
git diff --check
```

Expected: pass.

- [ ] **Step 3: Deploy to prod-web-02 and probe**

Clean only clearly disposable deployment garbage, deploy a new release, restart services, and probe:

```bash
curl.exe --noproxy * http://103.236.93.62:32020/login
python tools/robot_voice_probe.py --base-url http://103.236.93.62:32020 --device-id pi-lab-01 --device-token <server-configured token> --utterance "周六实机测试前的服务端模拟"
```

Expected: login returns 200; OTA/auth passes; WS returns `assistant.text.done`.

- [ ] **Step 4: Update local-only handoff**

Update `HANDOFF.md` with current branch/commit/release, verification, production probe, known limitation that real Pi/audio hardware waits for 2026-09-12, and next recommended field-test steps.

- [ ] **Step 5: Push and inspect GitHub checks**

Push `robot-runtime-protocol`, inspect checks/runs for the pushed SHA, and fix/repeat if failures appear.

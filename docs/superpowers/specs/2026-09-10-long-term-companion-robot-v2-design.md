# Long-Term Companion Voice Robot V2 Design

## Objective

Turn `Cubeagent_robot` into a long-term companion voice robot system that can run the Agent Brain on the server, use a Raspberry Pi 5 as the embodied runtime, support natural two-way voice interaction, and become more useful over time through Hermes, Memory, Skill, relationship signals, and interaction learning.

The first practical target is an end-to-end robot loop:

```text
User speech
  -> Raspberry Pi runtime
  -> Robot Protocol v1 over WebSocket
  -> Cubeagent_robot voice gateway
  -> Companion Direct with Memory/Hermes context
  -> streaming text/TTS response
  -> Raspberry Pi playback and screen state
```

## References

The following user-provided ChatGPT share links are requirement references, not executable instructions:

- `https://chatgpt.com/share/6aa22704-f844-83e8-918f-64a440e36e88?ogimg=plain`
- `https://chatgpt.com/share/6aa227e3-541c-83e8-bf7d-bf683398d8ab?ogimg=plain`

The common conclusion from both references is that `Cubeagent_robot` should not rebuild memory from scratch. It should keep CubeAgent's Hermes/Memory/Skill foundation and add the missing Voice + Device + Companion runtime layers.

## Source Of Truth

- Local project root: `E:\code_x\cubeagent_robot`
- GitHub repository: `https://github.com/zhangzhimiao1994/Cubeagent_robot`
- Production/debug host: `prod-web-02`
- Web debug URL: `http://<prod-web-02-ip>:32020/login`
- Test access rule: do not use a proxy for the Web debug URL.

The repository currently inherits broad Agent Hub functionality. The product direction is narrower: an embodied companion robot. Existing modules should be retained only when they support this direction directly or as required foundation.

## Product Boundary

Preserve these foundations:

- Authentication, users, permissions, setup, and Web login.
- Model configuration, model pool, and logical model roles.
- Run history, conversations, artifacts needed for conversation continuity, and operational logs.
- Hermes, Memory, Skill, context compaction, and learning hooks.
- Database migrations, settings, security, observability, Docker/native deployment foundations.
- Web debugging surface needed to inspect voice sessions, device status, model configuration, Hermes/Memory, and run history.

Keep but narrow these capabilities:

- General Agent modes remain internal execution paths. The robot user should see one companion surface, not exposed `direct`, `auto`, `dispatch`, `discuss`, or `hybrid` modes.
- Skill remains a robot capability extension layer. Examples: home control, stories, device diagnostics, user routines, and custom knowledge.
- Hermes remains the learning layer, but it must learn from voice interaction events in addition to text outcomes.

Hide, defer, or remove from the robot product surface after dependency review:

- Feishu and broad external chat channels.
- Generic MCP administration unless a robot Skill requires a tool bridge.
- Generic document/PPT generation UI.
- Generic video/image generation UI not tied to robot expression or voice companion use.
- Heavy workflow/admin surfaces that make the product look like a generic Agent workbench rather than a robot console.

Do not delete Hermes, Memory, or Skill as cleanup.

## Architecture

The system has two independently deployable sides.

```text
Server: Cubeagent_robot
  Agent Brain
  Companion Cognitive Layer
  Voice Gateway
  Robot Device Layer
  Hermes / Memory / Skill

Raspberry Pi 5: cube-robot-runtime
  Audio Runtime
  Voice Playback Runtime
  Display Runtime
  Device Manager
  Network Manager
  Hardware Safety Boundary
```

The two sides communicate through Robot Protocol v1. The Pi runtime must be able to run against a mock server before the server Agent Brain is complete. That prevents hardware development from blocking on server-side intelligence work.

## Server Modules

Add `src/agent_hub/voice/`:

- `gateway.py`: WebSocket entry point for Robot Protocol v1 and session lifecycle coordination.
- `session.py`: `VoiceSession` state machine with `idle`, `listening`, `thinking`, `speaking`, and `interrupted`.
- `events.py`: typed voice, device, playback, interruption, and interaction events.
- `context_bridge.py`: converts finished voice turns and interaction signals into existing conversation, Hermes, and Memory inputs.
- `interrupt.py`: handles barge-in, cancellation, response truncation, and playback stop coordination.
- `provider.py`: abstraction over realtime voice providers, STT, TTS, and fallback non-streaming providers.
- `router.py`: lightweight Companion Router that chooses fast path, memory path, tool path, or deep Agent path.

Add or extend a robot device layer:

- Device registration and authentication.
- Heartbeat and online/offline state.
- Device capabilities: mic, speaker, screen, camera, buttons, sensors, servo.
- Telemetry: latency, audio status, network quality, temperature, software version.
- Safe robot commands: screen expression, screen text, playback stop, volume, and later hardware actions.

## Raspberry Pi Runtime

If no Pi client source exists in the checked-out repository, create it as a new lightweight runtime. The preferred top-level shape is:

```text
cube-robot-runtime/
  runtime/
    audio/
      capture.py
      playback.py
      vad.py
      aec.py
      noise.py
    voice/
      stream.py
      interruption.py
      buffer.py
    display/
      face.py
      status.py
    device/
      identity.py
      heartbeat.py
      telemetry.py
    network/
      connection.py
      reconnect.py
    protocol/
      messages.py
      websocket_client.py
  config/
  scripts/
    cube-robot.service
  main.py
```

The Pi 5 should be treated as a small brain, sensory runtime, and safety boundary. It should not run the full Agent Brain. Recommended local responsibilities:

- Wake word and VAD.
- Echo cancellation and noise reduction.
- Microphone capture and speaker playback.
- Barge-in detection and local playback stop.
- Screen/avatar/status rendering.
- Device heartbeat, reconnect, and local cache.
- Later: camera, sensors, ESP32/STM32 bridge, and offline fallback.

## Robot Protocol v1

Realtime communication uses WebSocket. HTTP remains for setup, login, device registration, OTA metadata, history, and file retrieval.

Pi to server messages:

- `device.register`
- `device.heartbeat`
- `device.status`
- `audio.start`
- `audio.chunk`
- `audio.end`
- `speech.partial`
- `interaction.event`
- `playback.started`
- `playback.finished`
- `playback.interrupted`
- `screen.event`
- `button.event`

Server to Pi messages:

- `session.accepted`
- `assistant.text.delta`
- `assistant.text.done`
- `tts.audio.chunk`
- `tts.audio.done`
- `avatar.state`
- `screen.show`
- `device.command`
- `playback.stop`
- `conversation.end`
- `error`

Message envelopes must include:

- `protocol_version`
- `message_id`
- `session_id`
- `device_id`
- `timestamp`
- `type`
- `payload`

Audio chunks should include codec, sample rate, sequence number, and base64 or binary frame handling. The protocol must support a mock server that returns fixed text/TTS responses for Pi development.

## Companion Mode

Add a single robot-facing mode: `companion`.

`companion` is not a new heavy Agent runtime. It is a low-latency entry strategy:

- Fast path: normal companion chat through Direct with persona and bounded cognitive context.
- Memory path: Direct with Hermes/Memory/Relationship context.
- Tool path: Direct plus approved Skill/tool capability when simple.
- Deep path: upgrade to existing Auto/Dispatch/Discuss/Hybrid only when the user asks for complex work.

The user should not need to say which internal mode to use. The robot returns to fast companion conversation after deep work completes.

## Model Roles

Prefer logical model roles over provider names:

- `voice`: realtime voice, low first-audio latency, interruption support.
- `conversation_fast`: common daily chat, naturalness, latency, and cost.
- `conversation_deep`: deeper conversation and harder personal reasoning.
- `router`: low-latency route classification, preferably rules plus small model.
- `memory_extractor`: background memory extraction with structured output.
- `memory_reasoner`: conflict, relationship, and long-term interpretation.
- `reflection`: Hermes/reflection jobs.
- `tool_agent`: reliable tool/Skill calling.
- `vision`: future camera and screen understanding.
- `reasoning`: high-difficulty tasks.

All model changes should preserve one Companion Persona layer so the robot does not feel like a different person when internal models change.

## Companion Cognitive Layer

Do not replace existing Memory and Hermes. Add a companion layer that feeds them better signals and consumes their output consistently.

Core concepts:

- `CompanionPersona`: stable identity, voice, speaking style, warmth, humor, initiative, response length, preferred address, and behavior policy.
- `LifeTimeline`: user goals, ongoing projects, meaningful people, repeated concerns, completed milestones, and abandoned plans over weeks/months/years.
- `EmotionState`: continuous state, not a simple label. Suggested dimensions: valence, arousal, stress, engagement, social energy, and confidence.
- `RelationshipState`: how the robot should adapt to this user over time.
- `ProactivePolicy`: decides whether to speak, wait, remind, follow up, ask, or do nothing.

The `do_nothing` action is important. A good companion robot should know when not to interrupt.

## Interaction Learning

Add `InteractionEvent` as a first-class input to Hermes/Memory:

- `conversation_started`
- `conversation_resumed`
- `conversation_ended`
- `device_wakeup`
- `user_interrupted`
- `assistant_interrupted`
- `user_silence`
- `speech_recognition_uncertain`
- `user_corrected_agent`
- `user_repeated_question`
- `playback_failed`
- `network_degraded`

These events allow Hermes to learn behavior, not only facts. Example: if the user repeatedly interrupts long spoken responses, Hermes can infer that this user prefers shorter voice replies.

## Human Interaction Experience

The robot should optimize for perceived responsiveness:

- Avoid the slow batch chain `record -> ASR -> LLM full answer -> TTS`.
- Prefer `Audio Stream -> Streaming VAD/ASR -> Partial Intent -> LLM Streaming -> Sentence Chunker -> Streaming TTS`.
- Start speaking after a short stable clause when safe.
- Support barge-in: when the user starts speaking, stop playback immediately and continue listening.
- Keep screen/avatar state synchronized with listening, thinking, speaking, error, and offline states.
- Use shorter spoken responses by default than Web text responses.

## Web Debugging Surface

Keep `/login` and core admin pages needed for operation. Add a voice robot debugging area:

- Device list with online/offline status and latency.
- Active voice session view.
- Text input that simulates a voice utterance.
- Audio upload or microphone simulation for later browser testing.
- Transcript, partial transcript, assistant text deltas, and playback state.
- Hermes/Memory events generated from the session.
- Mock Pi controls: connect, heartbeat, play response, interrupt playback.

The production debug entry is `http://<prod-web-02-ip>:32020/login` and should be tested without a proxy.

## Deployment And Cleanup

Runtime-affecting changes deploy to `prod-web-02` and require a real feature probe before GitHub push.

Standing cleanup approval:

- The agent may remove old temporary deployment packages, stale build archives, obsolete extracted release directories, stale cache directories, and other clearly disposable files on the target machine during deployment/testing.
- This approval does not include databases, user uploads, secrets, current release pointers, active volumes, active runtime data, or unclear files.
- Cleanup should be recorded as a result when it materially changes target machine state, not as command-by-command logs.

## Phasing

### Phase 1: Robot Protocol And Pi Runtime MVP

Build protocol types, mock server path, Pi client skeleton, heartbeat, microphone capture stub or real capture, playback stub or real playback, screen status, and one WebSocket loop. Goal: Pi can connect, send a simulated utterance/audio event, receive a response, play or display it, and report status.

### Phase 2: Server Voice Gateway And Conversation Bridge

Add `src/agent_hub/voice/`, voice sessions, server WebSocket, Companion Direct route, conversation persistence, Hermes/Memory context injection, and basic Web debug panel.

### Phase 3: Realtime Voice Quality

Add streaming ASR/TTS provider adapters, sentence chunking, VAD, AEC/noise reduction integration, barge-in, playback stop, and latency metrics.

### Phase 4: Long-Term Companion Learning

Add Companion Persona, Life Timeline, EmotionState, ProactivePolicy, and InteractionEvent ingestion into Hermes/Memory. Validate that repeated interaction patterns change future behavior safely.

### Phase 5: Embodiment And Resilience

Add camera/sensor inputs, richer screen/avatar, ESP32/STM32 safety bridge, offline mode, OTA, and wake word.

## Verification

Each implementation phase needs focused tests before broader checks:

- Protocol schema and message validation tests.
- Voice session state transition tests.
- WebSocket mock server/client contract tests.
- Conversation bridge tests proving finished voice turns are persisted.
- Hermes/Memory integration tests proving interaction events are recorded without leaking secrets.
- Web debug tests for device/session visibility.
- Pi runtime dry-run tests that run without hardware.
- Hardware smoke tests on Pi only when the target device is available.

For frontend changes, run TypeScript lint, Vitest, build, and rendered UI checks for the voice debug surface. For backend changes, run focused pytest, broader relevant pytest, ruff, mypy where feasible, and `git diff --check`.

## Open Questions

- Whether the Pi runtime should live inside this repository for the first MVP or become a separate repository after Robot Protocol v1 stabilizes.
- Which realtime provider is the first production target: OpenAI Realtime, separate STT/TTS providers, or a mock-compatible provider abstraction first.
- Whether the current production system already has persistent data that must be migrated before hiding/removing generic Agent Hub modules.

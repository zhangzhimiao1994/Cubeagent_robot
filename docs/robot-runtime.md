# Robot Runtime (Raspberry Pi)

On-device interaction layer for the voice companion. This is not the cloud multi-agent console.

## Goals

- Continuous mic capture with low latency
- Turn-taking: decide when the user finished speaking
- Barge-in: cancel TTS playback when the user speaks
- Local session + Companion State mirror
- Bridge to cloud brain (`agent_hub`) over authenticated WebSocket
- Optional local small-model path (stub in Phase 1)

## Package layout (proposed)

```text
robot_runtime/
  README.md
  pyproject.toml
  src/robot_runtime/
    __init__.py
    main.py              # process entry
    config.py            # device id, urls, audio devices
    audio/
      capture.py         # mic input
      playback.py        # speaker queue
      aec.py             # echo cancel stub
    vad/
      turn_taking.py     # end-of-utterance
      barge_in.py        # interrupt while speaking
    session/
      state.py           # Companion State mirror
      loop.py            # listen → think → speak loop
    bridge/
      protocol.py        # message schema
      client.py          # WebSocket client to cloud
    router/
      edge_cloud.py      # Phase 1 stub: always cloud
```

## Main loop

```text
IDLE
  → hearing (VAD speech start)
  → capturing until turn-taking end
  → THINKING (send UtteranceEnd + audio/transcript to brain)
  → SPEAKING (stream TTS / play audio chunks)
  → if barge-in: stop playback, cancel brain turn, back to capturing
  → IDLE / hearing
```

## Bridge protocol (draft)

Transport: WebSocket `wss://<host>/api/robot/v1/ws`
Auth: device token (header or first frame)

### Device → Cloud

| type | purpose |
|---|---|
| `hello` | device_id, firmware, capabilities |
| `utterance.start` | turn_id |
| `utterance.audio` | turn_id, pcm/opus chunk |
| `utterance.end` | turn_id, optional local transcript |
| `barge_in` | turn_id being interrupted |
| `state.patch` | local companion state deltas |
| `ping` | keepalive |

### Cloud → Device

| type | purpose |
|---|---|
| `hello.ok` | session_id, companion_state snapshot |
| `assistant.audio` | reply_id, audio chunk |
| `assistant.text` | reply_id, text (debug / captions) |
| `assistant.end` | reply_id |
| `state.sync` | authoritative Companion State |
| `memory.hint` | optional short facts to speak naturally |
| `proactive.say` | Phase 2 push companion lines |
| `cancel` | stop current reply |
| `error` | recoverable error |

## Companion State (minimal)

```json
{
  "persona_id": "default",
  "relationship_level": 0,
  "mood": "neutral",
  "scene": "idle_chat",
  "last_user_topics": [],
  "updated_at": "2026-09-05T17:00:00Z"
}
```

Cloud is source of truth; device mirrors for offline UX and barge-in continuity.

## Cloud endpoints to add later

- `WS /api/robot/v1/ws` — realtime bridge
- `POST /api/robot/v1/devices/register` — device bootstrap
- `GET /api/robot/v1/companion-state` — snapshot
- Reuse memory APIs; do not invent a second memory store on device beyond short working buffer

## Non-goals for Robot Runtime

- Image/video/audio **generation** jobs (removed from product scope)
- Multi-agent dispatch UI
- OpenClaw / desktop control

# Voice Companion Product Direction

The agent backend must behave like an intelligent human voice companion, not an ops multi-agent console.

## Product north star

- Speak like a person: short turns, natural rhythm, can be interrupted
- Remember the user over weeks/months (preferences, life events, relationship)
- Have a stable persona and evolving relationship state
- Proactive care later (greetings, check-ins) without being annoying

## Split of responsibility

| Layer | Owns |
|---|---|
| Pi frontend `device/robot_runtime/` | Mic/speaker, VAD, barge-in, transport |
| Agent backend `src/agent_hub/` | Understanding, persona, memory, reply text/audio policy |

Pi never runs models. All “intelligence” is backend.

## Backend modules that matter for voice companionship

1. **Companion brain** (`companion/`) — persona, mood, relationship, scene
2. **Memory + Life Timeline** — durable facts/events injected every turn
3. **Voice dialogue policy** — reply length, speaking style, interrupt recovery
4. **Robot bridge** (`/api/robot/v1`) — realtime turns from device
5. **Proactive engine** — schedule-based nudges (phase 2)

## Explicitly de-emphasize for this product

- Dispatch / discuss multi-agent workbench UX
- Evolution / skill Darwin loops
- Multimedia generation jobs
- OpenClaw desktop control as the main path

## Voice dialogue policy (v1)

- Prefer 1–3 short spoken sentences unless user asks for detail
- On barge-in: drop unfinished reply, re-listen, answer the new intent
- Always pull top memory hints before answering
- Never dump tool traces or ops jargon into spoken replies

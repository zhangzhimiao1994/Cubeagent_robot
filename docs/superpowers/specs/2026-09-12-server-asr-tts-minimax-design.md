# Server ASR/TTS MiniMax Voice Loop Design

## Purpose

Build the first real voice interaction loop for the robot while keeping the Raspberry Pi as a device runtime only. The Pi captures microphone audio and plays returned audio. The server performs ASR, Agent/Hermes processing, TTS, and voice clone management.

## Current State

- Robot text dry-run works from the Raspberry Pi to `prod-web-02`.
- Robot Protocol v1 already includes `audio.start`, `audio.chunk`, `audio.end`, `assistant.text.done`, `tts.audio.chunk`, and `tts.audio.done`.
- The server already bridges final `speech.partial` text into Agent runs through `RobotRunBridge`.
- Pi runtime currently sends text dry-run and records playback text. It does not yet run a real record-send-play loop.

## Provider Choice

Use MiniMax for server-side speech:

- ASR: MiniMax Speech to Text API.
- TTS: MiniMax synchronous T2A HTTP API, initially non-streaming for the first reliable single-turn loop.
- Voice clone: MiniMax file upload plus `/v1/voice_clone`.

MiniMax API credentials stay on the server only:

- `MINIMAX_API_KEY`: required for provider calls.
- Optional endpoint override variables may be supported for testing, but no MiniMax key is written to Pi config, Git, browser code, logs, or Robot Protocol messages.

Primary MiniMax facts used by this design:

- The docs index exposes Speech to Text, HTTP/WebSocket T2A, voice cloning, voice management, and OpenAPI specs.
- T2A HTTP uses `POST /v1/t2a_v2`, supports `speech-2.8-hd` and `speech-2.8-turbo`, returns audio as hex or URL, supports `voice_setting.voice_id`, and supports formats including mp3 and wav for non-streaming.
- Voice clone uploads `mp3`, `m4a`, or `wav` source audio of 10 seconds to 5 minutes and up to 20 MB, then calls `/v1/voice_clone` with a custom `voice_id`.
- Custom `voice_id` must start with a letter, be 8-256 chars, contain letters/digits/`-`/`_`, and not end with `-` or `_`.
- Cloned voices are temporary unless used in T2A within 168 hours.

## Architecture

### Server Components

Add `src/agent_hub/voice/media.py`:

- Defines provider protocols:
  - `SpeechToTextProvider.transcribe(audio: VoiceAudio) -> SpeechTranscript`
  - `TextToSpeechProvider.synthesize(text: str, voice: VoiceSynthesisOptions) -> SynthesizedAudio`
  - `VoiceCloneProvider.clone_voice(request: VoiceCloneRequest) -> VoiceCloneResult`
- Defines `VoiceMediaService`, which owns per-session audio buffers and turns `audio.start/audio.chunk/audio.end` into:
  - `assistant.text.done`
  - `tts.audio.chunk`
  - `tts.audio.done`
  - `error` envelopes on bounded failures

Add `src/agent_hub/voice/minimax.py`:

- Implements MiniMax HTTP clients for STT, TTS, and voice clone.
- Reads the API key only from injected config or server environment.
- Does not log raw audio, raw transcript, token, or API key.
- Decodes MiniMax TTS hex audio to bytes.
- Uses MiniMax response `base_resp.status_code` and HTTP status for error classification.

Extend `src/agent_hub/voice/gateway.py`:

- Accept a `media_service` dependency.
- For `audio.start/audio.chunk/audio.end`, delegate to `VoiceMediaService`.
- Preserve existing `speech.partial` behavior.
- Return media response envelopes over the same WebSocket.

Add lightweight admin endpoints later for voice clone management. The first implementation may provide service-level clone methods and tests only; Web UI upload can be a follow-up task.

### Pi Components

Add a real single-turn command:

```bash
cube-robot voice-once --config /etc/cube-robot/robot.toml --seconds 5
```

The command:

1. Records mono WAV with `arecord`.
2. Sends `audio.start`.
3. Sends base64 `audio.chunk` messages.
4. Sends `audio.end` with selected `voice_id`.
5. Receives `assistant.text.done`.
6. Receives `tts.audio.chunk` / `tts.audio.done`.
7. Writes returned audio to a temp file.
8. Plays it with `aplay`.

Pi config gains:

```toml
[audio]
record_command = "arecord"
play_command = "aplay"
sample_rate_hz = 16000
channels = 1
format = "wav"

[voice]
tts_voice_id = "default_female_zh"
tts_model = "speech-2.8-turbo"
```

The Pi never receives or stores `MINIMAX_API_KEY`.

## Protocol Details

### `audio.start`

Payload:

```json
{
  "codec": "wav",
  "sample_rate_hz": 16000,
  "channels": 1,
  "language": "zh",
  "voice_id": "default_female_zh",
  "tts_model": "speech-2.8-turbo"
}
```

### `audio.chunk`

Payload:

```json
{
  "codec": "wav",
  "sample_rate_hz": 16000,
  "sequence": 1,
  "chunk_b64": "..."
}
```

### `audio.end`

Payload:

```json
{
  "total_chunks": 3,
  "voice_id": "default_female_zh",
  "tts_model": "speech-2.8-turbo"
}
```

### Server Responses

The server sends:

```json
{"type": "assistant.text.done", "payload": {"text": "..."}}
{"type": "tts.audio.chunk", "payload": {"codec": "mp3", "sequence": 1, "chunk_b64": "..."}}
{"type": "tts.audio.done", "payload": {"codec": "mp3", "total_chunks": 1}}
```

For the first implementation, TTS can be non-streaming and sent as one chunk. The protocol keeps chunking so streaming can be added without changing Pi command shape.

## Voice Selection And Clone

Voice selection is always by `voice_id`.

Initial support:

- Built-in/default MiniMax `voice_id` configured on server or Pi.
- Pi can request a `voice_id`, but the server may validate it against an allowlist.
- If requested voice fails, server falls back to a configured default voice and returns a bounded warning only in logs or debug metadata, not secrets.

Clone support:

- Source audio upload must be 10 seconds to 5 minutes, no more than 20 MB, format `mp3`, `m4a`, or `wav`.
- Clone request stores:
  - `voice_id`
  - `owner`
  - `consent_confirmed`
  - `provider="minimax"`
  - `model`
  - `status`
  - `created_at`
  - `last_used_at`
- The system must reject clone attempts unless the operator confirms the audio is their own voice or explicitly authorized.
- Reference audio and clone upload files are not committed, logged, or exposed to the Pi.

## Error Handling

Server errors become Robot Protocol `error` envelopes with:

```json
{
  "code": "asr_failed",
  "message": "speech recognition failed"
}
```

Supported initial error codes:

- `audio_session_missing`
- `audio_chunk_invalid`
- `audio_too_large`
- `asr_unavailable`
- `asr_failed`
- `tts_unavailable`
- `tts_failed`
- `voice_not_allowed`

The server must close or reset the current audio buffer after terminal errors to avoid replaying stale audio.

## Limits

Initial bounds:

- Max audio payload per turn: 10 MB after base64 decode.
- Max chunks per turn: 256.
- Max assistant text for TTS: 2,000 characters.
- Default TTS model: `speech-2.8-turbo`.
- Default TTS format: `mp3`.
- Default sample rate: `32000` for returned TTS.

## Testing

Server tests:

- `audio.start/chunk/end` calls ASR then existing Agent responder then TTS.
- `tts.audio.chunk` and `tts.audio.done` are emitted after assistant text.
- MiniMax TTS client builds the documented `/v1/t2a_v2` payload.
- Voice clone client validates consent and `voice_id` rules before provider calls.
- Invalid or oversized audio returns bounded `error` envelopes.

Pi tests:

- `voice-once` invokes the configured record command, sends audio envelopes, receives TTS envelopes, writes audio, and invokes play command.
- Pi runtime remains isolated from `agent_hub`, `cognition`, and `hermes`.

Deployment tests:

- Keep existing dry-run text probe.
- Add a media probe or Pi command run against `prod-web-02` with test audio.
- Verify `/health/live`, `/health/ready`, `/login`, OTA, text WebSocket, and `voice-once`.

## Security And Privacy

- Do not paste MiniMax keys into chat.
- Store `MINIMAX_API_KEY` only in `/etc/agent-hub/secrets.env` on the server.
- Do not put MiniMax keys in Pi config.
- Do not log raw audio, cloned voice samples, API keys, device tokens, or raw long transcripts.
- Voice clone requires explicit consent.
- Cloned voice profiles are private by default.
- If provider calls fail, degrade to text-only or default voice; do not retry in a tight loop.

## Rollout

1. Implement mockable server media service and protocol handling.
2. Implement Pi `voice-once` with shell-command recording/playback.
3. Implement MiniMax TTS and voice clone clients behind feature/config gates.
4. Add deployment docs and update the robot manual.
5. Deploy to `prod-web-02`.
6. Configure `MINIMAX_API_KEY` on server.
7. Run text probe, OTA probe, then Pi `voice-once`.

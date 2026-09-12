"""One-shot voice interaction for capture-only Raspberry Pi devices."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from cube_robot_runtime.audio.capture import AudioCapture, AudioCaptureConfig
from cube_robot_runtime.audio.playback import AudioPlayback
from cube_robot_runtime.device.identity import DeviceIdentity
from cube_robot_runtime.network.client import open_connection
from cube_robot_runtime.protocol.messages import RobotEnvelope


@dataclass(frozen=True)
class VoiceOnceConfig:
    server_url: str
    device_id: str
    session_id: str = "voice-once-session"
    device_token: str | None = None
    timeout_seconds: float = 30.0
    language: str | None = "zh"
    voice_id: str | None = None
    tts_model: str | None = None
    capture: AudioCaptureConfig = field(default_factory=AudioCaptureConfig)
    chunk_size_bytes: int = 48_000
    max_receive_frames: int = 32


@dataclass(frozen=True)
class VoiceOnceResult:
    sent_types: tuple[str, ...]
    received_types: tuple[str, ...]
    received_texts: tuple[str, ...]
    played_audio_codecs: tuple[str, ...]


def run_voice_once(
    config: VoiceOnceConfig,
    *,
    capture: AudioCapture,
    playback: AudioPlayback,
) -> VoiceOnceResult:
    if config.chunk_size_bytes <= 0:
        raise ValueError("chunk_size_bytes must be positive")
    identity = DeviceIdentity(device_id=config.device_id)
    audio = capture.record()
    if not audio:
        raise RuntimeError("audio capture returned no data")

    connection = open_connection(
        config.server_url,
        device_token=config.device_token,
        timeout_seconds=config.timeout_seconds,
    )
    sent: list[RobotEnvelope] = []
    received: list[RobotEnvelope] = []
    received_texts: list[str] = []
    played_codecs: list[str] = []
    buffered_audio: list[bytes] = []
    buffered_codec: str | None = None
    try:
        start_payload: dict[str, object] = {
            "runtime_version": "0.1.0",
        }
        heartbeat = RobotEnvelope.new(
            message_type="device.heartbeat",
            device_id=identity.device_id,
            session_id=config.session_id,
            payload=start_payload,
        )
        _send(connection, heartbeat, sent)
        audio_start_payload: dict[str, object] = {
            "codec": config.capture.codec,
            "sample_rate_hz": config.capture.sample_rate_hz,
            "channels": config.capture.channels,
        }
        if config.language:
            audio_start_payload["language"] = config.language
        if config.voice_id:
            audio_start_payload["voice_id"] = config.voice_id
        if config.tts_model:
            audio_start_payload["tts_model"] = config.tts_model
        _send(
            connection,
            RobotEnvelope.new(
                message_type="audio.start",
                device_id=identity.device_id,
                session_id=config.session_id,
                payload=audio_start_payload,
            ),
            sent,
        )
        total_chunks = 0
        for total_chunks, chunk in enumerate(_chunks(audio, config.chunk_size_bytes), start=1):
            _send(
                connection,
                RobotEnvelope.new(
                    message_type="audio.chunk",
                    device_id=identity.device_id,
                    session_id=config.session_id,
                    payload={
                        "codec": config.capture.codec,
                        "sample_rate_hz": config.capture.sample_rate_hz,
                        "sequence": total_chunks,
                        "chunk_b64": base64.b64encode(chunk).decode("ascii"),
                    },
                ),
                sent,
            )
        _send(
            connection,
            RobotEnvelope.new(
                message_type="audio.end",
                device_id=identity.device_id,
                session_id=config.session_id,
                payload={"total_chunks": total_chunks},
            ),
            sent,
        )
        for _frame_number in range(config.max_receive_frames):
            envelope = connection.receive()
            received.append(envelope)
            text = envelope.payload.get("text")
            if envelope.type == "assistant.text.done" and isinstance(text, str):
                received_texts.append(text)
            if envelope.type == "tts.audio.chunk":
                chunk_b64 = envelope.payload.get("chunk_b64")
                codec = envelope.payload.get("codec")
                if not isinstance(chunk_b64, str) or not isinstance(codec, str):
                    continue
                buffered_audio.append(base64.b64decode(chunk_b64, validate=True))
                buffered_codec = codec
            if envelope.type == "tts.audio.done":
                done_codec = envelope.payload.get("codec")
                codec = done_codec if isinstance(done_codec, str) else buffered_codec
                if codec and buffered_audio:
                    playback.play_audio(codec, b"".join(buffered_audio))
                    played_codecs.append(codec)
                break
    finally:
        connection.close()
    return VoiceOnceResult(
        sent_types=tuple(envelope.type for envelope in sent),
        received_types=tuple(envelope.type for envelope in received),
        received_texts=tuple(received_texts),
        played_audio_codecs=tuple(played_codecs),
    )


def _send(connection: object, envelope: RobotEnvelope, sent: list[RobotEnvelope]) -> None:
    connection.send(envelope)
    sent.append(envelope)


def _chunks(data: bytes, size: int) -> tuple[bytes, ...]:
    return tuple(data[index : index + size] for index in range(0, len(data), size))

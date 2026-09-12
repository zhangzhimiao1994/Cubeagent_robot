from __future__ import annotations

from agent_hub.robot.protocol import RobotMessageType, build_envelope
from agent_hub.voice.media import SpeechTranscript, SynthesizedAudio, VoiceMediaService


class FakeStt:
    def __init__(self) -> None:
        self.audio_sizes: list[int] = []

    async def transcribe(self, audio: object) -> SpeechTranscript:
        self.audio_sizes.append(len(audio.data))
        return SpeechTranscript(text="你好，机器人", confidence=0.9)


class FakeTts:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None]] = []

    async def synthesize(self, text: str, options: object) -> SynthesizedAudio:
        self.requests.append((text, options.voice_id))
        return SynthesizedAudio(codec="mp3", data=b"mp3-bytes", sample_rate_hz=32000)


async def fake_responder(envelope: object):
    return (
        build_envelope(
            message_type=RobotMessageType.ASSISTANT_TEXT_DONE,
            device_id=envelope.device_id,
            session_id=envelope.session_id,
            payload={"text": "收到，我来回答。"},
        ),
    )


def _audio_start(*, session_id: str = "voice-session-1"):
    return build_envelope(
        message_type=RobotMessageType.AUDIO_START,
        device_id="pi-lab-01",
        session_id=session_id,
        payload={
            "codec": "wav",
            "sample_rate_hz": 16000,
            "channels": 1,
            "language": "zh",
            "voice_id": "female-shaonv",
            "tts_model": "speech-2.8-turbo",
        },
    )


def _audio_chunk(
    *, session_id: str = "voice-session-1", chunk_b64: str = "QUJD", sequence: int = 1
):
    return build_envelope(
        message_type=RobotMessageType.AUDIO_CHUNK,
        device_id="pi-lab-01",
        session_id=session_id,
        payload={
            "codec": "wav",
            "sample_rate_hz": 16000,
            "sequence": sequence,
            "chunk_b64": chunk_b64,
        },
    )


def _audio_end(*, session_id: str = "voice-session-1"):
    return build_envelope(
        message_type=RobotMessageType.AUDIO_END,
        device_id="pi-lab-01",
        session_id=session_id,
        payload={"total_chunks": 1, "voice_id": "female-shaonv"},
    )


async def test_audio_end_transcribes_runs_agent_and_returns_tts_audio() -> None:
    stt = FakeStt()
    tts = FakeTts()
    service = VoiceMediaService(stt_provider=stt, tts_provider=tts, responder=fake_responder)

    assert await service.handle(_audio_start()) == ()
    assert await service.handle(_audio_chunk()) == ()
    responses = await service.handle(_audio_end())

    assert [response.type for response in responses] == [
        RobotMessageType.SPEECH_PARTIAL,
        RobotMessageType.ASSISTANT_TEXT_DONE,
        RobotMessageType.TTS_AUDIO_CHUNK,
        RobotMessageType.TTS_AUDIO_DONE,
    ]
    assert responses[0].payload == {"text": "你好，机器人", "is_final": True, "confidence": 0.9}
    assert responses[1].payload["text"] == "收到，我来回答。"
    assert responses[2].payload == {
        "codec": "mp3",
        "sample_rate_hz": 32000,
        "sequence": 1,
        "chunk_b64": "bXAzLWJ5dGVz",
    }
    assert responses[3].payload == {
        "codec": "mp3",
        "sample_rate_hz": 32000,
        "total_chunks": 1,
    }
    assert stt.audio_sizes == [3]
    assert tts.requests == [("收到，我来回答。", "female-shaonv")]


async def test_audio_chunk_without_start_returns_missing_session_error() -> None:
    service = VoiceMediaService(stt_provider=FakeStt(), tts_provider=FakeTts(), responder=fake_responder)

    responses = await service.handle(_audio_chunk(session_id="missing"))

    assert len(responses) == 1
    assert responses[0].type is RobotMessageType.ERROR
    assert responses[0].payload == {
        "code": "audio_session_missing",
        "message": "audio session is missing",
    }


async def test_invalid_audio_chunk_returns_error_and_resets_session() -> None:
    service = VoiceMediaService(stt_provider=FakeStt(), tts_provider=FakeTts(), responder=fake_responder)

    await service.handle(_audio_start())
    responses = await service.handle(_audio_chunk(chunk_b64="not base64"))

    assert len(responses) == 1
    assert responses[0].payload == {
        "code": "audio_chunk_invalid",
        "message": "audio chunk is invalid",
    }
    missing = await service.handle(_audio_end())
    assert missing[0].payload["code"] == "audio_session_missing"


async def test_audio_over_limit_returns_error_and_resets_session() -> None:
    service = VoiceMediaService(
        stt_provider=FakeStt(),
        tts_provider=FakeTts(),
        responder=fake_responder,
        max_audio_bytes=2,
    )

    await service.handle(_audio_start())
    responses = await service.handle(_audio_chunk())

    assert len(responses) == 1
    assert responses[0].payload == {
        "code": "audio_too_large",
        "message": "audio payload exceeds limit",
    }
    missing = await service.handle(_audio_end())
    assert missing[0].payload["code"] == "audio_session_missing"

import json

import httpx
import pytest

from agent_hub.voice.media import VoiceAudio, VoiceSynthesisOptions
from agent_hub.voice.minimax import MiniMaxSpeechClient, MiniMaxSpeechConfig


@pytest.mark.asyncio
async def test_minimax_transcribe_posts_multipart_audio_with_language_header() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["language"] = request.headers.get("language")
        captured["content_type"] = request.headers.get("content-type")
        captured["body"] = request.content
        return httpx.Response(200, json={"text": "你好，机器人", "duration": 1.2})

    client = MiniMaxSpeechClient(
        MiniMaxSpeechConfig(api_key="secret"),
        client=httpx.AsyncClient(
            base_url="https://api.minimax.io",
            transport=httpx.MockTransport(handler),
        ),
    )

    result = await client.transcribe(
        VoiceAudio(codec="wav", sample_rate_hz=16000, data=b"wav-bytes", language="zh")
    )

    assert result.text == "你好，机器人"
    assert captured["url"] == "https://api.minimax.io/v1/speech_to_text"
    assert captured["authorization"] == "Bearer secret"
    assert captured["language"] == "zh"
    assert str(captured["content_type"]).startswith("multipart/form-data")
    assert b'asr-1.0' in captured["body"]
    assert b"wav-bytes" in captured["body"]


@pytest.mark.asyncio
async def test_minimax_synthesize_decodes_hex_audio_and_uses_voice_settings() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {"audio": "6d7033", "status": 2},
                "extra_info": {
                    "audio_sample_rate": 32000,
                    "audio_format": "mp3",
                },
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

    client = MiniMaxSpeechClient(
        MiniMaxSpeechConfig(
            api_key="secret",
            default_voice_id="robot-voice",
            tts_model="speech-2.8-turbo",
        ),
        client=httpx.AsyncClient(
            base_url="https://api.minimax.io",
            transport=httpx.MockTransport(handler),
        ),
    )

    result = await client.synthesize(
        "服务端回答",
        VoiceSynthesisOptions(voice_id=None, model="speech-2.8-turbo", audio_format="mp3"),
    )

    assert captured["url"] == "https://api.minimax.io/v1/t2a_v2"
    assert captured["authorization"] == "Bearer secret"
    assert captured["json"]["voice_setting"]["voice_id"] == "robot-voice"
    assert captured["json"]["audio_setting"]["format"] == "mp3"
    assert result.codec == "mp3"
    assert result.sample_rate_hz == 32000
    assert result.data == b"mp3"


@pytest.mark.asyncio
async def test_minimax_synthesize_rejects_api_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": None,
                "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
            },
        )

    client = MiniMaxSpeechClient(
        MiniMaxSpeechConfig(api_key="secret", default_voice_id="robot-voice"),
        client=httpx.AsyncClient(
            base_url="https://api.minimax.io",
            transport=httpx.MockTransport(handler),
        ),
    )

    with pytest.raises(RuntimeError, match="text-to-speech returned an error"):
        await client.synthesize(
            "服务端回答",
            VoiceSynthesisOptions(voice_id=None, model="speech-2.8-turbo", audio_format="mp3"),
        )


@pytest.mark.asyncio
async def test_minimax_uploads_voice_file_and_starts_clone_job() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).endswith("/v1/files/upload"):
            return httpx.Response(200, json={"file": {"file_id": 123456789012345680}})
        return httpx.Response(
            200,
            json={
                "input_sensitive": False,
                "demo_audio": "https://example.test/demo.mp3",
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

    client = MiniMaxSpeechClient(
        MiniMaxSpeechConfig(api_key="secret"),
        client=httpx.AsyncClient(
            base_url="https://api.minimax.io",
            transport=httpx.MockTransport(handler),
        ),
    )

    file_id = await client.upload_voice_file(
        b"voice-bytes",
        filename="sample.wav",
        content_type="audio/wav",
        purpose="voice_clone",
    )
    result = await client.clone_voice(
        voice_id="robot-clone",
        source_file_id=file_id,
        model="speech-2.8-hd",
        preview_text="你好，我是你的语音机器人。",
        prompt_text="温和、自然、清晰。",
    )

    assert file_id == "123456789012345680"
    assert str(requests[0].url) == "https://api.minimax.io/v1/files/upload"
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert b'voice_clone' in requests[0].content
    assert b"voice-bytes" in requests[0].content
    assert str(requests[1].url) == "https://api.minimax.io/v1/voice_clone"
    assert json.loads(requests[1].content) == {
        "file_id": 123456789012345680,
        "voice_id": "robot-clone",
        "model": "speech-2.8-hd",
        "text": "你好，我是你的语音机器人。",
        "text_validation": "温和、自然、清晰。",
    }
    assert result["voice_id"] == "robot-clone"
    assert result["preview_audio_url"] == "https://example.test/demo.mp3"

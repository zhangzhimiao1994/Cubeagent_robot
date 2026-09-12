from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from agent_hub.voice.media import (
    SpeechTranscript,
    SynthesizedAudio,
    VoiceAudio,
    VoiceSynthesisOptions,
)

_DEFAULT_BASE_URL = "https://api.minimax.io"
_DEFAULT_ASR_MODEL = "asr-1.0"
_DEFAULT_TTS_MODEL = "speech-2.8-turbo"


@dataclass(frozen=True)
class MiniMaxSpeechConfig:
    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    asr_model: str = _DEFAULT_ASR_MODEL
    tts_model: str = _DEFAULT_TTS_MODEL
    default_voice_id: str | None = None
    audio_format: str = "mp3"
    sample_rate_hz: int = 32000
    bitrate: int = 128000
    language_boost: str | None = "auto"
    speed: float = 1.0
    volume: float = 1.0
    pitch: int = 0
    timeout_seconds: float = 60.0


class MiniMaxSpeechClient:
    def __init__(
        self,
        config: MiniMaxSpeechConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not config.api_key:
            raise ValueError("MiniMax API key is required")
        self._config = config
        self._client = client
        self._owns_client = client is None

    async def transcribe(self, audio: VoiceAudio) -> SpeechTranscript:
        headers = self._headers()
        if audio.language:
            headers["language"] = audio.language
        try:
            response = await self._http().post(
                "/v1/speech_to_text",
                headers=headers,
                data={
                    "model": self._config.asr_model,
                    "response_format": "json",
                    "stream": "false",
                },
                files={
                    "file": (
                        f"robot-turn.{_extension_for(audio.codec)}",
                        audio.data,
                        _content_type_for(audio.codec),
                    )
                },
            )
        except httpx.RequestError as error:
            raise ConnectionError("MiniMax speech-to-text unavailable") from error
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
            raise TypeError("MiniMax speech-to-text response did not include text")
        return SpeechTranscript(text=payload["text"])

    async def synthesize(
        self, text: str, options: VoiceSynthesisOptions
    ) -> SynthesizedAudio:
        voice_id = options.voice_id or self._config.default_voice_id
        if not voice_id:
            raise ValueError("MiniMax voice_id is required for speech synthesis")
        audio_format = options.audio_format or self._config.audio_format
        payload: dict[str, Any] = {
            "model": options.model or self._config.tts_model,
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": self._config.speed,
                "vol": self._config.volume,
                "pitch": self._config.pitch,
            },
            "audio_setting": {
                "sample_rate": self._config.sample_rate_hz,
                "bitrate": self._config.bitrate,
                "format": audio_format,
                "channel": 1,
            },
        }
        if self._config.language_boost:
            payload["language_boost"] = self._config.language_boost
        try:
            response = await self._http().post(
                "/v1/t2a_v2",
                headers=self._headers(),
                json=payload,
            )
        except httpx.RequestError as error:
            raise ConnectionError("MiniMax text-to-speech unavailable") from error
        response.raise_for_status()
        data = response.json()
        base_resp = data.get("base_resp") if isinstance(data, dict) else None
        if isinstance(base_resp, dict) and base_resp.get("status_code") not in (None, 0):
            raise RuntimeError("MiniMax text-to-speech returned an error")
        audio_hex = _nested_string(data, "data", "audio")
        if audio_hex is None:
            raise RuntimeError("MiniMax text-to-speech response did not include audio")
        extra_info = data.get("extra_info") if isinstance(data, dict) else None
        sample_rate = self._config.sample_rate_hz
        audio_codec = audio_format
        if isinstance(extra_info, dict):
            sample_rate_value = extra_info.get("audio_sample_rate")
            audio_format_value = extra_info.get("audio_format")
            if isinstance(sample_rate_value, int):
                sample_rate = sample_rate_value
            if isinstance(audio_format_value, str):
                audio_codec = audio_format_value
        return SynthesizedAudio(
            codec=audio_codec,
            data=bytes.fromhex(audio_hex),
            sample_rate_hz=sample_rate,
        )

    async def upload_voice_file(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        purpose: str,
    ) -> str:
        try:
            response = await self._http().post(
                "/v1/files/upload",
                headers=self._headers(),
                data={"purpose": purpose},
                files={"file": (filename, audio, content_type)},
            )
        except httpx.RequestError as error:
            raise ConnectionError("MiniMax file upload unavailable") from error
        response.raise_for_status()
        payload = response.json()
        file_id = _nested_scalar_string(payload, "file", "file_id") or _nested_scalar_string(
            payload, "data", "file_id"
        )
        if file_id is None:
            raise RuntimeError("MiniMax file upload response did not include file_id")
        return file_id

    async def clone_voice(
        self,
        *,
        voice_id: str,
        source_file_id: str,
        model: str,
        preview_text: str,
        prompt_text: str | None,
        prompt_file_id: str | None = None,
    ) -> dict[str, str]:
        payload: dict[str, Any] = {
            "file_id": _file_id_payload(source_file_id),
            "voice_id": voice_id,
            "model": model,
            "text": preview_text,
        }
        if prompt_file_id and prompt_text:
            payload["clone_prompt"] = {
                "prompt_audio": _file_id_payload(prompt_file_id),
                "prompt_text": prompt_text,
            }
        elif prompt_text:
            payload["text_validation"] = prompt_text
        try:
            response = await self._http().post(
                "/v1/voice_clone",
                headers=self._headers(),
                json=payload,
            )
        except httpx.RequestError as error:
            raise ConnectionError("MiniMax voice clone unavailable") from error
        response.raise_for_status()
        data = response.json()
        base_resp = data.get("base_resp") if isinstance(data, dict) else None
        if isinstance(base_resp, dict) and base_resp.get("status_code") not in (None, 0):
            raise RuntimeError("MiniMax voice clone returned an error")
        return {
            "voice_id": _nested_string(data, "data", "voice_id") or voice_id,
            "preview_audio_url": _nested_string(data, "data", "preview_audio")
            or _nested_string(data, "data", "preview_audio_url")
            or (data.get("demo_audio") if isinstance(data, dict) and isinstance(data.get("demo_audio"), str) else "")
            or "",
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http().aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
            )
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.api_key}"}


def _nested_string(data: object, key: str, child_key: str) -> str | None:
    if not isinstance(data, dict):
        return None
    child = data.get(key)
    if not isinstance(child, dict):
        return None
    value = child.get(child_key)
    return value if isinstance(value, str) and value else None


def _nested_scalar_string(data: object, key: str, child_key: str) -> str | None:
    if not isinstance(data, dict):
        return None
    child = data.get(key)
    if not isinstance(child, dict):
        return None
    value = child.get(child_key)
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return str(value)
    return None


def _file_id_payload(file_id: str) -> int | str:
    return int(file_id) if file_id.isdecimal() else file_id


def _extension_for(codec: str) -> str:
    normalized = codec.lower()
    return "m4a" if normalized == "alac" else normalized


def _content_type_for(codec: str) -> str:
    return {
        "aac": "audio/aac",
        "aiff": "audio/aiff",
        "alac": "audio/mp4",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "opus": "audio/ogg",
        "wav": "audio/wav",
    }.get(codec.lower(), "application/octet-stream")

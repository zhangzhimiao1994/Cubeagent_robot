from __future__ import annotations

import base64
import binascii
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from agent_hub.robot.protocol import RobotEnvelope, RobotMessageType, build_envelope

_DEFAULT_TTS_MODEL = "speech-2.8-turbo"
_DEFAULT_TTS_FORMAT = "mp3"
_DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024
_DEFAULT_MAX_AUDIO_CHUNKS = 256
_MAX_TTS_TEXT_CHARS = 2_000
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceAudio:
    codec: str
    sample_rate_hz: int
    data: bytes
    language: str | None = None


@dataclass(frozen=True)
class SpeechTranscript:
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class VoiceSynthesisOptions:
    voice_id: str | None
    model: str = _DEFAULT_TTS_MODEL
    audio_format: str = _DEFAULT_TTS_FORMAT


@dataclass(frozen=True)
class SynthesizedAudio:
    codec: str
    data: bytes
    sample_rate_hz: int | None = None


class SpeechToTextProvider(Protocol):
    async def transcribe(self, audio: VoiceAudio) -> SpeechTranscript: ...


class TextToSpeechProvider(Protocol):
    async def synthesize(
        self, text: str, options: VoiceSynthesisOptions
    ) -> SynthesizedAudio: ...


Responder = Callable[[RobotEnvelope], Awaitable[tuple[RobotEnvelope, ...]]]


@dataclass
class _AudioSession:
    codec: str
    sample_rate_hz: int
    language: str | None
    voice_id: str | None
    tts_model: str
    chunks: list[bytes]
    size_bytes: int = 0


class VoiceMediaService:
    """Buffers one robot audio turn and returns speech and TTS protocol envelopes."""

    def __init__(
        self,
        *,
        stt_provider: SpeechToTextProvider,
        tts_provider: TextToSpeechProvider,
        responder: Responder,
        max_audio_bytes: int = _DEFAULT_MAX_AUDIO_BYTES,
        max_audio_chunks: int = _DEFAULT_MAX_AUDIO_CHUNKS,
        debug_voice_logs: bool = False,
    ) -> None:
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._responder = responder
        self._max_audio_bytes = max_audio_bytes
        self._max_audio_chunks = max_audio_chunks
        self._debug_voice_logs = debug_voice_logs
        self._sessions: dict[tuple[str, str], _AudioSession] = {}

    async def handle(self, envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]:
        if envelope.type is RobotMessageType.AUDIO_START:
            return self._start(envelope)
        if envelope.type is RobotMessageType.AUDIO_CHUNK:
            return self._append_chunk(envelope)
        if envelope.type is RobotMessageType.AUDIO_END:
            return await self._complete(envelope)
        return ()

    def _start(self, envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]:
        codec = _payload_string(envelope, "codec")
        sample_rate_hz = _payload_positive_int(envelope, "sample_rate_hz")
        if codec is None or sample_rate_hz is None:
            return (self._error(envelope, "audio_chunk_invalid", "audio session is invalid"),)
        self._sessions[_session_key(envelope)] = _AudioSession(
            codec=codec,
            sample_rate_hz=sample_rate_hz,
            language=_payload_string(envelope, "language"),
            voice_id=_payload_string(envelope, "voice_id"),
            tts_model=_payload_string(envelope, "tts_model") or _DEFAULT_TTS_MODEL,
            chunks=[],
        )
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_audio_start device_id=%s session_id=%s message_id=%s "
                "codec=%s sample_rate_hz=%s language=%s voice_id=%s tts_model=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                codec,
                sample_rate_hz,
                _payload_string(envelope, "language"),
                _payload_string(envelope, "voice_id"),
                _payload_string(envelope, "tts_model") or _DEFAULT_TTS_MODEL,
            )
        return ()

    def _append_chunk(self, envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]:
        key = _session_key(envelope)
        session = self._sessions.get(key)
        if session is None:
            return (self._error(envelope, "audio_session_missing", "audio session is missing"),)
        chunk_b64 = _payload_string(envelope, "chunk_b64")
        try:
            decoded = base64.b64decode(chunk_b64 or "", validate=True)
        except (binascii.Error, ValueError):
            self._sessions.pop(key, None)
            return (self._error(envelope, "audio_chunk_invalid", "audio chunk is invalid"),)
        if not decoded or len(session.chunks) >= self._max_audio_chunks:
            self._sessions.pop(key, None)
            return (self._error(envelope, "audio_chunk_invalid", "audio chunk is invalid"),)
        if session.size_bytes + len(decoded) > self._max_audio_bytes:
            self._sessions.pop(key, None)
            return (self._error(envelope, "audio_too_large", "audio payload exceeds limit"),)
        session.chunks.append(decoded)
        session.size_bytes += len(decoded)
        return ()

    async def _complete(self, envelope: RobotEnvelope) -> tuple[RobotEnvelope, ...]:
        session = self._sessions.pop(_session_key(envelope), None)
        if session is None:
            return (self._error(envelope, "audio_session_missing", "audio session is missing"),)
        if not session.chunks:
            return (self._error(envelope, "audio_chunk_invalid", "audio chunk is invalid"),)
        try:
            transcript = await self._stt_provider.transcribe(
                VoiceAudio(
                    codec=session.codec,
                    sample_rate_hz=session.sample_rate_hz,
                    data=b"".join(session.chunks),
                    language=session.language,
                )
            )
        except ConnectionError:
            _LOGGER.warning(
                "robot_voice_asr_failed reason=asr_unavailable device_id=%s session_id=%s "
                "message_id=%s audio_bytes=%d audio_chunks=%d",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                session.size_bytes,
                len(session.chunks),
            )
            return (self._error(envelope, "asr_unavailable", "speech recognition is unavailable"),)
        except Exception:  # noqa: BLE001 - provider failures are a protocol boundary.
            _LOGGER.warning(
                "robot_voice_asr_failed reason=asr_failed device_id=%s session_id=%s "
                "message_id=%s audio_bytes=%d audio_chunks=%d",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                session.size_bytes,
                len(session.chunks),
            )
            return (self._error(envelope, "asr_failed", "speech recognition failed"),)
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_asr_done device_id=%s session_id=%s message_id=%s "
                "audio_codec=%s sample_rate_hz=%d audio_bytes=%d audio_chunks=%d "
                "asr_text_chars=%d asr_confidence=%s asr_text_preview=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                session.codec,
                session.sample_rate_hz,
                session.size_bytes,
                len(session.chunks),
                len(transcript.text),
                transcript.confidence,
                _preview(transcript.text),
            )
        speech = build_envelope(
            message_type=RobotMessageType.SPEECH_PARTIAL,
            device_id=envelope.device_id,
            session_id=envelope.session_id,
            payload={
                "text": transcript.text,
                "is_final": True,
                **({"confidence": transcript.confidence} if transcript.confidence is not None else {}),
            },
        )
        try:
            responses = await self._responder(speech)
        except Exception:  # noqa: BLE001 - responder error is returned as bounded ASR-independent error.
            _LOGGER.warning(
                "robot_voice_responder_failed device_id=%s session_id=%s message_id=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
            )
            return (speech, self._error(envelope, "asr_failed", "speech recognition failed"))
        assistant = next(
            (
                response
                for response in responses
                if response.type is RobotMessageType.ASSISTANT_TEXT_DONE
                and isinstance(response.payload.get("text"), str)
            ),
            None,
        )
        if assistant is None:
            _LOGGER.warning(
                "robot_voice_assistant_text_missing device_id=%s session_id=%s "
                "message_id=%s response_count=%d",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                len(responses),
            )
            return (speech, *responses)
        text = str(assistant.payload["text"])[:_MAX_TTS_TEXT_CHARS]
        options = VoiceSynthesisOptions(
            voice_id=_payload_string(envelope, "voice_id") or session.voice_id,
            model=_payload_string(envelope, "tts_model") or session.tts_model,
        )
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_tts_start device_id=%s session_id=%s message_id=%s "
                "tts_model=%s voice_id=%s assistant_text_chars=%d assistant_text_preview=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                options.model,
                options.voice_id,
                len(text),
                _preview(text),
            )
        try:
            audio = await self._tts_provider.synthesize(text, options)
        except ConnectionError:
            _LOGGER.warning(
                "robot_voice_tts_failed reason=tts_unavailable device_id=%s "
                "session_id=%s message_id=%s tts_model=%s voice_id=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                options.model,
                options.voice_id,
            )
            return (*((speech, *responses)), self._error(envelope, "tts_unavailable", "speech synthesis is unavailable"))
        except Exception:  # noqa: BLE001 - provider failures are a protocol boundary.
            _LOGGER.warning(
                "robot_voice_tts_failed reason=tts_failed device_id=%s session_id=%s "
                "message_id=%s tts_model=%s voice_id=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                options.model,
                options.voice_id,
            )
            return (*((speech, *responses)), self._error(envelope, "tts_failed", "speech synthesis failed"))
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_tts_done device_id=%s session_id=%s message_id=%s "
                "tts_codec=%s tts_audio_bytes=%d sample_rate_hz=%s",
                envelope.device_id,
                envelope.session_id,
                envelope.message_id,
                audio.codec,
                len(audio.data),
                audio.sample_rate_hz,
            )
        payload: dict[str, object] = {
            "codec": audio.codec,
            "sequence": 1,
            "chunk_b64": base64.b64encode(audio.data).decode("ascii"),
        }
        done_payload: dict[str, object] = {"codec": audio.codec, "total_chunks": 1}
        if audio.sample_rate_hz is not None:
            payload["sample_rate_hz"] = audio.sample_rate_hz
            done_payload["sample_rate_hz"] = audio.sample_rate_hz
        return (
            speech,
            *responses,
            build_envelope(
                message_type=RobotMessageType.TTS_AUDIO_CHUNK,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload=payload,
            ),
            build_envelope(
                message_type=RobotMessageType.TTS_AUDIO_DONE,
                device_id=envelope.device_id,
                session_id=envelope.session_id,
                payload=done_payload,
            ),
        )

    @staticmethod
    def _error(envelope: RobotEnvelope, code: str, message: str) -> RobotEnvelope:
        return build_envelope(
            message_type=RobotMessageType.ERROR,
            device_id=envelope.device_id,
            session_id=envelope.session_id,
            payload={"code": code, "message": message},
        )


def _session_key(envelope: RobotEnvelope) -> tuple[str, str]:
    return envelope.device_id, envelope.session_id


def _payload_string(envelope: RobotEnvelope, name: str) -> str | None:
    value = envelope.payload.get(name)
    return value if isinstance(value, str) and value else None


def _payload_positive_int(envelope: RobotEnvelope, name: str) -> int | None:
    value = envelope.payload.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _preview(text: str, *, max_chars: int = 160) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "..."

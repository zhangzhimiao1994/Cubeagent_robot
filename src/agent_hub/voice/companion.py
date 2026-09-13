from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable
from typing import Protocol
from uuid import UUID

from agent_hub.domain.runs import TaskMode

RobotTextResponder = Callable[..., str | Awaitable[str]]
_LOGGER = logging.getLogger(__name__)
_SAFE_CONVERSATION_PART = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_ROBOT_TEXT_CHARS = 1200


class RobotRunServiceProtocol(Protocol):
    def submit(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        message: str,
        mode: TaskMode,
        conversation_id: str | None = None,
        channel_context: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        **kwargs: object,
    ) -> object | Awaitable[object]: ...


class RobotRunRepositoryProtocol(Protocol):
    def artifacts(
        self,
        tenant_id: UUID,
        run_id: UUID,
    ) -> tuple[dict[str, object], ...] | Awaitable[tuple[dict[str, object], ...]]: ...


class CompanionResponder:
    """Replaceable bridge from a robot utterance to companion text."""

    def respond_text(
        self,
        utterance: str,
        *,
        device_id: str,
        session_id: str,
        message_id: str | None = None,
    ) -> str:
        del device_id, session_id, message_id
        return f"我听到了：{utterance}"


class RobotRunBridge:
    """Bridge robot final speech into the existing server-side Agent Run path."""

    def __init__(
        self,
        *,
        run_service: RobotRunServiceProtocol,
        run_repository: RobotRunRepositoryProtocol,
        tenant_id: UUID,
        actor_id: UUID | None = None,
        debug_voice_logs: bool = False,
    ) -> None:
        self._run_service = run_service
        self._run_repository = run_repository
        self._tenant_id = tenant_id
        self._actor_id = actor_id or tenant_id
        self._debug_voice_logs = debug_voice_logs

    async def respond_text(
        self,
        utterance: str,
        *,
        device_id: str,
        session_id: str,
        message_id: str | None = None,
    ) -> str:
        try:
            return await self._respond_text(
                utterance,
                device_id=device_id,
                session_id=session_id,
                message_id=message_id,
            )
        except Exception as error:  # noqa: BLE001 - robot voice must degrade safely.
            _LOGGER.warning(
                "robot_voice_fallback reason=bridge_exception error_type=%s "
                "device_id=%s session_id=%s message_id=%s",
                type(error).__name__,
                device_id,
                session_id,
                message_id,
            )
            return _fallback_text(None)

    async def _respond_text(
        self,
        utterance: str,
        *,
        device_id: str,
        session_id: str,
        message_id: str | None,
    ) -> str:
        utterance_digest = hashlib.sha256(utterance.encode("utf-8")).hexdigest()
        message_digest = _short_digest(message_id or "", utterance_digest)
        conversation_id = (
            f"robot-{_safe_conversation_part(device_id)}-{_safe_conversation_part(session_id)}"
        )
        idempotency_key = (
            f"robot:{_short_digest(device_id, length=12)}:"
            f"{_short_digest(session_id, length=12)}:{message_digest}"
        )
        channel_context = {
            "source_channel": "robot_voice",
            "channel_tenant_external_id": str(self._tenant_id),
            "channel_sender_external_id": device_id,
            "channel_conversation_external_id": session_id,
            "channel_message_id": message_id or utterance_digest[:32],
            "channel_event_id": idempotency_key,
            "channel_conversation_type": "voice_chat",
            "channel_entry_policy": "main_agent_decides",
            "requested_channel_features": "voice,audio,robot",
        }
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_run_submit device_id=%s session_id=%s message_id=%s "
                "conversation_id=%s utterance_chars=%d utterance_preview=%s",
                device_id,
                session_id,
                message_id,
                conversation_id,
                len(utterance),
                _preview(utterance),
            )
        submitted = await _maybe_await(
            self._run_service.submit(
                tenant_id=self._tenant_id,
                actor_id=self._actor_id,
                message=utterance,
                mode=TaskMode.AUTO,
                conversation_id=conversation_id,
                channel_context=channel_context,
                idempotency_key=idempotency_key,
            )
        )
        run_id = _run_id(submitted)
        execute = getattr(self._run_service, "execute", None)
        if run_id is not None and callable(execute):
            await _maybe_await(execute(run_id))
        if run_id is None:
            _LOGGER.warning(
                "robot_voice_fallback reason=run_id_missing device_id=%s "
                "session_id=%s message_id=%s conversation_id=%s",
                device_id,
                session_id,
                message_id,
                conversation_id,
            )
            return _fallback_text(None)
        text = await self._artifact_text(
            run_id,
            device_id=device_id,
            session_id=session_id,
            message_id=message_id,
        )
        if text is None:
            _LOGGER.warning(
                "robot_voice_fallback reason=run_artifact_missing device_id=%s "
                "session_id=%s message_id=%s conversation_id=%s run_id=%s",
                device_id,
                session_id,
                message_id,
                conversation_id,
                run_id,
            )
            return _fallback_text(run_id)
        return _bounded_robot_text(text)

    async def _artifact_text(
        self,
        run_id: UUID,
        *,
        device_id: str,
        session_id: str,
        message_id: str | None,
    ) -> str | None:
        artifacts = await _maybe_await(self._run_repository.artifacts(self._tenant_id, run_id))
        for index, artifact in reversed(tuple(enumerate(artifacts))):
            text = _artifact_text(artifact)
            if text is not None:
                if self._debug_voice_logs:
                    _LOGGER.info(
                        "robot_voice_run_artifact_selected device_id=%s session_id=%s "
                        "message_id=%s run_id=%s artifact_count=%d artifact_index=%d "
                        "response_chars=%d response_preview=%s",
                        device_id,
                        session_id,
                        message_id,
                        run_id,
                        len(artifacts),
                        index,
                        len(text),
                        _preview(text),
                    )
                return text
        if self._debug_voice_logs:
            _LOGGER.info(
                "robot_voice_run_artifact_missing device_id=%s session_id=%s "
                "message_id=%s run_id=%s artifact_count=%d",
                device_id,
                session_id,
                message_id,
                run_id,
                len(artifacts),
            )
        return None


async def _maybe_await(value: object | Awaitable[object]) -> object:
    if isawaitable(value):
        return await value
    return value


def _run_id(submitted: object) -> UUID | None:
    run_id = getattr(submitted, "id", None)
    return run_id if isinstance(run_id, UUID) else None


def _artifact_text(artifact: Mapping[str, object]) -> str | None:
    content = artifact.get("content")
    if isinstance(content, Mapping):
        text = _safe_text(content.get("text"))
        if text is not None:
            return text
    return (
        _safe_text(artifact.get("text"))
        or _safe_text(artifact.get("output"))
        or _safe_text(artifact.get("summary"))
    )


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _bounded_robot_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _MAX_ROBOT_TEXT_CHARS:
        return stripped
    return stripped[:_MAX_ROBOT_TEXT_CHARS].rstrip() + "\n\n……内容较长，已截断。"


def _fallback_text(run_id: UUID | None) -> str:
    lines = ["我已经收到你的语音，服务端 Agent 正在处理或暂时没有生成可播报结果。"]
    if run_id is not None:
        lines.append(f"Run ID: {run_id}")
    return "\n".join(lines)


def _preview(text: str, *, max_chars: int = 160) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "..."


def _safe_conversation_part(value: str) -> str:
    normalized = _SAFE_CONVERSATION_PART.sub("-", value.strip()).strip("-")
    return normalized or "unknown"


def _short_digest(*parts: str, length: int = 32) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(str(len(encoded)).encode("ascii"))
        digest.update(b":")
        digest.update(encoded)
    return digest.hexdigest()[:length]

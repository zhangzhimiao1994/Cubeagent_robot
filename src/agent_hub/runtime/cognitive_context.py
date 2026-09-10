"""Prompt bridge helpers for runtime-only cognitive guidance."""

from __future__ import annotations

from uuid import uuid4

from agent_hub.runtime.contracts import Artifact

_PRODUCER = "cognitive_context"
_TRUST = "internal_cognitive_guidance"
_CONTEXT_POLICY = "runtime_only"
_MAX_CONTEXT_BYTES = 6_000


def cognitive_context_artifact(text: str) -> Artifact | None:
    cleaned = _truncate_utf8(text.strip(), max_bytes=_MAX_CONTEXT_BYTES)
    if not cleaned:
        return None
    return Artifact(
        id=uuid4(),
        type="text",
        producer=_PRODUCER,
        content={
            "text": cleaned,
            "trust": _TRUST,
            "context_policy": _CONTEXT_POLICY,
        },
    )


def cognitive_context_text_from_artifacts(artifacts: tuple[Artifact, ...]) -> str:
    blocks: list[str] = []
    for artifact in artifacts:
        if not _is_cognitive_context_artifact(artifact):
            continue
        text = artifact.content.get("text")
        if isinstance(text, str) and text.strip():
            blocks.append(text.strip())
    return "\n".join(blocks)


def source_artifacts_without_cognitive_context(
    artifacts: tuple[Artifact, ...],
) -> tuple[Artifact, ...]:
    return tuple(
        artifact
        for artifact in artifacts
        if not _is_cognitive_context_artifact(artifact)
    )


def _is_cognitive_context_artifact(artifact: Artifact) -> bool:
    return (
        artifact.type == "text"
        and artifact.producer == _PRODUCER
        and artifact.content.get("trust") == _TRUST
        and artifact.content.get("context_policy") == _CONTEXT_POLICY
    )


def _truncate_utf8(text: str, *, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()


__all__ = [
    "cognitive_context_artifact",
    "cognitive_context_text_from_artifacts",
    "source_artifacts_without_cognitive_context",
]

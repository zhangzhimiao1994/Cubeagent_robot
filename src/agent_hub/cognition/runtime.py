"""Runtime-safe cognitive advice and outcome ingestion helpers."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Protocol
from uuid import UUID

from agent_hub.cognition.failure_learning import hermes_failure_observation
from agent_hub.cognition.router import render_cognitive_context
from agent_hub.cognition.types import CognitiveContextBundle
from agent_hub.domain.runs import RunStatus

_DEFAULT_ADVICE_TIMEOUT_SECONDS = 0.8
_DEFAULT_OUTCOME_TIMEOUT_SECONDS = 0.8
_FAILURE_FEEDBACK_TIMEOUT_SECONDS = 0.2
_LOGGER = logging.getLogger(__name__)


class CognitiveAdvisorProtocol(Protocol):
    async def advise(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        scene: str,
        current_request: str,
        conversation_id: str | None,
        run_id: UUID | None,
        limit: int = 8,
    ) -> CognitiveContextBundle: ...


class CognitiveOutcomeIngestProtocol(Protocol):
    async def ingest_run_outcome(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        run_id: UUID,
        status: str,
        request: str,
        routing_decision: dict[str, object],
    ) -> None: ...


class HermesFailureSinkProtocol(Protocol):
    def record_hermes_feedback(self, payload: dict[str, object]) -> object: ...


async def safe_cognitive_context_text(
    advisor: CognitiveAdvisorProtocol | None,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    scene: str,
    current_request: str,
    conversation_id: str | None = None,
    run_id: UUID | None = None,
    hermes_failure_sink: object | None = None,
    timeout_seconds: float = _DEFAULT_ADVICE_TIMEOUT_SECONDS,
    limit: int = 8,
) -> str:
    """Return rendered cognitive guidance while isolating all cognition failures."""

    if advisor is None:
        return ""
    try:
        bundle = await asyncio.wait_for(
            advisor.advise(
                tenant_id=tenant_id,
                user_id=user_id,
                scene=scene,
                current_request=current_request,
                conversation_id=conversation_id,
                run_id=run_id,
                limit=limit,
            ),
            timeout=timeout_seconds,
        )
        return render_cognitive_context(bundle)
    except TimeoutError:
        _LOGGER.warning("cognitive_advice_timeout failure_class=timeout")
        await _record_failure_observation(
            hermes_failure_sink,
            tenant_id=tenant_id,
            user_id=user_id,
            stage="advice",
            failure_class="timeout",
            impact="advice_skipped",
            strategy="fallback_to_memory_only",
        )
        return ""
    except Exception:  # noqa: BLE001 - isolate failures without logging private exception text
        _LOGGER.error("cognitive_advice_failed failure_class=unexpected_exception")
        await _record_failure_observation(
            hermes_failure_sink,
            tenant_id=tenant_id,
            user_id=user_id,
            stage="advice",
            failure_class="unexpected_exception",
            impact="advice_skipped",
            strategy="fallback_to_memory_only",
        )
        return ""


async def safe_cognitive_outcome_ingest(
    ingester: CognitiveOutcomeIngestProtocol | None,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    run_id: UUID,
    status: RunStatus,
    request: str,
    routing_decision: dict[str, object] | None,
    hermes_failure_sink: object | None = None,
    timeout_seconds: float = _DEFAULT_OUTCOME_TIMEOUT_SECONDS,
) -> None:
    """Best-effort outcome ingestion with Hermes-backed failure learning."""

    if ingester is None:
        return
    try:
        await asyncio.wait_for(
            ingester.ingest_run_outcome(
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                status=status.value,
                request=request,
                routing_decision={} if routing_decision is None else dict(routing_decision),
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        _LOGGER.warning("cognitive_outcome_ingest_timeout failure_class=timeout")
        await _record_failure_observation(
            hermes_failure_sink,
            tenant_id=tenant_id,
            user_id=user_id,
            stage="outcome_ingest",
            failure_class="timeout",
            impact="outcome_ingest_skipped",
            strategy="retry_later",
        )
    except Exception:  # noqa: BLE001 - isolate failures without logging private exception text
        _LOGGER.error("cognitive_outcome_ingest_failed failure_class=unexpected_exception")
        await _record_failure_observation(
            hermes_failure_sink,
            tenant_id=tenant_id,
            user_id=user_id,
            stage="outcome_ingest",
            failure_class="unexpected_exception",
            impact="outcome_ingest_skipped",
            strategy="retry_later",
        )


async def _record_failure_observation(
    sink: object | None,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    stage: str,
    failure_class: str,
    impact: str,
    strategy: str,
) -> None:
    if sink is None:
        return
    payload = hermes_failure_observation(
        stage=stage,
        failure_class=failure_class,
        impact=impact,
        strategy=strategy,
    )
    try:
        scoped_recorder = getattr(sink, "record_cognition_failure", None)
        if callable(scoped_recorder):
            result = scoped_recorder(
                tenant_id=tenant_id,
                user_id=user_id,
                stage=stage,
                failure_class=failure_class,
                impact=impact,
                strategy=strategy,
            )
        else:
            recorder = getattr(sink, "record_hermes_feedback", None)
            if not callable(recorder):
                return
            result = recorder(payload)
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=_FAILURE_FEEDBACK_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - failure recording is best effort only
        return


__all__ = [
    "CognitiveAdvisorProtocol",
    "CognitiveOutcomeIngestProtocol",
    "safe_cognitive_context_text",
    "safe_cognitive_outcome_ingest",
]

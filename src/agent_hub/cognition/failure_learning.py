from __future__ import annotations

import re

_SAFE_TOKEN = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_RAW_TOKEN_MARKERS = re.compile(
    r"\b(address|bearer|exception|password|profile|secret|token|traceback|transcript)\b|sk-[a-z0-9_-]+",
    re.IGNORECASE,
)


def _safe_token(value: str, *, fallback: str) -> str:
    normalized = "_".join(value.strip().casefold().replace("-", "_").split())
    if _RAW_TOKEN_MARKERS.search(value) is not None:
        return fallback
    if _SAFE_TOKEN.fullmatch(normalized) is None:
        return fallback
    return normalized


def hermes_failure_observation(
    stage: str,
    failure_class: str,
    impact: str,
    strategy: str,
) -> dict[str, object]:
    safe_stage = _safe_token(stage, fallback="unknown_stage")
    safe_failure_class = _safe_token(failure_class, fallback="unknown_failure")
    safe_impact = _safe_token(impact, fallback="unknown_impact")
    safe_strategy = _safe_token(strategy, fallback="unknown_strategy")
    return {
        "category": "scheduler",
        "outcome": "failure",
        "lesson": (
            f"cognition_failure stage={safe_stage} failure_class={safe_failure_class} "
            f"impact={safe_impact} strategy={safe_strategy}"
        ),
        "tags": ["cognition", "failure", safe_stage],
        "weight": 4,
    }


__all__ = ["hermes_failure_observation"]

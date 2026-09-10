from __future__ import annotations

from agent_hub.cognition.types import (
    CognitiveEpisode,
    CognitiveSource,
    EpisodeOutcome,
    EpisodeSignal,
    ExperienceRecord,
    ReflectionRecord,
    ReflectionTrigger,
    ReflectionType,
)


class ReflectionEngine:
    def reflect(
        self, episode: CognitiveEpisode, experience: ExperienceRecord | None = None
    ) -> ReflectionRecord:
        if not episode.evidence_refs:
            raise ValueError("reflection requires at least one evidence reference")

        reflection_type, trigger = _reflection_type_and_trigger(episode)
        return ReflectionRecord(
            episode_id=episode.id,
            reflection_type=reflection_type,
            trigger=trigger,
            what_happened=episode.summary,
            why_it_happened=_why(episode),
            better_next_time=_better_next_time(episode),
            candidate_experience_ids=(experience.id,) if experience is not None else (),
            confidence=0.72,
            requires_approval=False,
            evidence_refs=episode.evidence_refs,
        )


def _reflection_type_and_trigger(
    episode: CognitiveEpisode,
) -> tuple[ReflectionType, ReflectionTrigger]:
    signals = set(episode.signals)
    if episode.outcome is EpisodeOutcome.FAILURE or EpisodeSignal.TASK_FAILED in signals:
        return ReflectionType.COUNTERFACTUAL, ReflectionTrigger.TASK_FAILED
    if EpisodeSignal.USER_CORRECTED in signals:
        return ReflectionType.NEGATIVE, ReflectionTrigger.USER_CORRECTED
    if EpisodeSignal.USER_SATISFIED in signals:
        return ReflectionType.POSITIVE, ReflectionTrigger.USER_SATISFIED
    if episode.outcome is EpisodeOutcome.SUCCESS or EpisodeSignal.TASK_SUCCEEDED in signals:
        return ReflectionType.POSITIVE, ReflectionTrigger.TASK_SUCCEEDED
    if EpisodeSignal.REPEATED_PATTERN in signals or EpisodeSignal.USER_REPEATED_QUESTION in signals:
        return ReflectionType.CAUSAL, ReflectionTrigger.REPEATED_PATTERN
    return ReflectionType.MIXED, ReflectionTrigger.AGENT_UNCERTAIN


def _better_next_time(episode: CognitiveEpisode) -> str:
    summary = episode.summary.casefold()
    if "long" in summary and episode.source is CognitiveSource.VOICE:
        return "Use a shorter spoken answer first and ask before expanding."
    if "health check" in summary:
        return "Run or verify the health check before reporting deployment success."
    return "Identify the strongest signal, verify the next action, and keep the response focused."


def _why(episode: CognitiveEpisode) -> str:
    signal_class = _likely_signal_class(episode)
    outcome_class = episode.outcome.value
    source_class = episode.source.value
    return (
        f"Likely driven by signal class {signal_class} and outcome class "
        f"{outcome_class} from {source_class}."
    )


def _likely_signal_class(episode: CognitiveEpisode) -> str:
    if episode.signals:
        return episode.signals[0].value
    return "no_explicit_signal"

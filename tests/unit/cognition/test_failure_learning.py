from agent_hub.cognition.failure_learning import hermes_failure_observation


def test_cognitive_failure_observation_is_bounded_for_hermes() -> None:
    payload = hermes_failure_observation(
        stage="router",
        failure_class="timeout",
        impact="advice_skipped",
        strategy="fallback_to_memory_only",
    )

    assert payload["category"] == "scheduler"
    assert payload["outcome"] == "failure"
    assert payload["tags"] == ["cognition", "failure", "router"]
    assert payload["weight"] == 4
    assert payload["lesson"] == (
        "cognition_failure stage=router failure_class=timeout "
        "impact=advice_skipped strategy=fallback_to_memory_only"
    )


def test_cognitive_failure_observation_replaces_unsafe_tokens() -> None:
    payload = hermes_failure_observation(
        stage="Router crashed with bearer abcdefghijklmnopqrstuvwxyz",
        failure_class="Timeout: read raw exception from profile Alice",
        impact="Advice skipped; password=secret-value",
        strategy="Use transcript: user said their home address",
    )

    lesson = str(payload["lesson"])
    assert payload["tags"] == ["cognition", "failure", "unknown"]
    assert lesson == (
        "cognition_failure stage=unknown failure_class=unexpected_exception "
        "impact=unknown_impact strategy=require_review"
    )
    assert "abcdefghijklmnopqrstuvwxyz" not in lesson
    assert "secret-value" not in lesson
    assert "home address" not in lesson


def test_cognitive_failure_observation_replaces_unsafe_underscore_tokens() -> None:
    payload = hermes_failure_observation(
        stage="bearer_abc",
        failure_class="exception_timeout",
        impact="profile_alice",
        strategy="token_leaked",
    )

    assert payload["tags"] == ["cognition", "failure", "unknown"]
    assert payload["lesson"] == (
        "cognition_failure stage=unknown failure_class=unexpected_exception "
        "impact=unknown_impact strategy=require_review"
    )


def test_cognitive_failure_observation_allows_canonical_classification_tokens() -> None:
    payload = hermes_failure_observation(
        stage="router",
        failure_class="unexpected_exception",
        impact="advice_skipped",
        strategy="require_review",
    )

    assert payload["lesson"] == (
        "cognition_failure stage=router failure_class=unexpected_exception "
        "impact=advice_skipped strategy=require_review"
    )

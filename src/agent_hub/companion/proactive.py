from __future__ import annotations

from agent_hub.companion.types import CompanionState


class ProactiveEngine:
    """Suggest optional companion nudges (Phase 2 seed)."""

    def suggest_next_nudge(self, state: CompanionState) -> str | None:
        if state.scene == "idle_chat" and state.relationship_level >= 10:
            return "好久没聊了，今天过得怎么样？"
        return None

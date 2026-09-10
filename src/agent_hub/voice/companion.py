from __future__ import annotations


class CompanionResponder:
    """Replaceable bridge from a robot utterance to companion text."""

    def respond_text(self, utterance: str, *, device_id: str, session_id: str) -> str:
        del device_id, session_id
        return f"我听到了：{utterance}"

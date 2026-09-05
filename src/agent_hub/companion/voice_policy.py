from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_hub.companion.types import CompanionState


class VoiceReplyPolicy(BaseModel):
    """How the backend should speak for Pi playback."""

    model_config = ConfigDict(extra="forbid", strict=True)

    max_spoken_sentences: int = Field(default=3, ge=1, le=8)
    style: str = Field(default="warm_companion", min_length=1, max_length=64)
    allow_questions: bool = True
    avoid_ops_jargon: bool = True


def build_voice_system_prompt(state: CompanionState, policy: VoiceReplyPolicy | None = None) -> str:
    """System prompt for human-like voice companionship."""

    policy = policy or VoiceReplyPolicy()
    return (
        "你是一个智能语音陪伴伙伴，用自然口语和用户聊天。"
        f"人格={state.persona_id}，心情={state.mood}，场景={state.scene}，"
        f"关系亲密度={state.relationship_level}/100。"
        f"每次回复尽量不超过{policy.max_spoken_sentences}句短口语。"
        "可以关心用户，引用已记住的事实，但不要背诵列表。"
        "如果用户打断了你，直接接新话题，不要解释技术细节。"
        + ("不要说工作台、调度、工具调用等运维术语。" if policy.avoid_ops_jargon else "")
    )


def trim_for_speech(text: str, *, max_sentences: int = 3) -> str:
    parts = [p.strip() for p in text.replace("!", "。").replace("?", "？").split("。") if p.strip()]
    if not parts:
        return text.strip()
    clipped = parts[:max_sentences]
    return "。".join(clipped) + ("。" if clipped else "")

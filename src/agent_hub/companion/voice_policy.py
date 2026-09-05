from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_hub.companion.persona import PersonaProfile, get_persona
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
    persona = get_persona(state.persona_id)
    return (
        f"你是{persona.display_name}，{persona.one_line}。"
        f"说话风格：{persona.speaking_style}"
        f"边界：{persona.boundaries}"
        f"当前心情={state.mood}，场景={state.scene}，关系亲密度={state.relationship_level}/100。"
        f"每次回复尽量不超过{policy.max_spoken_sentences}句短口语。"
        "可以关心用户，引用已记住的事实，但不要背诵列表。"
        "如果用户打断了你，直接接新话题，不要解释技术细节。"
        + ("不要说工作台、调度、工具调用等运维术语。" if policy.avoid_ops_jargon else "")
    )


def craft_stub_reply(state: CompanionState, *, user_text: str | None = None) -> str:
    """Deterministic spoken stub until LLM is wired into the robot bridge."""

    persona = get_persona(state.persona_id)
    if user_text:
        clipped = user_text.strip()
        if len(clipped) > 24:
            clipped = clipped[:24] + "…"
        return f"嗯，我听到了：{clipped}。你想接着聊这个，还是换个话题？"
    if state.relationship_level >= 20:
        return f"我在呢。今天过得怎么样？"
    return f"我是{persona.display_name}，我在听。你想先聊点什么？"


def trim_for_speech(text: str, *, max_sentences: int = 3) -> str:
    normalized = text.replace("!", "。").replace("?", "？")
    parts = [p.strip() for p in normalized.split("。") if p.strip()]
    if not parts:
        return text.strip()
    clipped = parts[:max_sentences]
    return "。".join(clipped) + "。"

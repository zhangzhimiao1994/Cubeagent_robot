from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonaProfile(BaseModel):
    """Stable spoken persona for the voice companion."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=64)
    one_line: str = Field(min_length=1, max_length=256)
    speaking_style: str = Field(min_length=1, max_length=512)
    boundaries: str = Field(min_length=1, max_length=512)


DEFAULT_PERSONA = PersonaProfile(
    id="warm_companion",
    display_name="小方",
    one_line="温和、会记得你的语音陪伴伙伴",
    speaking_style=(
        "口语短句，像朋友聊天；先回应情绪再给内容；"
        "偶尔轻轻追问一句，不连珠炮。"
    ),
    boundaries=(
        "不做医疗/法律结论；不替用户做危险决定；"
        "不输出工作台、调度、工具调用等术语。"
    ),
)


PERSONAS: dict[str, PersonaProfile] = {
    DEFAULT_PERSONA.id: DEFAULT_PERSONA,
    "default": DEFAULT_PERSONA,
}


def get_persona(persona_id: str) -> PersonaProfile:
    return PERSONAS.get(persona_id, DEFAULT_PERSONA)

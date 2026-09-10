"""In-memory playback recorder for dry runs."""

from dataclasses import dataclass, field


@dataclass
class PlaybackRecorder:
    texts: list[str] = field(default_factory=list)

    def play(self, text: str) -> None:
        self.texts.append(text)

from __future__ import annotations

from enum import StrEnum


class RouteTarget(StrEnum):
    EDGE = "edge"
    CLOUD = "cloud"


class EdgeCloudRouter:
    """Phase-1 stub: always cloud unless prefer_edge_model is set."""

    def __init__(self, *, prefer_edge_model: bool = False) -> None:
        self._prefer_edge = prefer_edge_model

    def choose(self, *, text_len: int = 0, needs_tools: bool = False) -> RouteTarget:
        if needs_tools:
            return RouteTarget.CLOUD
        if self._prefer_edge and text_len < 80:
            return RouteTarget.EDGE
        return RouteTarget.CLOUD

from __future__ import annotations

import uuid

from robot_runtime.audio import (
    AudioCapture,
    AudioPlayback,
    NullAudioCapture,
    NullAudioPlayback,
    PassthroughEchoCanceller,
)
from robot_runtime.bridge import Envelope, LoggingBridgeClient
from robot_runtime.config import RuntimeConfig
from robot_runtime.router import EdgeCloudRouter
from robot_runtime.session import InteractionLoop, LocalSession, LoopState
from robot_runtime.vad import EnergyTurnTaking, SimpleBargeIn


class RobotRuntime:
    """On-device system wiring for Raspberry Pi companion."""

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        capture: AudioCapture | None = None,
        playback: AudioPlayback | None = None,
    ) -> None:
        self.config = config or RuntimeConfig()
        self.capture = capture or NullAudioCapture()
        self.playback = playback or NullAudioPlayback()
        self.aec = PassthroughEchoCanceller()
        self.turn_taking = EnergyTurnTaking()
        self.barge_in = SimpleBargeIn()
        self.bridge = LoggingBridgeClient(self.config)
        self.router = EdgeCloudRouter(prefer_edge_model=self.config.prefer_edge_model)
        self.session = LocalSession()
        self.loop = InteractionLoop()

    async def start(self) -> None:
        await self.capture.start()
        await self.playback.start()
        await self.bridge.connect()
        await self.bridge.send(
            Envelope(
                type="hello",
                payload={
                    "device_id": self.config.device_id,
                    "capabilities": ["vad", "barge_in", "pcm16"],
                },
            )
        )

    async def stop(self) -> None:
        await self.bridge.close()
        await self.playback.stop()
        await self.capture.stop()

    async def on_frame(self, pcm: bytes, *, energy: float | None = None) -> None:
        cleaned = self.aec.process(pcm)
        decision = self.turn_taking.observe(cleaned, energy=energy)
        if decision.speech_active and self.loop.state is LoopState.IDLE:
            self.loop.on_speech_start()
            self.session.turn_id = str(uuid.uuid4())
            await self.bridge.send(
                Envelope(type="utterance.start", turn_id=self.session.turn_id)
            )
        if self.loop.state is LoopState.CAPTURING and self.session.turn_id:
            await self.bridge.send(
                Envelope(
                    type="utterance.audio",
                    turn_id=self.session.turn_id,
                    payload={"bytes": len(cleaned)},
                )
            )
        if (
            self.config.enable_barge_in
            and self.barge_in.should_interrupt(
                speech_active=decision.speech_active,
                assistant_playing=self.playback.is_playing,
            )
        ):
            await self.playback.clear()
            self.loop.on_barge_in()
            await self.bridge.send(
                Envelope(type="barge_in", turn_id=self.session.turn_id)
            )
        if decision.turn_ended and self.session.turn_id:
            self.loop.on_turn_end()
            await self.bridge.send(
                Envelope(
                    type="utterance.end",
                    turn_id=self.session.turn_id,
                    payload={"route": self.router.choose().value},
                )
            )

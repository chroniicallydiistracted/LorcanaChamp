from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .ids import CardId, InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class CardInstance:
    """Runtime card instance.

    v2 treats instance state as the source for zone/controller/damage/exertion
    queries.  Card definition data lives in ``CardCatalog``.
    """
    instance_id: InstanceId
    card_id: CardId
    owner: PlayerId
    controller: PlayerId
    zone: str
    damage: int = 0
    exerted: bool = False
    drying: bool = False
    location_instance_id: InstanceId | None = None
    stack_parent_id: InstanceId | None = None
    cards_under: tuple[InstanceId, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_updates(self, **updates: Any) -> "CardInstance":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0
    deck: tuple[InstanceId, ...] = ()
    hand: tuple[InstanceId, ...] = ()
    play: tuple[InstanceId, ...] = ()
    discard: tuple[InstanceId, ...] = ()
    inkwell: tuple[InstanceId, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchState:
    """Immutable match state for v2 transitions."""
    players: tuple[PlayerState, PlayerState]
    cards: dict[InstanceId, CardInstance] = field(default_factory=dict)
    active_player: PlayerId = PlayerId(0)
    turn_number: int = 1
    phase: str = "main"
    seed: str = "v2-default-seed"
    winner: PlayerId | None = None
    event_log: tuple[Any, ...] = ()
    turn_metrics: dict[str, Any] = field(default_factory=dict)

    def opponent(self, player: PlayerId) -> PlayerId:
        return PlayerId(1 if int(player) == 0 else 0)

    def player(self, player: PlayerId) -> PlayerState:
        return self.players[int(player)]

    @staticmethod
    def empty() -> "MatchState":
        return MatchState(players=(PlayerState(PlayerId(0)), PlayerState(PlayerId(1))))

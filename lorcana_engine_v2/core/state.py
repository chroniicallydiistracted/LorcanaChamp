from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .ids import InstanceId, PlayerId
from .zones import ZoneRuntimeState, build_zone_registry, initialize_zone_state_from_registry, LORCANA_RUNTIME_ZONES


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0

    def with_updates(self, **updates: Any) -> "PlayerState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class TurnMetadata:
    """Serializable turn metadata owned by the Lorcana game layer.

    Lorcanito records cards inked this turn in `G.turnMetadata.inkedThisTurn`.
    v2 keeps the same concept explicit so moves can enforce once-per-turn rules
    without storing transient rule state in card definitions or zone records.
    """
    inked_this_turn: tuple[InstanceId, ...] = ()

    def record_ink(self, card_id: InstanceId | str) -> "TurnMetadata":
        cid = InstanceId(str(card_id))
        if cid in self.inked_this_turn:
            return self
        return replace(self, inked_this_turn=self.inked_this_turn + (cid,))

    def reset_for_new_turn(self) -> "TurnMetadata":
        return TurnMetadata()


@dataclass(frozen=True, slots=True)
class FrameworkState:
    """Serializable framework-owned match state.

    Mirrors Lorcanito's framework/game split at v2 scale: zones, priority-like
    active player, state ID, and phase live here, not in static card definitions.
    """
    player_ids: tuple[PlayerId, PlayerId]
    zones: ZoneRuntimeState
    state_id: int = 0
    active_player: PlayerId = PlayerId("p0")
    turn_number: int = 1
    phase: str = "main"
    seed: str = "v2-default-seed"
    winner: PlayerId | None = None

    def with_updates(self, **updates: Any) -> "FrameworkState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class GameState:
    """Game-owned serializable state.

    Phase 2 adds explicit turn metadata for the first real move. Future phases
    will add bag, pending effects, replacement effects, and floating triggers.
    """
    players: Mapping[PlayerId, PlayerState]
    turn_metadata: TurnMetadata = field(default_factory=TurnMetadata)
    event_log: tuple[Any, ...] = ()
    turn_metrics: Mapping[str, Any] = field(default_factory=dict)

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.players[PlayerId(str(player))]

    def with_updates(self, **updates: Any) -> "GameState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class MatchState:
    """Authoritative v2 match state envelope.

    Static card identity is deliberately not stored here. Resolve instance IDs
    through MatchStaticResources.instances, then CardCatalog.
    """
    framework: FrameworkState
    game: GameState

    def opponent(self, player: PlayerId | str) -> PlayerId:
        player_id = PlayerId(str(player))
        for candidate in self.framework.player_ids:
            if candidate != player_id:
                return candidate
        raise ValueError(f"Unknown player id: {player}")

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.game.player(player)

    @staticmethod
    def empty(player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1"))) -> "MatchState":
        registry = build_zone_registry(LORCANA_RUNTIME_ZONES, player_ids)
        zones = initialize_zone_state_from_registry(registry)
        return MatchState(
            framework=FrameworkState(player_ids=player_ids, zones=zones, active_player=player_ids[0]),
            game=GameState(players={player_id: PlayerState(player_id) for player_id in player_ids}),
        )
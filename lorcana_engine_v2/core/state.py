from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .ids import PlayerId
from .zones import ZoneRuntimeState, build_zone_registry, initialize_zone_state_from_registry, LORCANA_RUNTIME_ZONES


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0

    def with_updates(self, **updates: Any) -> "PlayerState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class FrameworkState:
    """Serializable framework-owned match state.

    Mirrors Lorcanito's TCGCtx split at v2 scale: zones and runtime indexing live
    here, not in static card definitions.
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

    This intentionally stays small in Phase 1.  Future phases will add bag,
    pending effects, turn metrics, replacements, and floating triggers here.
    """
    players: Mapping[PlayerId, PlayerState]
    event_log: tuple[Any, ...] = ()
    turn_metrics: Mapping[str, Any] = field(default_factory=dict)

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.players[PlayerId(str(player))]

    def with_updates(self, **updates: Any) -> "GameState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class MatchState:
    """Authoritative v2 match state envelope.

    Static card identity is deliberately not stored here.  Resolve instance IDs
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

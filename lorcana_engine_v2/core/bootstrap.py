from __future__ import annotations

from .ids import PlayerId
from .runtime_config import MatchInitContext, Player, initialize_match_state
from .state import MatchState
from .static_resources import MatchStaticResources
from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config


def initialize_match_state_from_static_resources(
    resources: MatchStaticResources,
    player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1")),
    *,
    seed: str = "v2-default-seed",
    match_id: str | None = None,
    game_id: str | None = None,
    choosing_first_player: PlayerId | None = None,
) -> MatchState:
    result = initialize_match_state(
        MatchInitContext(
            config=lorcana_runtime_config,
            players=tuple(Player(id=player_id) for player_id in player_ids),
            staticResources=resources,
            seed=seed,
            matchID=match_id,
            gameID=game_id,
            choosingFirstPlayer=choosing_first_player,
        )
    )
    return result.state

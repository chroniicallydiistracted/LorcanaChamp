from __future__ import annotations

from .ids import PlayerId
from .state import FrameworkState, GameState, MatchState, PlayerState
from .static_resources import MatchStaticResources
from .zones import build_zone_registry, initialize_zone_state_from_registry, put_cards_in_zone, scoped_zone


def initialize_match_state_from_static_resources(
    resources: MatchStaticResources,
    player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1")),
    *,
    seed: str = "v2-default-seed",
    active_player: PlayerId | None = None,
    shuffle: bool = False,
) -> MatchState:
    """Create an initial MatchState with each owner's instances in deck.

    Phase 1 intentionally keeps order deterministic by default.  Future runtime
    random APIs can supply Lorcanito-style seeded shuffling at game start.
    """
    registry = build_zone_registry(resources.zone_definitions, player_ids)
    zones = initialize_zone_state_from_registry(registry)

    records_by_owner = {player_id: [] for player_id in player_ids}
    for record in resources.instances.entries():
        owner_id = record.owner_id
        if owner_id not in records_by_owner:
            raise ValueError(f"CARDS_MAPS_INVALID: owner '{owner_id}' is not a match player")
        records_by_owner[owner_id].append(record.instance_id)

    for player_id in player_ids:
        instance_ids = tuple(records_by_owner[player_id])
        if shuffle:
            # Placeholder hook.  Do not silently randomize until v2 has a seeded
            # random API matching Lorcanito's runtime random service.
            raise NotImplementedError("v2 seeded shuffle is not implemented yet")
        zones = put_cards_in_zone(
            zones,
            zone_key=scoped_zone("deck", player_id),
            card_ids=instance_ids,
            owner_id=player_id,
            controller_id=player_id,
        )

    active = active_player if active_player is not None else player_ids[0]
    return MatchState(
        framework=FrameworkState(player_ids=player_ids, zones=zones, active_player=active, seed=seed),
        game=GameState(players={player_id: PlayerState(player_id) for player_id in player_ids}),
    )

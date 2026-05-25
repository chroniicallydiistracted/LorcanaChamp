from __future__ import annotations

from lorcana_engine_v2.core.runtime_config import BoardSetupContext, MatchRuntimeConfig, SetupArgs
from lorcana_engine_v2.core.state import MatchState, create_initial_lorcana_g
from lorcana_engine_v2.core.view_filter import ViewRoleContext, filter_match_view
from lorcana_engine_v2.core.zones import (
    LORCANA_RUNTIME_ZONES,
    PublicZoneSummary,
    ZoneCardIndexEntry,
    ZoneRuntimePrivateState,
    ZoneRuntimePublicState,
    ZoneRuntimeState,
    build_zone_registry,
    scoped_zone,
)
from lorcana_engine_v2.flow.runtime_flow_config import lorcana_runtime_flow
from lorcana_engine_v2.moves.ink import PUT_CARD_INTO_INKWELL, PutCardIntoInkwellMove
from lorcana_engine_v2.moves.setup import ALTER_HAND, CHOOSE_WHO_GOES_FIRST, AlterHandMove, ChooseWhoGoesFirstMove
from lorcana_engine_v2.rules.queries import create_lorcana_runtime_card_deriver


lorcana_runtime_zones = LORCANA_RUNTIME_ZONES


def setup_lorcana_g(args: SetupArgs):
    if len(args.players) != 2:
        raise ValueError("Lorcana requires exactly 2 players")
    return create_initial_lorcana_g(args.players[0].id, args.players[1].id)


def board_setup(state: MatchState, ctx: BoardSetupContext) -> MatchState:
    zone_cards = {zone_id: tuple(card_ids) for zone_id, card_ids in state.ctx.zones.private.zoneCards.items()}
    card_index = dict(state.ctx.zones.private.cardIndex)
    card_meta = dict(state.ctx.zones.private.cardMeta)
    zone_summaries = dict(state.ctx.zones.public.zoneSummaries)

    for player in ctx.players:
        deck_zone_id = scoped_zone("deck", player.id)
        deck_cards = list(zone_cards.get(deck_zone_id, ()))
        instance_ids = [
            record.instance_id
            for record in ctx.staticResources.instances.entries()
            if record.owner_id == player.id
        ]
        shuffled_ids = ctx.random.shuffle(instance_ids)
        for card_id in shuffled_ids:
            deck_cards.append(card_id)
            card_index[card_id] = ZoneCardIndexEntry(
                zoneKey=deck_zone_id,
                index=len(deck_cards) - 1,
                ownerID=player.id,
                controllerID=player.id,
            )
        zone_cards[deck_zone_id] = tuple(deck_cards)
        zone_summaries[deck_zone_id] = PublicZoneSummary(
            revision=1,
            count=len(deck_cards),
            topPublicCardID=None,
        )

    zones = ZoneRuntimeState(
        public=ZoneRuntimePublicState(zoneSummaries=zone_summaries),
        reveals=state.ctx.zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zone_cards,
            cardIndex=card_index,
            cardMeta=card_meta,
        ),
    )
    return MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))


def lorcana_player_view(state: MatchState, role_ctx: ViewRoleContext):
    return filter_match_view(
        state,
        role_ctx,
        build_zone_registry(lorcana_runtime_zones, state.ctx.playerIds),
    )


lorcana_runtime_config = MatchRuntimeConfig(
    name="Disney Lorcana TCG",
    moves={
        CHOOSE_WHO_GOES_FIRST: ChooseWhoGoesFirstMove(),
        ALTER_HAND: AlterHandMove(),
        PUT_CARD_INTO_INKWELL: PutCardIntoInkwellMove(),
    },
    flow=lorcana_runtime_flow,
    zones=lorcana_runtime_zones,
    setup=setup_lorcana_g,
    boardSetup=board_setup,
    playerView=lorcana_player_view,
    projectBoard=None,
    deriveRuntimeCard=create_lorcana_runtime_card_deriver(),
    derivePacketAnimations=None,
)

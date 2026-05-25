from lorcana_engine_v2.core.ids import InstanceId
from lorcana_engine_v2.core.zones import CardMeta, ZoneRuntimePrivateState, ZoneRuntimeState
from lorcana_engine_v2.effects.continuous_effects import add_stat_modifier_effect
from lorcana_engine_v2.effects.temporary_effects import (
    add_temporary_keyword,
    cleanup_expired_effects,
    has_temporary_keyword,
    prune_expired_temporary_effects,
)

from .helpers import context_for, resources_for, state_with_play


def test_temporary_keyword_appears_in_runtime_card_until_pruned():
    resources = resources_for({"hero": "Y1z"})
    state = state_with_play(resources, p0=("hero",))
    state = type(state)(
        G=state.G,
        ctx=state.ctx.with_updates(status=state.ctx.status.with_updates(turn=1)),
    )
    meta = add_temporary_keyword(CardMeta(), "Rush", expires_at_turn=1)
    zones = ZoneRuntimeState(
        public=state.ctx.zones.public,
        reveals=state.ctx.zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=state.ctx.zones.private.zoneCards,
            cardIndex=state.ctx.zones.private.cardIndex,
            cardMeta={**state.ctx.zones.private.cardMeta, InstanceId("hero"): meta},
        ),
    )
    state = type(state)(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    ctx = context_for(resources)

    card = ctx.query.runtime_card(state, "hero")
    assert "Rush" in card.keywords
    assert has_temporary_keyword(meta, 1, "Rush")

    pruned = prune_expired_temporary_effects(meta, 2)
    assert pruned.temporaryKeywords is None


def test_continuous_stat_modifier_affects_real_runtime_card_and_cleanup_expires_it():
    resources = resources_for({"hero": "Y1z"})
    state = state_with_play(resources, p0=("hero",))
    state = type(state)(
        G=state.G,
        ctx=state.ctx.with_updates(status=state.ctx.status.with_updates(turn=1)),
    )
    ctx = context_for(resources)
    base_strength = ctx.query.runtime_card(state, "hero").strength

    state, effect = add_stat_modifier_effect(
        state,
        source_id="hero",
        target_id="hero",
        stat="strength",
        modifier=2,
        duration="this-turn",
    )

    assert effect.id == "ce_1"
    assert ctx.query.runtime_card(state, "hero").strength == base_strength + 2

    next_turn = type(state)(
        G=state.G,
        ctx=state.ctx.with_updates(status=state.ctx.status.with_updates(turn=2)),
    )
    cleaned = cleanup_expired_effects(next_turn, 2)

    assert cleaned.G.continuousEffects.instances == ()
    assert ctx.query.runtime_card(cleaned, "hero").strength == base_strength

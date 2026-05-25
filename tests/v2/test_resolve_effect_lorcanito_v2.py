from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    create_pending_action_effect,
    enqueue_pending_action_effect,
    resolve_pending_action_effect,
)

from .helpers import resources_for, state_with_play


def test_resolve_pending_action_effect_consumes_choice_and_resumes_effect_resolution():
    resources = resources_for({"aladdin": "ZTM"})
    state = state_with_play(resources, p0=("aladdin",))
    state = type(state)(
        G=state.G.with_updates(lore={PlayerId("p0"): 0, PlayerId("p1"): 3}),
        ctx=state.ctx,
    )
    pending = create_pending_action_effect(
        state,
        kind="optional-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={
            "playerId": PlayerId("p0"),
            "cardId": "aladdin",
            "cardType": "character",
            "costType": "free",
        },
        effect={
            "type": "optional",
            "effect": {"type": "lose-lore", "target": "EACH_OPPONENT", "amount": 1},
        },
    )
    state = enqueue_pending_action_effect(state, pending)

    result = resolve_pending_action_effect(
        state,
        effect_id=pending.id,
        player_id="p0",
        params={"resolveOptional": True},
        resolver=lambda next_state, pending_effect, resolution_input: resolve_action_effect(
            next_state,
            pending_effect.cardPlayed,
            pending_effect.effect,
            resolution_input,
        ),
    )

    assert result.status == "resolved"
    assert result.state.G.pendingEffects == ()
    assert result.state.ctx.priority.pendingChoice is None
    assert result.state.G.lore[PlayerId("p1")] == 2


def test_action_effect_with_missing_chosen_target_suspends_into_pending_effect():
    resources = resources_for({"aladdin": "ZTM"})
    state = state_with_play(resources, p0=("aladdin",))

    result = resolve_action_effect(
        state,
        {
            "playerId": PlayerId("p0"),
            "cardId": "aladdin",
            "cardType": "character",
            "costType": "free",
        },
        {"type": "banish", "target": "CHOSEN_CHARACTER"},
    )

    assert result.status == "suspended"
    assert result.pendingEffect is not None
    assert result.pendingEffect.kind == "target-selection"
    assert result.state.G.pendingEffects == (result.pendingEffect,)

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.resolution.pending import (
    create_pending_action_effect,
    enqueue_pending_action_effect,
    move_suspended_action_card_to_limbo,
    validate_pending_choice_input,
)

from .helpers import resources_for, state_with_play


def test_pending_action_effect_enqueue_sets_lorcanito_pending_effect_and_priority_choice():
    resources = resources_for({"action": "YDE"})
    state = state_with_play(resources, p0=("action",))
    pending = create_pending_action_effect(
        state,
        kind="target-selection",
        sourceCardId="action",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={
            "playerId": PlayerId("p0"),
            "cardId": InstanceId("action"),
            "cardType": "action",
            "costType": "ink",
        },
        effect={"type": "draw", "amount": 1},
    )

    state = enqueue_pending_action_effect(state, pending)

    assert state.G.pendingEffects == (pending,)
    assert state.ctx.priority.pendingChoice is not None
    assert state.ctx.priority.pendingChoice.type == "action-effect"
    assert state.ctx.priority.pendingChoice.playerID == PlayerId("p0")
    assert state.ctx.priority.pendingChoice.requestID == pending.id


def test_validate_pending_choice_and_move_suspended_real_action_to_limbo():
    resources = resources_for({"action": "YDE"})
    state = state_with_play(resources, p0=("action",))
    pending = create_pending_action_effect(
        state,
        kind="target-selection",
        sourceCardId="action",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={
            "playerId": PlayerId("p0"),
            "cardId": InstanceId("action"),
            "cardType": "action",
            "costType": "ink",
        },
        effect={"type": "draw", "amount": 1},
    )
    state = enqueue_pending_action_effect(state, pending)

    assert validate_pending_choice_input(
        state,
        player_id="p0",
        effect_id=pending.id,
        params={"targets": []},
    ).valid
    assert not validate_pending_choice_input(
        state,
        player_id="p1",
        effect_id=pending.id,
    ).valid

    state = move_suspended_action_card_to_limbo(state, pending.cardPlayed)

    assert state.ctx.zones.private.cardIndex[InstanceId("action")].zoneKey == scoped_zone("limbo", "p0")
    assert state.ctx.zones.private.cardMeta[InstanceId("action")].publicFaceState == "faceUp"

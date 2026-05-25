from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.moves.resolve_pending import RESOLVE_EFFECT
from lorcana_engine_v2.resolution.action_effects import resolve_action_effect
from lorcana_engine_v2.resolution.pending import (
    create_pending_action_effect,
    enqueue_pending_action_effect,
    resolve_pending_action_effect,
)

from .helpers import resources_for, state_with_play


def _main_state(state):
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(
                turn=1,
                gameSegment="mainGame",
                phase="main",
                turnOwnerId=PlayerId("p0"),
            ),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )


def _resolve_command(effect_id, params=None, **top_level):
    args = {"effectId": effect_id, **top_level}
    if params is not None:
        args["params"] = params
    return CommandEnvelope(
        commandID=f"resolve-{effect_id}",
        move=RESOLVE_EFFECT,
        input=MoveInput(args=args),
    )


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


def test_resolve_effect_command_requires_effect_id():
    resources = resources_for({"aladdin": "ZTM"})
    runtime = MatchRuntime(resources)
    runtime.load_state(_main_state(state_with_play(resources, p0=("aladdin",))))

    result = runtime.process_command(
        CommandEnvelope(commandID="resolve-missing", move=RESOLVE_EFFECT, input=MoveInput(args={"params": {}})),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.errorCode == "RESOLVE_EFFECT_ID_REQUIRED"


def test_resolve_effect_command_uses_lorcanito_params_shape_not_top_level_targets():
    resources = resources_for({"aladdin": "ZTM", "target": "Y1z"}, owners={"p0": ("aladdin",), "p1": ("target",)})
    state = _main_state(state_with_play(resources, p0=("aladdin",), p1=("target",)))
    pending = create_pending_action_effect(
        state,
        kind="target-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": "aladdin", "cardType": "character", "costType": "free"},
        effect={"type": "banish", "target": "CHOSEN_OPPOSING_CHARACTER"},
    )
    state = enqueue_pending_action_effect(state, pending)
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    legacy = runtime.process_command(_resolve_command(pending.id, targets=["target"]), "p0", actor_role="player")

    assert legacy.success is False
    assert legacy.errorCode == "RESOLVE_EFFECT_PARAMS_REQUIRED"

    runtime.load_state(state)
    result = runtime.process_command(_resolve_command(pending.id, params={"targets": ["target"]}), "p0", actor_role="player")

    assert result.success is True
    assert result.state.G.pendingEffects == ()


def test_resolve_effect_wrong_pending_chooser_cannot_resolve():
    resources = resources_for({"aladdin": "ZTM"})
    state = _main_state(state_with_play(resources, p0=("aladdin",)))
    pending = create_pending_action_effect(
        state,
        kind="optional-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p1",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": "aladdin", "cardType": "character", "costType": "free"},
        effect={"type": "optional", "effect": {"type": "gain-lore", "target": "CONTROLLER", "amount": 1}},
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(enqueue_pending_action_effect(state, pending))

    result = runtime.process_command(_resolve_command(pending.id, params={"resolveOptional": True}), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "RESOLVE_EFFECT_WRONG_PLAYER"


def test_resolve_effect_choice_selection_requires_choice_index():
    resources = resources_for({"aladdin": "ZTM"})
    state = _main_state(state_with_play(resources, p0=("aladdin",)))
    pending = create_pending_action_effect(
        state,
        kind="choice-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": "aladdin", "cardType": "character", "costType": "free"},
        effect={"type": "choice", "options": [{"type": "gain-lore", "target": "CONTROLLER", "amount": 1}]},
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(enqueue_pending_action_effect(state, pending))

    result = runtime.process_command(_resolve_command(pending.id, params={}), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "RESOLVE_EFFECT_CHOICE_REQUIRED"


def test_resolve_effect_optional_selection_requires_resolve_optional():
    resources = resources_for({"aladdin": "ZTM"})
    state = _main_state(state_with_play(resources, p0=("aladdin",)))
    pending = create_pending_action_effect(
        state,
        kind="optional-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": "aladdin", "cardType": "character", "costType": "free"},
        effect={"type": "optional", "effect": {"type": "gain-lore", "target": "CONTROLLER", "amount": 1}},
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(enqueue_pending_action_effect(state, pending))

    result = runtime.process_command(_resolve_command(pending.id, params={}), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "RESOLVE_EFFECT_OPTIONAL_REQUIRED"


def test_resolve_effect_scry_selection_requires_destinations():
    resources = resources_for({"aladdin": "ZTM"})
    state = _main_state(state_with_play(resources, p0=("aladdin",)))
    pending = create_pending_action_effect(
        state,
        kind="scry-selection",
        sourceCardId="aladdin",
        controllerId="p0",
        chooserId="p0",
        cardPlayed={"playerId": PlayerId("p0"), "cardId": "aladdin", "cardType": "character", "costType": "free"},
        effect={"type": "scry", "amount": 1},
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(enqueue_pending_action_effect(state, pending))

    result = runtime.process_command(_resolve_command(pending.id, params={}), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "RESOLVE_EFFECT_DESTINATIONS_REQUIRED"

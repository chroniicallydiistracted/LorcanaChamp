from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.context import create_framework_state_snapshot
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.turn_owner import (
    require_current_player_for_move,
    resolve_current_player_for_move,
    resolve_pending_choice_player_id,
    resolve_priority_holder_id,
    resolve_runtime_identity,
    resolve_turn_owner_id,
)
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves.ink import PUT_CARD_INTO_INKWELL
from lorcana_engine_v2.moves.play import PLAY_CARD

from .helpers import resources_for
from .test_play_card_lorcanito_v2 import _main_state


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-play-identity-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def _ink_command(card_id):
    return CommandEnvelope(
        commandID=f"cmd-ink-identity-{card_id}",
        move=PUT_CARD_INTO_INKWELL,
        input=MoveInput(args={"cardId": card_id}),
    )


def test_turn_owner_prefers_explicit_turn_owner_over_priority_holder_with_real_state():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )

    assert resolve_turn_owner_id(state) == PlayerId("p0")
    assert resolve_current_player_for_move(state) == PlayerId("p0")
    assert resolve_priority_holder_id(state) == PlayerId("p1")

    identity = resolve_runtime_identity(state)
    assert identity.turnOwnerId == PlayerId("p0")
    assert identity.priorityHolderId == PlayerId("p1")
    assert identity.pendingChoicePlayerId is None


def test_turn_owner_falls_back_to_otp_and_completed_turn_rotation_when_turn_owner_missing():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G.with_updates(
            turnsCompletedByPlayer={PlayerId("p0"): 1, PlayerId("p1"): 0}
        ),
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(turnOwnerId=None, otp=PlayerId("p0")),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )

    assert resolve_turn_owner_id(state) == PlayerId("p1")


def test_turn_owner_falls_back_to_priority_only_when_otp_is_absent():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(turnOwnerId=None, otp=None),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )

    assert resolve_turn_owner_id(state) == PlayerId("p1")


def test_framework_snapshot_current_player_uses_canonical_turn_owner_resolver():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G.with_updates(
            turnsCompletedByPlayer={PlayerId("p0"): 1, PlayerId("p1"): 0}
        ),
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(turnOwnerId=None, otp=PlayerId("p0")),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )

    snapshot = create_framework_state_snapshot(state)

    assert snapshot.currentPlayer == PlayerId("p1")


def test_pending_choice_player_is_not_turn_owner_or_priority_holder():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    pending_choice = type(
        "PendingChoiceLike",
        (),
        {
            "type": "action-effect",
            "playerID": PlayerId("p1"),
            "requestID": "pending-1",
        },
    )()
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(
                holder=PlayerId("p0"),
                windowOpen=True,
                pendingChoice=pending_choice,
            ),
        ),
    )

    assert resolve_turn_owner_id(state) == PlayerId("p0")
    assert resolve_priority_holder_id(state) == PlayerId("p0")
    assert resolve_pending_choice_player_id(state) == PlayerId("p1")


def test_require_current_player_rejects_priority_holder_when_not_turn_owner():
    resources = resources_for({"card": "XGm"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )

    result = require_current_player_for_move(state, PlayerId("p1"))

    assert result.valid is False
    assert result.errorCode == "NOT_CURRENT_PLAYER"


def test_play_card_allows_turn_owner_even_when_priority_holder_is_temporarily_different():
    resources = resources_for({"card": "XGm", "ink1": "Y1z", "ink2": "Y1z", "ink3": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink1", "ink2", "ink3"))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("card"),
        "p0",
        prev_state_id=state.ctx._stateID,
        actor_role="player",
    )

    assert result.success is True
    assert InstanceId("card") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]


def test_play_card_rejects_non_turn_owner_even_when_they_hold_priority():
    resources = resources_for({"p0_card": "XGm", "p1_card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("p0_card",), inkwell=("ink",))
    zones = move_card_to_zone(
        state.ctx.zones,
        card_id="p1_card",
        destination_zone_key=scoped_zone("hand", "p1"),
    )
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            zones=zones,
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _play_command("p1_card"),
        "p1",
        prev_state_id=state.ctx._stateID,
        actor_role="player",
    )

    assert result.success is False
    assert result.errorCode == "NOT_CURRENT_PLAYER"


def test_inkwell_uses_priority_holder_as_actor_like_lorcanito():
    resources = resources_for(
        {"p0_card": "XGm", "p1_card": "Y1z"},
        owners={"p0": ("p0_card",), "p1": ("p1_card",)},
    )
    state = _main_state(resources, hand=("p0_card",))
    zones = move_card_to_zone(
        state.ctx.zones,
        card_id="p1_card",
        destination_zone_key=scoped_zone("hand", "p1"),
    )
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            zones=zones,
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _ink_command("p1_card"),
        "p1",
        prev_state_id=state.ctx._stateID,
        actor_role="player",
    )

    assert result.success is True
    assert InstanceId("p1_card") in result.state.ctx.zones.private.zoneCards[scoped_zone("inkwell", "p1")]


def test_inkwell_rejects_turn_owner_when_priority_holder_is_temporarily_different():
    resources = resources_for({"card": "Y1z"})
    state = _main_state(resources, hand=("card",))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        _ink_command("card"),
        "p0",
        prev_state_id=state.ctx._stateID,
        actor_role="player",
    )

    assert result.success is False
    assert result.errorCode == "NOT_PRIORITY_HOLDER"
    assert InstanceId("card") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
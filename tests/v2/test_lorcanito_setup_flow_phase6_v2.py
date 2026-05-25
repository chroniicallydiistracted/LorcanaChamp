from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.moves import ALTER_HAND, CHOOSE_WHO_GOES_FIRST, PUT_CARD_INTO_INKWELL

from .helpers import resources_for


def _setup_resources(deck_size: int = 16):
    cards = {
        **{f"p0_card_{index}": "XGm" for index in range(deck_size)},
        **{f"p1_card_{index}": "Y1z" for index in range(deck_size)},
    }
    return resources_for(
        cards,
        owners={
            "p0": tuple(f"p0_card_{index}" for index in range(deck_size)),
            "p1": tuple(f"p1_card_{index}" for index in range(deck_size)),
        },
    )


def _runtime_at_start(resources, chooser: PlayerId = PlayerId("p0")) -> MatchRuntime:
    state = initialize_match_state_from_static_resources(
        resources,
        seed="phase6-seed",
        match_id="phase6-match",
        game_id="phase6-game",
        choosing_first_player=chooser,
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _choose_command(player_id: str) -> CommandEnvelope:
    return CommandEnvelope(
        commandID=f"cmd-choose-{player_id}",
        move=CHOOSE_WHO_GOES_FIRST,
        input=MoveInput(args={"playerId": player_id}),
    )


def _alter_command(player_id: str, cards_to_mulligan=()) -> CommandEnvelope:
    return CommandEnvelope(
        commandID=f"cmd-alter-{player_id}",
        move=ALTER_HAND,
        input=MoveInput(args={"playerId": player_id, "cardsToMulligan": tuple(cards_to_mulligan)}),
    )


def test_initial_legal_move_is_choose_who_goes_first_for_the_chooser_only():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))

    assert runtime.get_state().ctx.status.gameSegment == "startingAGame"
    assert runtime.get_state().ctx.status.phase == "chooseFirstPlayer"
    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (CHOOSE_WHO_GOES_FIRST,)
    assert runtime.enumerate_moves_for_player("p1", actor_role="player") == ()


def test_setup_flow_disallows_non_setup_moves_before_first_player_is_chosen():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))

    result = runtime.process_command(
        CommandEnvelope(
            commandID="cmd-illegal-ink",
            move=PUT_CARD_INTO_INKWELL,
            input=MoveInput(args={"cardId": "p0_card_0"}),
        ),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Move 'putCardIntoInkwell' is not legal in phase 'chooseFirstPlayer'"
    assert result.errorCode == "FLOW_DISALLOWED"


def test_choose_who_goes_first_rejects_invalid_player_before_state_change():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    state = runtime.get_state()

    result = runtime.process_command(_choose_command("not-a-player"), "p0", actor_role="player")

    assert result.success is False
    assert result.error == "Invalid player ID: not-a-player"
    assert result.errorCode == "INVALID_PLAYER"
    assert runtime.get_state() == state


def test_choose_who_goes_first_sets_otp_draws_opening_hands_and_enters_mulligan():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    state = runtime.get_state()

    result = runtime.process_command(_choose_command("p1"), "p0", actor_role="player", timestamp=6000)

    assert result.success is True
    assert result.stateID == state.ctx._stateID + 1
    assert result.gameEvents[0].event.kind == "MOVE_EXECUTED"
    assert result.moveLogs[0].defaultMessage.key == "lorcana.setup.firstPlayerChosen"

    next_state = result.state
    assert next_state.ctx.status.gameSegment == "startingAGame"
    assert next_state.ctx.status.phase == "mulligan"
    assert next_state.ctx.status.otp == PlayerId("p1")
    assert next_state.ctx.status.turnOwnerId == PlayerId("p1")
    assert next_state.ctx.status.pendingMulligan == (PlayerId("p1"), PlayerId("p0"))
    assert next_state.ctx.priority.holder == PlayerId("p1")
    assert next_state.ctx.priority.windowOpen is True
    assert len(next_state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]) == 7
    assert len(next_state.ctx.zones.private.zoneCards[scoped_zone("hand", "p1")]) == 7
    assert len(next_state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")]) == 9
    assert len(next_state.ctx.zones.private.zoneCards[scoped_zone("deck", "p1")]) == 9


def test_alter_hand_rejects_card_not_in_hand():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    choose_result = runtime.process_command(_choose_command("p0"), "p0", actor_role="player")
    assert choose_result.success is True

    result = runtime.process_command(
        _alter_command("p0", cards_to_mulligan=("not-a-card",)),
        "p0",
        actor_role="player",
    )

    assert result.success is False
    assert result.error == "Card not-a-card not in hand"
    assert result.errorCode == "CARD_NOT_IN_HAND"


def test_alter_hand_moves_selected_cards_to_bottom_draws_replacements_and_advances_priority():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    choose_result = runtime.process_command(_choose_command("p0"), "p0", actor_role="player")
    assert choose_result.success is True
    state_after_choose = runtime.get_state()
    original_hand = state_after_choose.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
    selected = original_hand[:2]

    result = runtime.process_command(_alter_command("p0", selected), "p0", actor_role="player")

    assert result.success is True
    assert result.moveLogs[0].defaultMessage.key == "lorcana.setup.mulligan.count"
    assert result.moveLogs[0].visibility.mode == "PUBLIC_WITH_OVERRIDES"
    assert result.state.ctx.status.pendingMulligan == (PlayerId("p1"),)
    assert result.state.ctx.priority.holder == PlayerId("p1")
    assert result.state.ctx.priority.windowOpen is True

    next_hand = result.state.ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]
    next_deck = result.state.ctx.zones.private.zoneCards[scoped_zone("deck", "p0")]
    assert len(next_hand) == 7
    assert all(card_id not in next_hand for card_id in selected)
    assert all(card_id in next_deck for card_id in selected)
    assert next_deck[:2] == tuple(reversed(tuple(InstanceId(card_id) for card_id in selected)))


def test_alter_hand_rejects_player_who_already_mulliganed():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    assert runtime.process_command(_choose_command("p0"), "p0", actor_role="player").success is True
    assert runtime.process_command(_alter_command("p0", ()), "p0", actor_role="player").success is True

    result = runtime.process_command(_alter_command("p0", ()), "judge", actor_role="judge")

    assert result.success is False
    assert result.error == "Player has already made a mulligan decision"
    assert result.errorCode == "MULLIGAN_ALREADY_DONE"


def test_second_mulligan_transitions_to_main_game_main_phase_turn_one_with_otp_priority():
    resources = _setup_resources()
    runtime = _runtime_at_start(resources, chooser=PlayerId("p0"))
    assert runtime.process_command(_choose_command("p0"), "p0", actor_role="player").success is True
    assert runtime.process_command(_alter_command("p0", ()), "p0", actor_role="player").success is True

    result = runtime.process_command(_alter_command("p1", ()), "p1", actor_role="player")

    assert result.success is True
    assert result.moveLogs[0].defaultMessage.key == "lorcana.setup.mulligan.count"
    assert result.moveLogs[1].defaultMessage.key == "lorcana.setup.done"
    assert result.state.ctx.status.pendingMulligan == ()
    assert result.state.ctx.status.gameSegment == "mainGame"
    assert result.state.ctx.status.phase == "main"
    assert result.state.ctx.status.turn == 1
    assert result.state.ctx.status.otp == PlayerId("p0")
    assert result.state.ctx.priority.holder == PlayerId("p0")
    assert result.state.ctx.priority.windowOpen is True
    assert runtime.enumerate_moves_for_player("p0", actor_role="player") == (PUT_CARD_INTO_INKWELL,)

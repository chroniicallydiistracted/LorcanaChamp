from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.zones import scoped_zone
from lorcana_engine_v2.moves.play import PLAY_CARD

from .test_play_card_lorcanito_v2 import _main_state
from .helpers import resources_for


def _runtime(resources, state):
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    return runtime


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-play-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def test_standard_play_rejects_when_available_ink_is_too_low():
    resources = resources_for({"card": "Y1z", "i1": "XGm", "i2": "XGm", "i3": "XGm"})
    state = _main_state(resources, hand=("card",), inkwell=("i1", "i2", "i3"))
    runtime = _runtime(resources, state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "INSUFFICIENT_INK"
    assert InstanceId("card") in runtime.get_state().ctx.zones.private.zoneCards[scoped_zone("hand", "p0")]


def test_available_ink_counts_only_ready_inkwell_cards_after_payment():
    resources = resources_for({"card": "XGm", "i1": "Y1z", "i2": "Y1z", "i3": "Y1z", "i4": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("i1", "i2", "i3", "i4"))
    runtime = _runtime(resources, state)

    before = runtime.validate_command(_play_command("card"), "p0", actor_role="player")
    assert before.valid is True

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is True
    assert result.state.ctx.zones.private.cardMeta[InstanceId("i1")].state == "exerted"
    ready = [
        card_id
        for card_id in ("i1", "i2", "i3", "i4")
        if result.state.ctx.zones.private.cardMeta[InstanceId(card_id)].state != "exerted"
    ]
    assert ready == ["i4"]

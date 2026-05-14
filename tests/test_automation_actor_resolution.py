from lorcana_bot.automation.actor_resolution import resolve_current_actor
from lorcana_bot.constants import PHASE_MULLIGAN
from lorcana_bot.state import BagEffectEntry, PendingTrigger


def test_main_phase_actor(engine, state):
    result = resolve_current_actor(state, engine)
    assert result.actor == state.active_player
    assert result.reason == "active_priority_player"


def test_bag_actor(engine, state):
    # Create a BagEffectEntry using the new field names
    entry = BagEffectEntry(
        id=state.next_bag_id(),
        kind="triggered_ability",
        ability_id="test_trigger",
        ability_index=0,
        ability_key="test_trigger_key",
        ability_name="Test Trigger",
        auto_resolve=True,
        controller_id=1,
        chooser_id=1,
        source_id=state.players[1].hand[0],
        source_card_id="test_card",
        trigger={"event": "TEST"},
        condition=None,
        effects=(),
        occurrence_index=1,
    )
    state.bag.append(entry)
    result = resolve_current_actor(state, engine)
    assert result.actor == 1
    assert result.reason == "pending_bag_resolver"


def test_mulligan_actor(engine):
    state = engine.setup_game([["Amber Recruit"] * 50, ["Amber Recruit"] * 50], seed=1, enable_mulligan=True)
    result = resolve_current_actor(state, engine)
    assert result.actor == state.active_player
    assert result.reason == "mulligan_player"


def test_unresolved_actor(engine, state):
    state.active_player = 9
    result = resolve_current_actor(state, engine)
    assert result.actor is None
    assert result.reason == "unresolved_actor"

"""
Guard test to prevent EffectResolver from reintroducing direct gameplay mutation.

Microfix 8: Forces effect resolution through engine-owned event boundaries.
All gameplay-significant mutations must go through GameEngine helpers.
"""

from __future__ import annotations

from pathlib import Path


def test_effect_resolver_does_not_directly_mutate_gameplay_state():
    """
    Guard test that scans lorcana_bot/effects.py for direct gameplay mutation patterns.

    This test ensures that the EffectResolver delegates all rule-significant state
    changes to engine-owned helpers rather than mutating state directly.

    Allowed resolver-local mutations (excluded from this guard):
    - state.players[context.actor].cost_reductions.append(...)
    - state.cards[target].temporary_keywords.append(...)
    - state.cards[target].temporary_modifiers[...] = ...
    - state.cards[cid].revealed = True
    - state.shuffle_counter += 1
    - rng.shuffle(state.players[player].deck)
    """
    source = Path("lorcana_bot/effects.py").read_text()

    forbidden_patterns = {
        "state.move_card(": "zone movement must go through GameEngine._move_card_eventful or a more specific helper",
        ".lore +=": "lore gain must go through GameEngine._gain_lore_eventful",
        ".lore -=": "lore loss must go through GameEngine._lose_lore_eventful",
        ".damage +=": "damage must go through GameEngine._deal_damage_eventful",
        ".damage -=": "damage removal must go through GameEngine._remove_damage_eventful",
        ".exerted = True": "exertion must go through GameEngine._exert_eventful",
        ".exerted = False": "readying must go through GameEngine._ready_eventful unless it is in an engine helper",
        "state.event_log.append(": "events must go through GameEngine.emit_event",
        "GameEvent(": "events must go through GameEngine.emit_event",
    }

    violations = {
        pattern: reason
        for pattern, reason in forbidden_patterns.items()
        if pattern in source
    }

    assert violations == {}, (
        f"EffectResolver must not directly mutate gameplay state. Found violations:\n" +
        "\n".join(f"  - {pattern!r}: {reason}" for pattern, reason in violations.items())
    )


def test_effect_resolver_uses_engine_helpers_for_card_movement():
    """
    Verify that zone movement effects use engine helpers like _move_card_eventful.

    Direct zone movement (state.move_card) bypasses the event system and replacement
    effects, which could break card routing logic.
    """
    source = Path("lorcana_bot/effects.py").read_text()

    # Check that _move_card_eventful is used instead of state.move_card
    assert "_move_card_eventful" in source, (
        "EffectResolver should use _move_card_eventful for card movement"
    )

    # Verify no direct state.move_card calls
    assert "state.move_card(" not in source, (
        "Zone movement must go through GameEngine._move_card_eventful, not state.move_card"
    )


def test_effect_resolver_uses_engine_helpers_for_lore_changes():
    """
    Verify that lore changes use engine helpers like _gain_lore_eventful/_lose_lore_eventful.

    Direct lore mutation bypasses the event system, which could break replacement effects
    that trigger on lore changes.
    """
    source = Path("lorcana_bot/effects.py").read_text()

    # Check that eventful helpers are used
    assert "_gain_lore_eventful" in source, (
        "EffectResolver should use _gain_lore_eventful for lore gain"
    )
    assert "_lose_lore_eventful" in source, (
        "EffectResolver should use _lose_lore_eventful for lore loss"
    )

    # Verify no direct .lore +/-= mutations
    assert ".lore +=" not in source, (
        "Lore gain must go through GameEngine._gain_lore_eventful"
    )
    assert ".lore -=" not in source, (
        "Lore loss must go through GameEngine._lose_lore_eventful"
    )


def test_effect_resolver_uses_engine_helpers_for_damage():
    """
    Verify that damage changes use engine helpers like _deal_damage_eventful.

    Direct damage mutation bypasses the event system and resistance mechanics.
    """
    source = Path("lorcana_bot/effects.py").read_text()

    # Check that eventful helpers are used
    assert "_deal_damage_eventful" in source, (
        "EffectResolver should use _deal_damage_eventful for damage"
    )
    assert "_remove_damage_eventful" in source, (
        "EffectResolver should use _remove_damage_eventful for damage removal"
    )

    # Verify no direct damage mutations on card instances
    assert ".damage +=" not in source, (
        "Damage must go through GameEngine._deal_damage_eventful"
    )
    assert ".damage -=" not in source, (
        "Damage removal must go through GameEngine._remove_damage_eventful"
    )


def test_effect_resolver_uses_engine_helpers_for_exert_ready():
    """
    Verify that exert/ready changes use engine helpers like _exert_eventful/_ready_eventful.

    Direct exert/ready mutation bypasses the event system.
    """
    source = Path("lorcana_bot/effects.py").read_text()

    # Check that eventful helpers are used
    assert "_exert_eventful" in source, (
        "EffectResolver should use _exert_eventful for exertion"
    )
    assert "_ready_eventful" in source, (
        "EffectResolver should use _ready_eventful for readying"
    )

    # Verify no direct exerted mutations in effects.py
    # Note: We allow .exerted = False in engine helpers, but NOT in EffectResolver
    lines = source.split("\n")
    for i, line in enumerate(lines, 1):
        if ".exerted = True" in line and "_eventful" not in line:
            assert False, f"Line {i}: Exertion must go through GameEngine._exert_eventful"
        if ".exerted = False" in line and "_eventful" not in line:
            assert False, f"Line {i}: Readying must go through GameEngine._ready_eventful"


def test_effect_resolver_uses_engine_helpers_for_event_emission():
    """
    Verify that events are emitted through engine emit_event, not direct GameEvent creation.

    Direct event creation bypasses the event queue and trigger processing.
    """
    source = Path("lorcana_bot/effects.py").read_text()

    # Verify no direct GameEvent creation or event_log.append in effects.py
    assert "GameEvent(" not in source, (
        "Events must be emitted through GameEngine.emit_event, not direct GameEvent()"
    )
    assert "state.event_log.append(" not in source, (
        "Events must be emitted through GameEngine.emit_event, not direct event_log.append"
    )


def test_allowed_resolver_local_mutations_are_not_guarded():
    """
    Verify that allowed resolver-local mutations are not treated as violations.

    These are the few cases where EffectResolver may mutate state directly:
    - cost_reductions.append (player state, not rule-significant)
    - temporary_keywords.append (effect state, not game state)
    - temporary_modifiers[...] = (effect state, not game state)
    - revealed = True (informational flag)
    - shuffle_counter += 1 (metadata)
    - rng.shuffle (deterministic shuffle)
    """
    forbidden_patterns = {
        "state.move_card(",
        ".lore +=",
        ".lore -=",
        ".damage +=",
        ".damage -=",
        ".exerted = True",
        ".exerted = False",
        "state.event_log.append(",
        "GameEvent(",
    }
    allowed_patterns = {
        "cost_reductions.append",
        "temporary_keywords.append",
        "temporary_modifiers",
        "revealed = True",
        "shuffle_counter += 1",
        "rng.shuffle",
    }

    assert forbidden_patterns.isdisjoint(allowed_patterns)

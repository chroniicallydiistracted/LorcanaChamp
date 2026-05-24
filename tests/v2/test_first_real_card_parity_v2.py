from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.state import CardInstance, MatchState, PlayerState


def _catalog() -> CardCatalog:
    return CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))


def _state_with(*instances: CardInstance) -> MatchState:
    play0 = tuple(inst.instance_id for inst in instances if int(inst.controller) == 0 and inst.zone == "play")
    play1 = tuple(inst.instance_id for inst in instances if int(inst.controller) == 1 and inst.zone == "play")
    return MatchState(
        players=(PlayerState(PlayerId(0), play=play0), PlayerState(PlayerId(1), play=play1)),
        cards={inst.instance_id: inst for inst in instances},
    )


def _inst(i: int, card_id: str, controller: int = 0, zone: str = "play", damage: int = 0):
    return CardInstance(
        instance_id=InstanceId(i),
        card_id=CardId(card_id),
        owner=PlayerId(controller),
        controller=PlayerId(controller),
        zone=zone,
        damage=damage,
    )


def test_chi_fu_real_static_lore_materializes_from_lorcanito_data():
    catalog = _catalog()
    ctx = build_rules_context(catalog)
    state = _state_with(_inst(1, "XGm"))

    assert catalog.get("XGm").full_name == "Chi-Fu - Imperial Advisor"
    assert ctx.derived.effective_lore(state, ctx, 1) == 3


def test_mr_incredible_real_filtered_count_static_strength():
    catalog = _catalog()
    ctx = build_rules_context(catalog)
    state = _state_with(
        _inst(1, "qoz"),  # Mr. Incredible - Super Strong, printed 6 strength
        _inst(2, "Y1z"),  # another public character controlled by you
    )

    assert catalog.get("qoz").full_name == "Mr. Incredible - Super Strong"
    assert ctx.derived.effective_strength(state, ctx, 1) == 8


def test_tamatoa_real_items_in_play_lore_amount_provider():
    catalog = _catalog()
    ctx = build_rules_context(catalog)
    # Use a real item card id from set 1: Dinglehopper (sapphire item).
    state = _state_with(_inst(1, "Z2D"), _inst(2, "Bf0"))

    # If Bf0 is not an item in a future dataset, this test should fail and the
    # fixture should be updated to another real item card, not replaced by a fake.
    assert catalog.get("Z2D").full_name == "Tamatoa - So Shiny!"
    assert catalog.get("Bf0").card_type == "item"
    assert ctx.derived.effective_lore(state, ctx, 1) == catalog.get("Z2D").lore + 1


def test_ling_real_classification_target_static_strength():
    catalog = _catalog()
    ctx = build_rules_context(catalog)
    state = _state_with(
        _inst(1, "HyV"),  # Ling - Imperial Soldier: Your Hero characters get +1 strength
        _inst(2, "Y1z"),  # Hero character
    )

    assert catalog.get("HyV").full_name == "Ling - Imperial Soldier"
    assert "Hero" in catalog.get("Y1z").classifications
    assert ctx.derived.effective_strength(state, ctx, 2) == catalog.get("Y1z").strength + 1


def test_aurora_real_ward_grant_excludes_self():
    catalog = _catalog()
    ctx = build_rules_context(catalog)
    state = _state_with(
        _inst(1, "Au0"),  # Aurora - Dreaming Guardian: Your other characters gain Ward
        _inst(2, "Y1z"),
    )

    assert catalog.get("Au0").full_name == "Aurora - Dreaming Guardian"
    assert "WARD" not in ctx.derived.keywords(state, ctx, 1)
    assert "WARD" in ctx.derived.keywords(state, ctx, 2)

from lorcana_engine_v2.core.zones import CardMeta

from .helpers import context_for, resources_for, state_with_play


def test_chi_fu_real_static_lore_materializes_from_lorcanito_data():
    resources = resources_for({"chi": "XGm"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("chi",))

    assert resources.cards.get("XGm").full_name == "Chi-Fu - Imperial Advisor"
    assert ctx.derived.effective_lore(state, ctx, "chi") == 3


def test_mr_incredible_real_filtered_count_static_strength():
    resources = resources_for({"mr": "qoz", "ally": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("mr", "ally"))

    assert resources.cards.get("qoz").full_name == "Mr. Incredible - Super Strong"
    assert ctx.derived.effective_strength(state, ctx, "mr") == 8


def test_tamatoa_real_items_in_play_lore_amount_provider():
    resources = resources_for({"tamatoa": "Z2D", "item": "Bf0"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("tamatoa", "item"))

    assert resources.cards.get("Z2D").full_name == "Tamatoa - So Shiny!"
    assert resources.cards.get("Bf0").card_type == "item"
    assert ctx.derived.effective_lore(state, ctx, "tamatoa") == resources.cards.get("Z2D").lore + 1


def test_ling_real_classification_target_static_strength():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    assert resources.cards.get("HyV").full_name == "Ling - Imperial Soldier"
    assert "Hero" in resources.cards.get("Y1z").classifications
    assert ctx.derived.effective_strength(state, ctx, "hero") == resources.cards.get("Y1z").strength + 1


def test_aurora_real_ward_grant_excludes_self():
    resources = resources_for({"aurora": "Au0", "ally": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("aurora", "ally"))

    assert resources.cards.get("Au0").full_name == "Aurora - Dreaming Guardian"
    assert "WARD" not in ctx.derived.keywords(state, ctx, "aurora")
    assert "WARD" in ctx.derived.keywords(state, ctx, "ally")


def test_donald_damage_on_self_static_lore_reads_card_meta():
    resources = resources_for({"donald": "2q9"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("donald",), meta={"donald": CardMeta(damage=2)})

    assert resources.cards.get("2q9").full_name == "Donald Duck - Not Again!"
    assert ctx.derived.effective_lore(state, ctx, "donald") == resources.cards.get("2q9").lore + 2

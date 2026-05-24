from lorcana_engine_v2.rules.amount_resolver import AmountContext

from .helpers import context_for, resources_for, state_with_play


def test_items_in_play_amount_provider_counts_real_items_through_query_api():
    resources = resources_for({"source": "Z2D", "item": "Bf0"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("source", "item"))

    assert resources.cards.get("Bf0").card_type == "item"
    assert ctx.amounts.resolve(
        state,
        ctx,
        {"type": "items-in-play", "controller": "you"},
        AmountContext(actor="p0", source_id="source"),
    ) == 1


def test_damage_on_self_amount_provider_reads_card_meta():
    from lorcana_engine_v2.core.zones import CardMeta

    resources = resources_for({"source": "2q9"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("source",), meta={"source": CardMeta(damage=3)})

    assert ctx.amounts.resolve(
        state,
        ctx,
        {"type": "damage-on-self"},
        AmountContext(actor="p0", source_id="source"),
    ) == 3

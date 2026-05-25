from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.zones import CardMeta
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext

from .helpers import context_for, resources_for, state_with_play


def test_condition_evaluator_counts_real_play_zone_card_types_and_classifications():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    assert ctx.conditions.evaluate(
        state,
        ctx,
        {
            "type": "has-character-count",
            "controller": "you",
            "classification": "Hero",
            "comparison": "greater-or-equal",
            "count": 1,
        },
        ConditionContext(actor=PlayerId("p0"), source_id=InstanceId("ling")),
    )


def test_condition_evaluator_reads_meta_damage_and_target_query():
    resources = resources_for({"donald": "2q9", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("donald", "hero"), meta={"donald": CardMeta(damage=2)})

    assert ctx.conditions.evaluate(
        state,
        ctx,
        {"type": "self-has-damage"},
        ConditionContext(actor="p0", source_id="donald"),
    )
    assert ctx.conditions.evaluate(
        state,
        ctx,
        {
            "type": "target-query",
            "query": {
                "selector": "all",
                "owner": "you",
                "zones": ["play"],
                "cardTypes": ["character"],
                "filter": [{"type": "has-classification", "classification": "Hero"}],
            },
            "comparison": {"operator": "gte", "value": 1},
        },
        ConditionContext(actor="p0", source_id="donald"),
    )


def test_target_resolver_matches_lorcanito_owner_zones_types_filters_and_exclude_self():
    resources = resources_for({"aurora": "Au0", "ally": "Y1z", "opposing": "2q9"}, owners={"p0": ("aurora", "ally"), "p1": ("opposing",)})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("aurora", "ally"), p1=("opposing",))

    result = ctx.targets.resolve(
        state,
        ctx,
        {
            "selector": "all",
            "owner": "you",
            "zones": ["play"],
            "cardTypes": ["character"],
            "excludeSelf": True,
        },
        TargetQueryContext(actor="p0", source_id="aurora"),
    )

    assert result == (InstanceId("ally"),)

    opposing = ctx.targets.resolve(
        state,
        ctx,
        {
            "selector": "all",
            "owner": "opponent",
            "zones": ["play"],
            "cardTypes": ["character"],
            "filter": [{"type": "has-classification", "classification": "Hero"}],
        },
        TargetQueryContext(actor="p0", source_id="aurora"),
    )

    assert opposing == (InstanceId("opposing"),)

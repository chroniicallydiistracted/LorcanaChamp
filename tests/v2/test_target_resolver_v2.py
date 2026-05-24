from lorcana_engine_v2.rules.target_resolver import TargetQueryContext

from .helpers import context_for, resources_for, state_with_play


def test_your_hero_characters_alias_resolves_real_hero_card_through_runtime_query_api():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    result = ctx.targets.resolve(state, ctx, "YOUR_HERO_CHARACTERS", TargetQueryContext(actor="p0", source_id="ling"))
    assert result == ("hero",)

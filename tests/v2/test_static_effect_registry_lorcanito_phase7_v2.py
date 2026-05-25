from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.registries.static_registry import StaticRegistry

from .helpers import context_for, resources_for, state_with_play


def test_static_effect_registry_indexes_effects_by_target_source_and_kind():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    registry = StaticRegistry().build(state, ctx.query)

    target_effects = registry.get_effects_for_card("hero", kind="modify-stat")
    source_effects = registry.get_effects_from_card("ling")

    assert len(target_effects) == 1
    assert target_effects[0].sourceId == InstanceId("ling")
    assert target_effects[0].sourceControllerId == PlayerId("p0")
    assert target_effects[0].abilityName == "FULL OF SPIRIT"
    assert target_effects[0].sourceDefinitionId == "HyV"
    assert target_effects[0].payload["stat"] == "strength"
    assert target_effects[0].payload["modifier"] == 1
    assert source_effects == target_effects


def test_static_effect_registry_materializes_real_keyword_grant_targets():
    resources = resources_for({"aurora": "Au0", "ally": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("aurora", "ally"))

    registry = StaticRegistry().build(state, ctx.query)

    assert registry.get_effects_for_card("aurora", kind="gain-keyword") == ()
    effects = registry.get_effects_for_card("ally", kind="gain-keyword")
    assert len(effects) == 1
    assert effects[0].sourceId == InstanceId("aurora")
    assert effects[0].payload["keyword"] == "Ward"

from .helpers import context_for, resources_for, state_with_play


def test_static_registry_materializes_real_chi_fu_static_using_static_resources():
    resources = resources_for({"chi": "XGm"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("chi",))

    effects = ctx.static.materialize(state, ctx)
    assert len(effects) == 1
    assert effects[0].kind == "modify-stat"
    assert effects[0].source_id == "chi"
    assert effects[0].source_controller == "p0"
    assert effects[0].target_ids == ("chi",)
    assert effects[0].payload == {"stat": "lore", "amount": 2}

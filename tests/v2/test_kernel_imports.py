def test_v2_kernel_imports_without_legacy_runtime():
    import sys
    import lorcana_engine_v2

    assert lorcana_engine_v2.MatchRuntime is not None
    forbidden = [
        "lorcana_bot.engine",
        "lorcana_bot.effects",
        "lorcana_bot.static_effects",
        "lorcana_bot.targeting",
    ]
    assert not any(name in sys.modules for name in forbidden)

from pathlib import Path


def test_v2_core_does_not_import_legacy_runtime_modules():
    root = Path("lorcana_engine_v2")
    forbidden = (
        "lorcana_bot.engine",
        "lorcana_bot.effects",
        "lorcana_bot.static_effects",
        "lorcana_bot.targeting",
        "from lorcana_bot.engine",
        "from lorcana_bot.effects",
        "from lorcana_bot.static_effects",
        "from lorcana_bot.targeting",
    )
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path}: {needle}")
    assert offenders == []

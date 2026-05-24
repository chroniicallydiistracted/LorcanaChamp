from __future__ import annotations

import json
import subprocess
import sys
import textwrap


def test_v2_kernel_imports_without_legacy_runtime():
    """Importing v2 in a clean process must not import legacy v1 runtime modules.

    This test intentionally runs in a subprocess so the assertion is not polluted
    by other pytest collection/import side effects in the parent process.
    """
    forbidden = [
        "lorcana_bot.engine",
        "lorcana_bot.effects",
        "lorcana_bot.static_effects",
        "lorcana_bot.targeting",
    ]

    script = textwrap.dedent(
        """
        import json
        import sys

        import lorcana_engine_v2

        forbidden = [
            "lorcana_bot.engine",
            "lorcana_bot.effects",
            "lorcana_bot.static_effects",
            "lorcana_bot.targeting",
        ]

        imported = [name for name in forbidden if name in sys.modules]

        print(json.dumps({
            "match_runtime_exported": getattr(lorcana_engine_v2, "MatchRuntime", None) is not None,
            "view_filter_exported": getattr(lorcana_engine_v2, "filter_match_view", None) is not None,
            "imported_forbidden_modules": imported,
        }))
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["match_runtime_exported"] is True
    assert payload["view_filter_exported"] is True
    assert payload["imported_forbidden_modules"] == []

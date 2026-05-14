import json
import subprocess
import sys

from lorcana_bot.importers.lorcanito_source_report import build_mapping_coverage


def test_report_json_has_expected_counts():
    data = build_mapping_coverage("data/lorcanito_extracted/cards.normalized.json")
    assert data["schema_version"] == 1
    assert data["total_cards"] > 2500
    assert data["ability_type_counts"]
    assert data["effect_type_counts"]
    assert data["top_engine_blockers"]


def test_report_script_prints_summary(tmp_path):
    out = tmp_path / "coverage.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/report_lorcanito_source_mapping.py",
            "--source-json",
            "data/lorcanito_extracted/cards.normalized.json",
            "--out",
            str(out),
            "--print-summary",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "total cards" in result.stdout
    assert json.loads(out.read_text())["schema_version"] == 1


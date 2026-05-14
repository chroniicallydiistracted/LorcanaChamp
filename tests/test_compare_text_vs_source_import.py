import json
import subprocess
import sys


def test_compare_script_runs_and_does_not_mutate_source_artifact(tmp_path):
    source = "data/lorcanito_extracted/cards.normalized.json"
    before = open(source, encoding="utf-8").read()
    out = tmp_path / "comparison.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/compare_text_import_vs_source_import.py",
            "--text-card-data",
            "data/cards",
            "--source-json",
            source,
            "--out",
            str(out),
        ],
        check=True,
    )
    data = json.loads(out.read_text())
    assert data["schema_version"] == 1
    assert "text_unsupported_but_source_structured" in data
    assert open(source, encoding="utf-8").read() == before


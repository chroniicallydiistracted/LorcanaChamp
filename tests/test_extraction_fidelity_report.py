import json

from scripts.report_lorcanito_extraction_fidelity import build_extraction_fidelity_report


def test_extraction_fidelity_report_fields_and_blockers(tmp_path):
    source = tmp_path / "cards.json"
    audit = tmp_path / "audit.json"
    patterns = tmp_path / "patterns.json"
    gaps = tmp_path / "gaps.json"
    source.write_text(json.dumps({"schema_version": 1, "cards": [{"id": "a", "abilities": [{"type": "unknown"}]}]}), encoding="utf-8")
    audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "unknowns": [],
                "summary": {"total_unknowns": 1, "by_inferred_category": {"unknown": 1}, "by_recommended_action": {"manual_review": 1}},
            }
        ),
        encoding="utf-8",
    )
    patterns.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "patterns": [
                    {
                        "pattern_fingerprint": "object_keys:type",
                        "count": 5,
                        "inferred_category": "unknown",
                        "recommended_action": "manual_review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    gaps.write_text(json.dumps({"schema_version": 1, "gaps": [], "summary": {"by_gap_type": {}, "by_impact": {}}}), encoding="utf-8")

    report1 = build_extraction_fidelity_report(source, audit, patterns, gaps)
    report2 = build_extraction_fidelity_report(source, audit, patterns, gaps)

    assert report1 == report2
    assert report1["schema_version"] == 1
    assert report1["unknown_percentage"] == 100.0
    assert report1["safe_to_proceed_to_B2"] is False
    assert report1["blocking_reasons"]

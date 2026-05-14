import json

from scripts.audit_unknown_lorcanito_abilities import build_unknown_ability_audit


def test_unknown_audit_has_required_fields_and_is_deterministic(tmp_path):
    source = tmp_path / "cards.normalized.json"
    payload = {
        "schema_version": 1,
        "cards": [
            {
                "id": "c1",
                "name": "Singer Test",
                "version": "One",
                "cardType": "character",
                "set": "TST",
                "sourceFile": "cards/c1.ts",
                "abilities": [{"type": "unknown", "rawReference": "singer", "rawExpression": "singer(5)"}],
            }
        ],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    audit1 = build_unknown_ability_audit(source, tmp_path)
    audit2 = build_unknown_ability_audit(source, tmp_path)

    assert audit1 == audit2
    assert audit1["schema_version"] == 1
    entry = audit1["unknowns"][0]
    assert entry["card_id"] or entry["source_file"]
    assert entry["pattern_fingerprint"]
    assert entry["inferred_category"] == "keyword"
    assert entry["recommended_action"] == "mapper_fix"

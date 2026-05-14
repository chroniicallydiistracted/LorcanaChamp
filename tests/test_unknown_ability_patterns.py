from scripts.audit_unknown_lorcanito_abilities import build_unknown_ability_patterns


def test_unknown_patterns_aggregate_counts_and_examples():
    audit = {
        "schema_version": 1,
        "unknowns": [
            {
                "card_id": "a",
                "card_name": "A",
                "source_file": "cards/a.ts",
                "pattern_fingerprint": "helper:singer",
                "detected_helper_calls": ["singer"],
                "detected_object_keys": ["rawReference", "type"],
                "inferred_category": "keyword",
                "recommended_action": "mapper_fix",
                "confidence": "high",
                "notes": "known Lorcanito keyword helper",
            },
            {
                "card_id": "b",
                "card_name": "B",
                "source_file": "cards/b.ts",
                "pattern_fingerprint": "helper:singer",
                "detected_helper_calls": ["singer"],
                "detected_object_keys": ["rawReference", "type"],
                "inferred_category": "keyword",
                "recommended_action": "mapper_fix",
                "confidence": "high",
                "notes": "known Lorcanito keyword helper",
            },
        ],
    }

    patterns = build_unknown_ability_patterns(audit)

    assert patterns["schema_version"] == 1
    assert patterns["patterns"][0]["pattern_fingerprint"] == "helper:singer"
    assert patterns["patterns"][0]["count"] == 2
    assert patterns["patterns"][0]["example_cards"] == ["a", "b"]

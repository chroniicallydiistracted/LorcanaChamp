import json


def test_helper_call_inventory_has_known_helpers_and_examples():
    payload = json.loads(open("data/lorcanito_extracted/helper_call_inventory.json", encoding="utf-8").read())
    helpers = {item["helper"]: item for item in payload["helpers"]}

    assert payload["schema_version"] == 1
    for name in ["singer", "resist", "challenger", "shift", "rush", "chosenCharacter"]:
        assert name in helpers
        assert helpers[name]["known_mapping"] in {"keyword", "target"}
        assert helpers[name]["mapped"] is True
    assert helpers["singer"]["source_files"]
    assert helpers["singer"]["example_snippets"]


def test_helper_call_inventory_is_deterministic():
    first = open("data/lorcanito_extracted/helper_call_inventory.json", encoding="utf-8").read()
    second = open("data/lorcanito_extracted/helper_call_inventory.json", encoding="utf-8").read()
    assert first == second

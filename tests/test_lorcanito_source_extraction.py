from pathlib import Path

import json

from scripts.extract_lorcanito_source_cards import extract


def test_extractor_creates_required_artifacts(tmp_path):
    out = tmp_path / "extract"
    extract("lorcanito-full-src-code", out)
    for name in [
        "manifest.json",
        "cards.normalized.json",
        "abilities.schema_inventory.json",
        "effects.schema_inventory.json",
        "targets.schema_inventory.json",
        "conditions.schema_inventory.json",
        "costs.schema_inventory.json",
        "triggers.schema_inventory.json",
        "source_file_index.json",
    ]:
        assert (out / name).exists()
    manifest = json.loads((out / "manifest.json").read_text())
    cards = json.loads((out / "cards.normalized.json").read_text())["cards"]
    effects = json.loads((out / "effects.schema_inventory.json").read_text())
    assert manifest["card_file_count"] > 2000
    assert len(cards) > 2500
    assert effects["counts"]["draw"] > 0


def test_extractor_is_deterministic_across_two_runs(tmp_path):
    out1 = tmp_path / "one"
    out2 = tmp_path / "two"
    extract("lorcanito-full-src-code", out1)
    extract("lorcanito-full-src-code", out2)
    assert (out1 / "cards.normalized.json").read_text() == (out2 / "cards.normalized.json").read_text()
    assert (out1 / "effects.schema_inventory.json").read_text() == (out2 / "effects.schema_inventory.json").read_text()


def test_malicious_mean_and_scary_extracts_full_name_and_nested_ability(tmp_path):
    """Regression test: Malicious, Mean, and Scary should preserve commas and nested ability structure."""
    source_root = Path("lorcanito-full-src-code")
    if not source_root.exists():
        import pytest
        pytest.skip("lorcanito-full-src-code not available")
    out = tmp_path / "extract"
    extract(source_root, out)
    cards = json.loads((out / "cards.normalized.json").read_text())["cards"]
    card = next((c for c in cards if c.get("id") == "Rc1"), None)
    assert card is not None, "Card Rc1 not found in extracted cards"
    assert card["name"] == "Malicious, Mean, and Scary", f"Expected full name with commas, got: {card.get('name')}"
    assert card["text"] == "Put 1 damage counter on each opposing character."
    assert card["actionSubtype"] == "song"
    # Verify nested ability structure is preserved
    abilities = card.get("abilities", [])
    assert len(abilities) == 1, f"Expected 1 ability, got {len(abilities)}"
    assert abilities[0]["type"] == "action", f"Expected action type, got: {abilities[0].get('type')}"
    assert abilities[0].get("effect", {}).get("type") == "put-damage", f"Expected put-damage effect, got: {abilities[0].get('effect')}"
    assert abilities[0].get("effect", {}).get("amount") == 1, f"Expected amount 1, got: {abilities[0].get('effect')}"
    assert abilities[0].get("effect", {}).get("target") == "ALL_OPPOSING_CHARACTERS", f"Expected target ALL_OPPOSING_CHARACTERS, got: {abilities[0].get('effect')}"


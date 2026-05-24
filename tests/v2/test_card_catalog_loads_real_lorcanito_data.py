from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog


def _source_json() -> Path:
    return Path("data/lorcanito_runtime_extracted/cards.normalized.json")


def test_v2_catalog_loads_real_lorcanito_data():
    catalog = CardCatalog.from_lorcanito_normalized_json(_source_json())
    assert len(catalog.cards) >= 2500
    assert catalog.ref == "lorcana:cards"
    chi_fu = catalog.get("XGm")
    assert chi_fu.full_name == "Chi-Fu - Imperial Advisor"
    assert any(ability.kind == "static" for ability in chi_fu.abilities)


def test_v2_catalog_has_lorcanito_catalog_semantics():
    catalog = CardCatalog.from_lorcanito_normalized_json(_source_json(), ref="test:cards")
    assert catalog.ref == "test:cards"
    assert catalog.has("Z2D") is True
    assert catalog.has("missing-card") is False


"""Lorcanito normalized JSON adapter for v2.

This adapter is intentionally independent from legacy ``lorcana_bot`` importers.
It reads normalized card data directly and converts it into v2 dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from .catalog import CardCatalog


def load_lorcanito_catalog(path: str | Path) -> CardCatalog:
    return CardCatalog.from_lorcanito_normalized_json(path)

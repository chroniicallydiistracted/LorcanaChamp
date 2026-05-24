"""LorcanaChamp Rules Kernel v2.

This package is intentionally independent from the legacy ``lorcana_bot``
runtime. v2 may read normalized Lorcanito card data, but v2 core modules must
not import legacy runtime modules from the v1 engine, effects, targeting, or
static-effect packages.

The public package surface exposes the v2 runtime shell, immutable card catalog,
Lorcanito-style static resources, and the current v2 match-state envelope.

Do not re-export the removed scaffold-era ``CardInstance`` shape here. v2 card
identity belongs in ``CardInstanceRecord`` / ``CardInstanceRegistry`` under
``MatchStaticResources``; mutable zone/meta state belongs in ``MatchState``.
"""

from .cards.catalog import CardCatalog
from .core.runtime import MatchRuntime
from .core.state import FrameworkState, GameState, MatchState, PlayerState
from .core.static_resources import (
    CardsMaps,
    CardInstanceRecord,
    CardInstanceRegistry,
    MatchStaticResources,
    StaticResourceRefs,
    create_cards_maps_from_static_resources,
    create_match_static_resources_from_cards_maps,
    get_static_resource_refs,
    validate_match_static_resources,
)

__all__ = [
    "CardCatalog",
    "CardsMaps",
    "CardInstanceRecord",
    "CardInstanceRegistry",
    "FrameworkState",
    "GameState",
    "MatchRuntime",
    "MatchState",
    "MatchStaticResources",
    "PlayerState",
    "StaticResourceRefs",
    "create_cards_maps_from_static_resources",
    "create_match_static_resources_from_cards_maps",
    "get_static_resource_refs",
    "validate_match_static_resources",
]

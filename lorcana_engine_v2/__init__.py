"""LorcanaChamp Rules Kernel v2.

This package is intentionally independent from the legacy ``lorcana_bot``
runtime.  v2 may read normalized Lorcanito card data, but v2 core modules must
not import legacy runtime modules from the v1 engine, effects, targeting, or static-effect packages.
"""

from .core.runtime import MatchRuntime
from .core.state import MatchState, PlayerState, CardInstance
from .cards.catalog import CardCatalog

__all__ = ["MatchRuntime", "MatchState", "PlayerState", "CardInstance", "CardCatalog"]

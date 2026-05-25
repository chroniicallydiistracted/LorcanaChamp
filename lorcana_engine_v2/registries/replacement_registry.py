from __future__ import annotations

from lorcana_engine_v2.effects.replacement_effects import (
    ReplacementRegistration,
    apply_replacement_effects,
    preview_replacement_effects,
    prune_expired_replacement_effects,
    register_replacement_effect,
)


class ReplacementRegistry:
    register = staticmethod(register_replacement_effect)
    apply = staticmethod(apply_replacement_effects)
    preview = staticmethod(preview_replacement_effects)
    prune_expired = staticmethod(prune_expired_replacement_effects)


__all__ = [
    "ReplacementRegistry",
    "ReplacementRegistration",
    "apply_replacement_effects",
    "preview_replacement_effects",
    "prune_expired_replacement_effects",
    "register_replacement_effect",
]

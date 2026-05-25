from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.resolution.action_effects import resolve_action_effect


@dataclass(slots=True)
class EffectResolver:
    """Compatibility adapter for the Lorcanito-shaped action effect resolver."""

    def resolve(self, target, card_played, effect, resolution_input=None, options=None):
        return resolve_action_effect(target, card_played, effect, resolution_input, options)


__all__ = ["EffectResolver"]

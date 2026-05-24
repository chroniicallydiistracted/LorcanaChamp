from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EffectResolver:
    """Effect resolver dispatcher scaffold.

    Future work registers typed handlers in ``effects.handlers``. Handlers must
    use RulesContext services and must not parse legacy card logic directly.
    """

    def resolve(self, state, ctx, effect, resolution_context):
        raise NotImplementedError("v2 effect resolution handlers are not implemented in scaffold")

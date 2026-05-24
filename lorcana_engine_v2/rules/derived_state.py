from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.enums import Stat


@dataclass(frozen=True, slots=True)
class DerivedState:
    """Read-only derived rules queries built from static materialization."""

    def effective_strength(self, state, ctx, instance_id: int) -> int:
        card = ctx.catalog.get(str(state.cards[instance_id].card_id))
        return max(0, card.strength + self._stat_delta(state, ctx, instance_id, Stat.STRENGTH.value))

    def effective_willpower(self, state, ctx, instance_id: int) -> int:
        card = ctx.catalog.get(str(state.cards[instance_id].card_id))
        return max(0, card.willpower + self._stat_delta(state, ctx, instance_id, Stat.WILLPOWER.value))

    def effective_lore(self, state, ctx, instance_id: int) -> int:
        card = ctx.catalog.get(str(state.cards[instance_id].card_id))
        return max(0, card.lore + self._stat_delta(state, ctx, instance_id, Stat.LORE.value))

    def keywords(self, state, ctx, instance_id: int) -> frozenset[str]:
        card = ctx.catalog.get(str(state.cards[instance_id].card_id))
        base = set()
        for ability in card.abilities:
            if ability.kind == "keyword" and ability.raw.get("keyword"):
                base.add(str(ability.raw["keyword"]).upper().replace(" ", "_"))
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "gain-keyword" and instance_id in effect.target_ids:
                keyword = effect.payload.get("keyword")
                if keyword:
                    base.add(str(keyword).upper().replace(" ", "_"))
        return frozenset(base)

    def _stat_delta(self, state, ctx, instance_id: int, stat: str) -> int:
        total = 0
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "modify-stat" and effect.payload.get("stat") == stat and instance_id in effect.target_ids:
                total += int(effect.payload.get("amount", 0))
        return total

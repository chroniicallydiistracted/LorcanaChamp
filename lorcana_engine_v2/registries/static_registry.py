from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.rules.amount_resolver import AmountContext
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext


@dataclass(frozen=True, slots=True)
class MaterializedStaticEffect:
    source_id: int
    source_controller: int
    kind: str
    target_ids: tuple[int, ...]
    payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class StaticRegistry:
    """Materialize continuous effects from active public source cards.

    This intentionally mirrors Lorcanito's derived/static-read model rather than
    v1's entry-time static mutation model.
    """

    def materialize(self, state, ctx) -> tuple[MaterializedStaticEffect, ...]:
        effects: list[MaterializedStaticEffect] = []
        for source_id in ctx.query.public_in_play_ids(state):
            source_card = ctx.catalog.get(str(state.cards[source_id].card_id))
            for ability in source_card.static_abilities():
                condition = ability.raw.get("condition")
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    condition,
                    ConditionContext(actor=int(state.cards[source_id].controller), source_id=source_id, target_id=source_id),
                ):
                    continue
                for effect in ability.effects:
                    materialized = self._materialize_effect(state, ctx, source_id, effect.raw)
                    effects.extend(materialized)
        return tuple(effects)

    def _materialize_effect(self, state, ctx, source_id: int, raw: dict[str, Any]) -> tuple[MaterializedStaticEffect, ...]:
        kind = raw.get("type")
        raw_target = raw.get("target") or "SELF"
        actor = int(state.cards[source_id].controller)
        target_ids = ctx.targets.resolve(state, ctx, raw_target, TargetQueryContext(actor=actor, source_id=source_id))
        if kind == "modify-stat":
            amount_raw = raw.get("amount") if "amount" in raw else raw.get("modifier")
            amount = ctx.amounts.resolve(state, ctx, amount_raw, AmountContext(actor=actor, source_id=source_id))
            return (MaterializedStaticEffect(
                source_id=source_id,
                source_controller=actor,
                kind="modify-stat",
                target_ids=target_ids,
                payload={"stat": str(raw.get("stat") or raw.get("attribute") or "strength"), "amount": amount},
                raw=dict(raw),
            ),)
        if kind in {"gain-keyword", "gain-keywords"}:
            keywords = raw.get("keywords") if "keywords" in raw else raw.get("keyword")
            values = keywords if isinstance(keywords, list) else [keywords]
            return tuple(
                MaterializedStaticEffect(
                    source_id=source_id,
                    source_controller=actor,
                    kind="gain-keyword",
                    target_ids=target_ids,
                    payload={"keyword": keyword},
                    raw=dict(raw),
                )
                for keyword in values if keyword
            )
        return ()

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .target_specs import TargetSpec, normalize_target_spec


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    actor: int
    source_id: int | None = None
    event_payload: dict[str, Any] | None = None


class TargetResolver:
    def resolve(self, state, ctx, raw_target: Any, query: TargetQueryContext) -> tuple[int, ...]:
        spec = normalize_target_spec(raw_target)
        if spec.selector == "self":
            return (query.source_id,) if query.source_id is not None and self._matches(state, ctx, query.source_id, spec, query) else ()
        candidates = []
        for cid in ctx.query.public_in_play_ids(state):
            if self._matches(state, ctx, cid, spec, query):
                candidates.append(cid)
        return tuple(candidates)

    def _matches(self, state, ctx, instance_id: int, spec: TargetSpec, query: TargetQueryContext) -> bool:
        inst = state.cards.get(instance_id)
        if inst is None or inst.zone not in spec.zones:
            return False
        if inst.stack_parent_id is not None:
            return False
        if spec.exclude_self and query.source_id is not None and instance_id == query.source_id:
            return False
        if spec.controller == "you" and int(inst.controller) != int(query.actor):
            return False
        if spec.controller == "opponent" and int(inst.controller) == int(query.actor):
            return False
        if spec.owner == "you" and int(inst.owner) != int(query.actor):
            return False
        if spec.owner == "opponent" and int(inst.owner) == int(query.actor):
            return False
        card = ctx.catalog.get(str(inst.card_id))
        if spec.card_types and card.card_type not in spec.card_types and "card" not in spec.card_types:
            return False
        for filter_def in spec.filters:
            if not self._filter_matches(state, ctx, instance_id, filter_def, query):
                return False
        return True

    def _filter_matches(self, state, ctx, instance_id: int, filter_def: dict[str, Any], query: TargetQueryContext) -> bool:
        kind = filter_def.get("type")
        if kind in {"has-classification", "classification"}:
            classification = filter_def.get("classification") or filter_def.get("value")
            return bool(classification and ctx.query.has_classification(state, instance_id, str(classification)))
        if kind == "has-name":
            card = ctx.catalog.get(str(state.cards[instance_id].card_id))
            expected = str(filter_def.get("name") or filter_def.get("value") or "")
            return card.name == expected or card.full_name == expected
        if kind == "damaged":
            return state.cards[instance_id].damage > 0
        if kind == "ready":
            return not state.cards[instance_id].exerted
        if kind == "exerted":
            return state.cards[instance_id].exerted
        # Unknown filters are intentionally false so report integration can stay honest.
        return False

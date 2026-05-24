from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import base_zone_from_key

from .target_specs import TargetSpec, normalize_target_spec


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    actor: PlayerId | str
    source_id: InstanceId | str | None = None
    event_payload: dict[str, Any] | None = None

    @property
    def actor_id(self) -> PlayerId:
        return PlayerId(str(self.actor))

    @property
    def source_instance_id(self) -> InstanceId | None:
        return InstanceId(str(self.source_id)) if self.source_id is not None else None


class TargetResolver:
    def resolve(self, state, ctx, raw_target: Any, query: TargetQueryContext) -> tuple[InstanceId, ...]:
        spec = normalize_target_spec(raw_target)
        if spec.selector == "self":
            source_id = query.source_instance_id
            return (source_id,) if source_id is not None and self._matches(state, ctx, source_id, spec, query) else ()
        candidates = []
        for instance_id in ctx.query.public_in_play_ids(state):
            if self._matches(state, ctx, instance_id, spec, query):
                candidates.append(instance_id)
        return tuple(candidates)

    def _matches(self, state, ctx, instance_id: InstanceId, spec: TargetSpec, query: TargetQueryContext) -> bool:
        runtime_card = ctx.query.runtime_card(state, instance_id)
        if runtime_card.zone_id is None:
            return False
        if spec.zones and base_zone_from_key(runtime_card.zone_id) not in {ZoneId(str(zone)) for zone in spec.zones}:
            return False
        if runtime_card.meta.stack_parent_id is not None:
            return False
        if spec.exclude_self and query.source_instance_id is not None and instance_id == query.source_instance_id:
            return False
        if spec.controller == "you" and runtime_card.controller_id != query.actor_id:
            return False
        if spec.controller == "opponent" and runtime_card.controller_id == query.actor_id:
            return False
        if spec.owner == "you" and runtime_card.owner_id != query.actor_id:
            return False
        if spec.owner == "opponent" and runtime_card.owner_id == query.actor_id:
            return False
        card = runtime_card.definition
        if spec.card_types and card.card_type not in spec.card_types and "card" not in spec.card_types:
            return False
        for filter_def in spec.filters:
            if not self._filter_matches(state, ctx, instance_id, filter_def, query):
                return False
        return True

    def _filter_matches(self, state, ctx, instance_id: InstanceId, filter_def: dict[str, Any], query: TargetQueryContext) -> bool:
        kind = filter_def.get("type")
        runtime_card = ctx.query.runtime_card(state, instance_id)
        if kind in {"has-classification", "classification"}:
            classification = filter_def.get("classification") or filter_def.get("value")
            return bool(classification and ctx.query.has_classification(state, instance_id, str(classification)))
        if kind == "has-name":
            expected = str(filter_def.get("name") or filter_def.get("value") or "")
            return runtime_card.definition.name == expected or runtime_card.definition.full_name == expected
        if kind == "damaged":
            return runtime_card.meta.damage > 0
        if kind == "ready":
            return not runtime_card.meta.exerted
        if kind == "exerted":
            return runtime_card.meta.exerted
        # Unknown filters are intentionally false so report integration can stay honest.
        return False

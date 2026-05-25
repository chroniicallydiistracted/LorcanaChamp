from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import base_zone_from_key

from .target_specs import TargetSpec, normalize_target_spec


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    actor: PlayerId | str
    source_id: InstanceId | str | None = None
    event_payload: Mapping[str, Any] | None = None
    selected_targets: tuple[InstanceId, ...] = ()
    strict_unknown_filters: bool = True

    @property
    def actor_id(self) -> PlayerId:
        return PlayerId(str(self.actor))

    @property
    def source_instance_id(self) -> InstanceId | None:
        return InstanceId(str(self.source_id)) if self.source_id is not None else None


def normalize_target_descriptor(raw: Any) -> TargetSpec | None:
    try:
        return normalize_target_spec(raw)
    except TypeError:
        return None


class TargetResolver:
    def resolve(self, state, ctx, raw_target: Any, query: TargetQueryContext) -> tuple[InstanceId, ...]:
        spec = normalize_target_descriptor(raw_target)
        if spec is None:
            return ()

        if spec.selector in {"self", "source"}:
            source_id = query.source_instance_id
            return (source_id,) if source_id is not None and self._matches(state, ctx, source_id, spec, query) else ()

        candidates: list[InstanceId] = []
        seen: set[InstanceId] = set()
        for instance_id in self._candidate_card_ids(state, spec):
            if instance_id in seen:
                continue
            if self._matches(state, ctx, instance_id, spec, query):
                seen.add(instance_id)
                candidates.append(instance_id)
        return tuple(candidates)

    def _candidate_card_ids(self, state, spec: TargetSpec) -> tuple[InstanceId, ...]:
        ids: list[InstanceId] = []
        requested_zones = {ZoneId(str(zone)) for zone in spec.zones}
        for zone_key, card_ids in state.ctx.zones.private.zoneCards.items():
            if requested_zones and base_zone_from_key(zone_key) not in requested_zones and zone_key not in requested_zones:
                continue
            ids.extend(card_ids)
        return tuple(ids)

    def _base_card(self, state, ctx, instance_id: InstanceId):
        if hasattr(ctx.query, "base_runtime_card"):
            return ctx.query.base_runtime_card(state, instance_id)
        return ctx.query.runtime_card(state, instance_id)

    def _runtime_card(self, state, ctx, instance_id: InstanceId):
        try:
            return ctx.query.runtime_card(state, instance_id)
        except RecursionError:
            return self._base_card(state, ctx, instance_id)

    def _matches(self, state, ctx, instance_id: InstanceId, spec: TargetSpec, query: TargetQueryContext) -> bool:
        runtime_card = self._base_card(state, ctx, instance_id)
        if runtime_card.zoneID is None:
            return False
        if spec.zones and base_zone_from_key(runtime_card.zoneID) not in {ZoneId(str(zone)) for zone in spec.zones}:
            return False
        if runtime_card.meta.stackParentId is not None:
            return False
        if spec.exclude_self and query.source_instance_id is not None and instance_id == query.source_instance_id:
            return False

        if spec.controller == "you" and runtime_card.controllerID != query.actor_id:
            return False
        if spec.controller == "opponent" and runtime_card.controllerID == query.actor_id:
            return False
        if spec.owner == "you" and runtime_card.ownerID != query.actor_id:
            return False
        if spec.owner == "opponent" and runtime_card.ownerID == query.actor_id:
            return False

        card = runtime_card.definition
        if spec.card_types and card.card_type not in spec.card_types and "card" not in spec.card_types:
            is_song = card.card_type == "action" and card.raw.get("actionSubtype") == "song"
            if not (is_song and "song" in spec.card_types):
                return False

        for filter_def in spec.filters:
            if not self._filter_matches(state, ctx, instance_id, filter_def, query):
                return False
        return True

    def _filter_matches(self, state, ctx, instance_id: InstanceId, filter_def: Mapping[str, Any], query: TargetQueryContext) -> bool:
        kind = filter_def.get("type")
        runtime_card = self._base_card(state, ctx, instance_id)

        if kind in {"or", "any"}:
            return any(self._filter_matches(state, ctx, instance_id, item, query) for item in filter_def.get("filters", ()))
        if kind == "and":
            return all(self._filter_matches(state, ctx, instance_id, item, query) for item in filter_def.get("filters", ()))
        if kind == "not":
            nested = filter_def.get("filter") or filter_def.get("condition")
            return isinstance(nested, Mapping) and not self._filter_matches(state, ctx, instance_id, nested, query)
        if kind in {"has-classification", "classification"}:
            classification = filter_def.get("classification") or filter_def.get("value")
            return bool(
                classification
                and any(
                    str(item).lower() == str(classification).lower()
                    for item in runtime_card.definition.classifications
                )
            )
        if kind in {"card-type", "cardType"}:
            value = filter_def.get("value") or filter_def.get("cardType")
            return runtime_card.definition.card_type == value
        if kind in {"name", "has-name"}:
            expected = str(filter_def.get("name") or filter_def.get("value") or filter_def.get("equals") or "")
            return runtime_card.definition.name == expected or runtime_card.definition.full_name == expected
        if kind in {"status", "damaged"}:
            status = filter_def.get("status") or ("damaged" if kind == "damaged" else None)
            if status == "damaged":
                return (runtime_card.meta.damage or 0) > 0
            if status == "ready":
                return runtime_card.meta.state != "exerted"
            if status == "exerted":
                return runtime_card.meta.state == "exerted"
            if status == "drying":
                return bool(runtime_card.meta.isDrying)
            return False
        if kind == "ready":
            return runtime_card.meta.state != "exerted"
        if kind == "exerted":
            return runtime_card.meta.state == "exerted"
        if kind == "cost":
            return self._compare(runtime_card.definition.cost, filter_def)
        if kind in {"strength", "strength-comparison"}:
            return self._compare(runtime_card.definition.strength, filter_def)
        if kind in {"willpower", "willpower-comparison"}:
            return self._compare(runtime_card.definition.willpower, filter_def)
        if kind in {"lore", "lore-comparison", "lore-value"}:
            return self._compare(runtime_card.definition.lore, filter_def)
        if kind == "same-location-as-source":
            source_id = query.source_instance_id
            return (
                source_id is not None
                and runtime_card.meta.atLocationId is not None
                and runtime_card.meta.atLocationId == ctx.query.get_meta(state, source_id).atLocationId
            )

        return not query.strict_unknown_filters

    def _compare(self, actual: int, filter_def: Mapping[str, Any]) -> bool:
        operator = str(filter_def.get("comparison") or filter_def.get("operator") or filter_def.get("op") or "equal")
        expected = int(filter_def.get("value", filter_def.get("amount", 0)) or 0)
        normalized = operator.lower().replace("_", "-")
        if normalized in {"eq", "equal", "equals", "=="}:
            return actual == expected
        if normalized in {"gt", "greater", ">"}:
            return actual > expected
        if normalized in {"gte", "or-more", "greater-or-equal", ">="}:
            return actual >= expected
        if normalized in {"lt", "less", "<"}:
            return actual < expected
        if normalized in {"lte", "or-less", "less-or-equal", "<="}:
            return actual <= expected
        if normalized in {"neq", "not-equal", "!="}:
            return actual != expected
        return False


__all__ = [
    "TargetQueryContext",
    "TargetResolver",
    "normalize_target_descriptor",
]

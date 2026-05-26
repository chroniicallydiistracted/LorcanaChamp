from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.core.turn_owner import resolve_turn_owner_id


@dataclass(frozen=True, slots=True)
class ConditionContext:
    actor: PlayerId | str
    source_id: InstanceId | str | None = None
    target_id: InstanceId | str | None = None
    event_payload: Mapping[str, Any] | None = None

    @property
    def actor_id(self) -> PlayerId:
        return PlayerId(str(self.actor))

    @property
    def source_instance_id(self) -> InstanceId | None:
        return InstanceId(str(self.source_id)) if self.source_id is not None else None

    @property
    def target_instance_id(self) -> InstanceId | None:
        return InstanceId(str(self.target_id)) if self.target_id is not None else None


def _compare(left: int, operator: str, right: int) -> bool:
    normalized = operator.lower().replace("_", "-")
    if normalized in {"eq", "equal", "equals", "=="}:
        return left == right
    if normalized in {"neq", "not-equal", "!="}:
        return left != right
    if normalized in {"gt", "greater", "greater-than", ">"}:
        return left > right
    if normalized in {"gte", "or-more", "greater-or-equal", "greater-than-or-equal", ">="}:
        return left >= right
    if normalized in {"lt", "less", "less-than", "<"}:
        return left < right
    if normalized in {"lte", "or-less", "less-or-equal", "less-than-or-equal", "<="}:
        return left <= right
    return False


def _comparison_parts(raw_condition: Mapping[str, Any]) -> tuple[str, int]:
    comparison = raw_condition.get("comparison")
    if isinstance(comparison, Mapping):
        return str(comparison.get("operator", "gte")), int(comparison.get("value", 1) or 0)
    return str(comparison or raw_condition.get("operator") or "gte"), int(
        raw_condition.get("count", raw_condition.get("value", 1)) or 0
    )


class ConditionEvaluator:
    def evaluate(self, state, ctx, raw_condition: Any, context: ConditionContext) -> bool:
        if raw_condition is None:
            return True
        if not isinstance(raw_condition, Mapping):
            return False

        kind = raw_condition.get("type") or raw_condition.get("kind")
        if kind in {None, "always", "if-you-do"}:
            return True
        if kind == "not":
            return not self.evaluate(state, ctx, raw_condition.get("condition"), context)
        if kind == "and":
            return all(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        if kind == "or":
            return any(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        if kind == "if":
            return self.evaluate(state, ctx, raw_condition.get("condition"), context)

        if kind in {"no-damage", "has-no-damage"}:
            target = context.target_instance_id or context.source_instance_id
            return target is not None and (ctx.query.get_meta(state, target).damage or 0) <= 0
        if kind in {"has-any-damage", "self-has-damage"}:
            target = context.target_instance_id or context.source_instance_id
            return target is not None and (ctx.query.get_meta(state, target).damage or 0) > 0
        if kind in {"exerted", "is-exerted"}:
            target = context.target_instance_id or context.source_instance_id
            return target is not None and ctx.query.get_meta(state, target).state == "exerted"
        if kind in {"your-turn", "during-turn", "turn"}:
            return self._evaluate_turn_condition(state, raw_condition, context)
        if kind in {"first-turn-non-otp"}:
            return state.ctx.status.turn == 1 and state.ctx.status.otp != context.actor_id
        if kind == "inkwell-count":
            operator, value = _comparison_parts(raw_condition)
            return _compare(
                self._zone_count(state, "inkwell", self._player_for_controller(state, raw_condition.get("controller"), context)),
                operator,
                value,
            )
        if kind == "resource-count":
            operator, value = _comparison_parts(raw_condition)
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            what = raw_condition.get("what")
            zone = {
                "cards-in-hand": "hand",
                "cards-in-inkwell": "inkwell",
                "cards-in-discard": "discard",
            }.get(str(what), str(what or "hand"))
            return _compare(self._zone_count(state, zone, player_id), operator, value)
        if kind in {"has-character-count", "has-item-count", "has-location-count"}:
            card_type = {
                "has-character-count": "character",
                "has-item-count": "item",
                "has-location-count": "location",
            }[str(kind)]
            operator, value = _comparison_parts(raw_condition)
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            count = self._count_in_play(state, ctx, player_id, card_type, raw_condition.get("classification"))
            return _compare(count, operator, value)
        if kind == "has-another-character":
            source_id = context.source_instance_id
            return any(card_id != source_id for card_id in ctx.query.characters_in_play(state, context.actor_id))
        if kind == "has-character-with-classification":
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            classification = raw_condition.get("classification")
            return self._count_in_play(state, ctx, player_id, "character", classification) > 0
        if kind == "has-character-with-keyword":
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            keyword = str(raw_condition.get("keyword") or "")
            return any(
                keyword in ctx.query.runtime_card(state, card_id).keywords
                for card_id in ctx.query.characters_in_play(state, player_id)
            )
        if kind == "has-character-with-strength":
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            operator, value = _comparison_parts(raw_condition)
            return any(
                _compare(ctx.query.runtime_card(state, card_id).strength, operator, value)
                for card_id in ctx.query.characters_in_play(state, player_id)
            )
        if kind in {"has-named-character", "has-named-item"}:
            card_type = "character" if kind == "has-named-character" else "item"
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            expected = str(raw_condition.get("name") or "")
            return any(
                self._definition_matches_name(ctx.query.card(state, card_id), expected)
                for card_id in self._ids_of_type(state, ctx, player_id, card_type)
            )
        if kind == "has-location-in-play":
            player_id = self._player_for_controller(state, raw_condition.get("controller"), context)
            return bool(ctx.query.locations_in_play(state, player_id))
        if kind == "is-named":
            target = context.target_instance_id or context.source_instance_id
            expected = str(raw_condition.get("name") or raw_condition.get("value") or "")
            return target is not None and self._definition_matches_name(ctx.query.card(state, target), expected)
        if kind == "stat-threshold":
            target = context.target_instance_id or context.source_instance_id
            if target is None:
                return False
            operator, value = _comparison_parts(raw_condition)
            stat = str(raw_condition.get("stat") or "strength")
            runtime_card = ctx.query.runtime_card(state, target)
            actual = getattr(runtime_card, stat if stat != "move-cost" else "moveCost", 0)
            return _compare(int(actual), operator, value)
        if kind == "target-query":
            from lorcana_engine_v2.rules.target_resolver import TargetQueryContext

            result = ctx.targets.resolve(
                state,
                ctx,
                raw_condition.get("query"),
                TargetQueryContext(actor=context.actor_id, source_id=context.source_instance_id),
            )
            operator, value = _comparison_parts(raw_condition)
            return _compare(len(result), operator, value)

        return False

    def _evaluate_turn_condition(self, state, raw_condition: Mapping[str, Any], context: ConditionContext) -> bool:
        whose = raw_condition.get("whose")
        turn_owner = resolve_turn_owner_id(state)
        if whose in {"your", "you", "controller"}:
            return turn_owner == context.actor_id
        if whose == "opponent":
            return turn_owner is not None and turn_owner != context.actor_id
        return turn_owner == context.actor_id

    def _player_for_controller(self, state, controller: object, context: ConditionContext) -> PlayerId:
        if controller == "opponent":
            return state.opponent(context.actor_id)
        return context.actor_id

    def _zone_count(self, state, zone: str, player_id: PlayerId) -> int:
        zone_id = ZoneId(f"{zone}:{player_id}")
        return len(state.ctx.zones.private.zoneCards.get(zone_id, ()))

    def _ids_of_type(self, state, ctx, player_id: PlayerId, card_type: str) -> tuple[InstanceId, ...]:
        if card_type == "character":
            return ctx.query.characters_in_play(state, player_id)
        if card_type == "item":
            return ctx.query.items_in_play(state, player_id)
        if card_type == "location":
            return ctx.query.locations_in_play(state, player_id)
        return ()

    def _count_in_play(self, state, ctx, player_id: PlayerId, card_type: str, classification: object = None) -> int:
        count = 0
        for card_id in self._ids_of_type(state, ctx, player_id, card_type):
            if classification and not ctx.query.has_classification(state, card_id, str(classification)):
                continue
            count += 1
        return count

    def _definition_matches_name(self, definition, expected: str) -> bool:
        return definition.name == expected or definition.full_name == expected


__all__ = ["ConditionContext", "ConditionEvaluator"]

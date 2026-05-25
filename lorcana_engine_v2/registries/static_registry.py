from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Mapping

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.rules.amount_resolver import AmountContext, AmountResolver
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator
from lorcana_engine_v2.rules.queries import QueryService
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext, TargetResolver


MaterializedEffectKind = str


@dataclass(frozen=True, slots=True)
class MaterializedStaticEffect:
    sourceId: InstanceId
    sourceControllerId: PlayerId
    abilityIndex: int
    kind: MaterializedEffectKind
    payload: Mapping[str, Any] = field(default_factory=dict)
    abilityName: str | None = None
    sourceDefinitionId: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StaticEffectRegistry:
    byTarget: Mapping[InstanceId, tuple[MaterializedStaticEffect, ...]] = field(default_factory=dict)
    byPlayer: Mapping[PlayerId, tuple[MaterializedStaticEffect, ...]] = field(default_factory=dict)
    globalEffects: tuple[MaterializedStaticEffect, ...] = ()
    bySource: Mapping[InstanceId, tuple[MaterializedStaticEffect, ...]] = field(default_factory=dict)

    def get_effects_for_card(
        self,
        card_id: InstanceId | str,
        *,
        kind: str | None = None,
    ) -> tuple[MaterializedStaticEffect, ...]:
        effects = self.byTarget.get(InstanceId(str(card_id)), ())
        if kind is None:
            return effects
        return tuple(effect for effect in effects if effect.kind == kind)

    def get_effects_for_player(
        self,
        player_id: PlayerId | str,
        *,
        kind: str | None = None,
    ) -> tuple[MaterializedStaticEffect, ...]:
        effects = self.byPlayer.get(PlayerId(str(player_id)), ())
        if kind is None:
            return effects
        return tuple(effect for effect in effects if effect.kind == kind)

    def get_effects_from_card(
        self,
        source_id: InstanceId | str,
        *,
        kind: str | None = None,
    ) -> tuple[MaterializedStaticEffect, ...]:
        effects = self.bySource.get(InstanceId(str(source_id)), ())
        if kind is None:
            return effects
        return tuple(effect for effect in effects if effect.kind == kind)


def getEffectsForCard(
    registry: StaticEffectRegistry,
    card_id: InstanceId | str,
    kind: str | None = None,
) -> tuple[MaterializedStaticEffect, ...]:
    return registry.get_effects_for_card(card_id, kind=kind)


def getEffectsForPlayer(
    registry: StaticEffectRegistry,
    player_id: PlayerId | str,
    kind: str | None = None,
) -> tuple[MaterializedStaticEffect, ...]:
    return registry.get_effects_for_player(player_id, kind=kind)


def getEffectsFromCard(
    registry: StaticEffectRegistry,
    source_id: InstanceId | str,
    kind: str | None = None,
) -> tuple[MaterializedStaticEffect, ...]:
    return registry.get_effects_from_card(source_id, kind=kind)


class StaticRegistry:
    """Build Lorcanito-style static-effect indexes from active source cards."""

    def build(self, state: MatchState, query: QueryService) -> StaticEffectRegistry:
        by_target: dict[InstanceId, list[MaterializedStaticEffect]] = {}
        by_player: dict[PlayerId, list[MaterializedStaticEffect]] = {}
        global_effects: list[MaterializedStaticEffect] = []
        by_source: dict[InstanceId, list[MaterializedStaticEffect]] = {}

        ctx = self._build_context(query)
        for source_id in query.public_in_play_ids(state):
            source_def = query.card(state, source_id)
            source_entry = state.ctx.zones.private.cardIndex.get(source_id)
            if source_entry is None:
                continue
            source_controller = source_entry.controllerID
            for ability_index, ability in enumerate(source_def.abilities):
                if ability.kind != "static":
                    continue
                source_zones = ability.source_zones or tuple(ability.raw.get("sourceZones") or ("play",))
                if "play" not in source_zones:
                    continue
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    ability.raw.get("condition"),
                    ConditionContext(actor=source_controller, source_id=source_id, target_id=source_id),
                ):
                    continue
                effect = ability.raw.get("effect")
                if not isinstance(effect, Mapping):
                    continue
                for materialized in self._materialize_effect(
                    state=state,
                    ctx=ctx,
                    source_id=source_id,
                    source_controller=source_controller,
                    source_definition_id=source_def.id,
                    ability_index=ability_index,
                    ability_name=ability.name,
                    raw_effect=effect,
                ):
                    by_source.setdefault(source_id, []).append(materialized)
                    if materialized.kind in {"cost-increase", "restriction"} and materialized.payload.get("playerTarget") == "ALL_PLAYERS":
                        global_effects.append(materialized)
                        continue
                    player_id = materialized.payload.get("playerId")
                    if player_id is not None:
                        by_player.setdefault(PlayerId(str(player_id)), []).append(materialized)
                        continue
                    target_ids = materialized.payload.get("targetIds")
                    if isinstance(target_ids, tuple):
                        for target_id in target_ids:
                            by_target.setdefault(InstanceId(str(target_id)), []).append(materialized)

        return StaticEffectRegistry(
            byTarget={key: tuple(value) for key, value in by_target.items()},
            byPlayer={key: tuple(value) for key, value in by_player.items()},
            globalEffects=tuple(global_effects),
            bySource={key: tuple(value) for key, value in by_source.items()},
        )

    def materialize(self, state: MatchState, ctx) -> tuple[MaterializedStaticEffect, ...]:
        registry = self.build(state, ctx.query)
        effects: list[MaterializedStaticEffect] = []
        for bucket in registry.byTarget.values():
            effects.extend(bucket)
        for bucket in registry.byPlayer.values():
            effects.extend(bucket)
        effects.extend(registry.globalEffects)
        return tuple(effects)

    def _build_context(self, query: QueryService):
        return SimpleNamespace(
            query=query,
            targets=TargetResolver(),
            conditions=ConditionEvaluator(),
            amounts=AmountResolver(),
            static=self,
        )

    def _materialize_effect(
        self,
        *,
        state: MatchState,
        ctx,
        source_id: InstanceId,
        source_controller: PlayerId,
        source_definition_id: str,
        ability_index: int,
        ability_name: str | None,
        raw_effect: Mapping[str, Any],
    ) -> tuple[MaterializedStaticEffect, ...]:
        effect_type = str(raw_effect.get("type") or "")

        if effect_type == "conditional":
            condition = raw_effect.get("condition")
            if not ctx.conditions.evaluate(
                state,
                ctx,
                condition,
                ConditionContext(actor=source_controller, source_id=source_id, target_id=source_id),
            ):
                return ()
            next_effect = raw_effect.get("then") or raw_effect.get("effect") or raw_effect.get("ifTrue")
            if isinstance(next_effect, Mapping):
                return self._materialize_effect(
                    state=state,
                    ctx=ctx,
                    source_id=source_id,
                    source_controller=source_controller,
                    source_definition_id=source_definition_id,
                    ability_index=ability_index,
                    ability_name=ability_name,
                    raw_effect=next_effect,
                )
            return ()

        if effect_type == "modify-stat":
            target_ids = self._resolve_card_targets(state, ctx, raw_effect.get("target", "SELF"), source_controller, source_id)
            raw_amount = raw_effect.get("modifier", raw_effect.get("amount", 0))
            effects: list[MaterializedStaticEffect] = []
            for target_id in target_ids:
                amount = ctx.amounts.resolve(
                    state,
                    ctx,
                    raw_amount,
                    AmountContext(actor=source_controller, source_id=source_id, target_id=target_id),
                )
                effects.append(
                    self._effect(
                        source_id,
                        source_controller,
                        source_definition_id,
                        ability_index,
                        ability_name,
                        "modify-stat",
                        {
                            "targetIds": (target_id,),
                            "stat": str(raw_effect.get("stat") or raw_effect.get("attribute") or "strength"),
                            "modifier": amount,
                        },
                        raw_effect,
                    )
                )
            return tuple(effects)

        if effect_type == "stat-floor":
            target_ids = self._resolve_card_targets(state, ctx, raw_effect.get("target", "SELF"), source_controller, source_id)
            return tuple(
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "stat-floor",
                    {
                        "targetIds": (target_id,),
                        "stat": str(raw_effect.get("stat") or "strength"),
                        "floor": raw_effect.get("minimum", raw_effect.get("floor", 0)),
                    },
                    raw_effect,
                )
                for target_id in target_ids
            )

        if effect_type in {"gain-keyword", "gain-keywords"}:
            target_ids = self._resolve_card_targets(state, ctx, raw_effect.get("target", "SELF"), source_controller, source_id)
            keywords = raw_effect.get("keywords") if "keywords" in raw_effect else raw_effect.get("keyword")
            keyword_values = keywords if isinstance(keywords, (tuple, list)) else (keywords,)
            return tuple(
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "gain-keyword",
                    {
                        "targetIds": tuple(target_ids),
                        "keyword": str(keyword),
                        "value": raw_effect.get("value"),
                    },
                    raw_effect,
                )
                for keyword in keyword_values
                if keyword
            )

        if effect_type == "lose-keyword":
            target_ids = self._resolve_card_targets(state, ctx, raw_effect.get("target", "SELF"), source_controller, source_id)
            keyword = raw_effect.get("keyword")
            if not keyword:
                return ()
            return (
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "lose-keyword",
                    {"targetIds": tuple(target_ids), "keyword": str(keyword)},
                    raw_effect,
                ),
            )

        if (
            effect_type == "property-modification"
            and raw_effect.get("property") == "classification"
            and raw_effect.get("operation", "add") == "add"
        ):
            target_ids = self._resolve_card_targets(state, ctx, raw_effect.get("target", "SELF"), source_controller, source_id)
            classification = raw_effect.get("value")
            if not classification:
                return ()
            return tuple(
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "grant-classification",
                    {"targetIds": (target_id,), "classification": str(classification)},
                    raw_effect,
                )
                for target_id in target_ids
            )

        if effect_type == "restriction":
            target = raw_effect.get("target", "SELF")
            restriction = str(raw_effect.get("restriction") or "")
            if target in {"CONTROLLER", "YOU"}:
                return (
                    self._effect(
                        source_id,
                        source_controller,
                        source_definition_id,
                        ability_index,
                        ability_name,
                        "restriction",
                        {
                            "playerId": source_controller,
                            "playerTarget": "CONTROLLER",
                            "restriction": restriction,
                        },
                        raw_effect,
                    ),
                )
            target_ids = self._resolve_card_targets(state, ctx, target, source_controller, source_id)
            return tuple(
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "restriction",
                    {"targetIds": (target_id,), "restriction": restriction},
                    raw_effect,
                )
                for target_id in target_ids
            )

        if effect_type == "cost-reduction":
            return (
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "cost-reduction",
                    {
                        "playerId": source_controller,
                        "amount": raw_effect.get("amount", raw_effect.get("reduction", 0)),
                        "cardType": raw_effect.get("cardType"),
                        "classification": raw_effect.get("classification"),
                        "cardName": raw_effect.get("cardName"),
                        "playMethod": raw_effect.get("playMethod"),
                    },
                    raw_effect,
                ),
            )

        if effect_type == "cost-increase":
            return (
                self._effect(
                    source_id,
                    source_controller,
                    source_definition_id,
                    ability_index,
                    ability_name,
                    "cost-increase",
                    {
                        "playerTarget": "ALL_PLAYERS",
                        "amount": raw_effect.get("amount", raw_effect.get("increase", 0)),
                        "cardType": raw_effect.get("cardType"),
                    },
                    raw_effect,
                ),
            )

        return ()

    def _resolve_card_targets(
        self,
        state: MatchState,
        ctx,
        raw_target: object,
        source_controller: PlayerId,
        source_id: InstanceId,
    ) -> tuple[InstanceId, ...]:
        return ctx.targets.resolve(
            state,
            ctx,
            raw_target,
            TargetQueryContext(actor=source_controller, source_id=source_id),
        )

    def _effect(
        self,
        source_id: InstanceId,
        source_controller: PlayerId,
        source_definition_id: str,
        ability_index: int,
        ability_name: str | None,
        kind: str,
        payload: Mapping[str, Any],
        raw: Mapping[str, Any],
    ) -> MaterializedStaticEffect:
        return MaterializedStaticEffect(
            sourceId=source_id,
            sourceControllerId=source_controller,
            sourceDefinitionId=source_definition_id,
            abilityIndex=ability_index,
            abilityName=ability_name,
            kind=kind,
            payload=dict(payload),
            raw=dict(raw),
        )


def buildStaticEffectRegistry(state: MatchState, query: QueryService) -> StaticEffectRegistry:
    return StaticRegistry().build(state, query)


__all__ = [
    "MaterializedStaticEffect",
    "StaticEffectRegistry",
    "StaticRegistry",
    "buildStaticEffectRegistry",
    "getEffectsForCard",
    "getEffectsForPlayer",
    "getEffectsFromCard",
]

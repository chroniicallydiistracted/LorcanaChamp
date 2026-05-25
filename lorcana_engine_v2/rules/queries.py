from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.static_resources import MatchStaticResources
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, base_zone_from_key


RuntimeCardDeriver = Callable[
    [MatchState, "RuntimeCardBase", MatchStaticResources, PlayerId | None, object | None],
    Mapping[str, object],
]


@dataclass(frozen=True, slots=True)
class RuntimeCardBase:
    instanceId: InstanceId
    definitionId: str
    ownerID: PlayerId
    controllerID: PlayerId
    zoneID: ZoneId | None
    zoneIndex: int | None
    meta: CardMeta
    definition: CardDefinition


@dataclass(frozen=True, slots=True)
class RuntimeCard(RuntimeCardBase):
    strength: int = 0
    willpower: int = 0
    lore: int = 0
    playCost: int = 0
    shiftInkCost: int | None = None
    shiftPlayCost: int | None = None
    moveCost: int = 0
    damage: int = 0
    exerted: bool = False
    drying: bool = False
    canBePutInInkwell: bool = False
    hasSupport: bool = False
    hasRush: bool = False
    hasReckless: bool = False
    hasEvasive: bool = False
    hasQuestRestriction: bool = False
    fullName: str = ""
    keywords: tuple[str, ...] = ()
    keywordValues: Mapping[str, int] = field(default_factory=dict)
    classifications: tuple[str, ...] = ()
    temporaryAbilities: Mapping[str, object] = field(default_factory=dict)
    temporaryAbilityStarts: Mapping[str, int] = field(default_factory=dict)
    temporaryRestrictions: Mapping[str, object] = field(default_factory=dict)
    temporaryRestrictionStarts: Mapping[str, int] = field(default_factory=dict)
    grantedAbilityTextEntries: tuple[object, ...] = ()


def create_lorcana_runtime_card_deriver(registry: object | None = None) -> RuntimeCardDeriver:
    from lorcana_engine_v2.rules.derived_state import derive_runtime_card_fields

    def deriver(
        state: MatchState,
        card: RuntimeCardBase,
        static_resources: MatchStaticResources,
        actor_player_id: PlayerId | None,
        runtime_card_cache: object | None = None,
    ) -> Mapping[str, object]:
        _ = runtime_card_cache
        return derive_runtime_card_fields(
            state=state,
            card=card,
            static_resources=static_resources,
            actor_player_id=actor_player_id,
            registry=registry,
        )

    return deriver


@dataclass(slots=True)
class QueryService:
    resources: MatchStaticResources
    actorPlayerId: PlayerId | None = None
    deriveRuntimeCard: RuntimeCardDeriver | None = None
    runtimeCardCache: object | None = None
    cacheViews: bool = True
    _card_view_cache: dict[InstanceId, RuntimeCard] = field(default_factory=dict)
    _card_view_cache_state_id: int | None = None
    _card_view_cache_static_effects_version: int | None = None

    def with_actor(self, actor_player_id: PlayerId | str | None) -> "QueryService":
        return QueryService(
            resources=self.resources,
            actorPlayerId=PlayerId(str(actor_player_id)) if actor_player_id is not None else None,
            deriveRuntimeCard=self.deriveRuntimeCard,
            runtimeCardCache=self.runtimeCardCache,
            cacheViews=self.cacheViews,
        )

    def _clear_cache_if_needed(self, state: MatchState) -> None:
        if not self.cacheViews:
            return
        static_effects_version = getattr(state.G, "staticEffectsVersion", 0)
        if (
            self._card_view_cache_state_id != state.ctx._stateID
            or self._card_view_cache_static_effects_version != static_effects_version
        ):
            self._card_view_cache.clear()
            self._card_view_cache_state_id = state.ctx._stateID
            self._card_view_cache_static_effects_version = static_effects_version

    def _base_runtime_card(self, state: MatchState, instance_id: InstanceId | str) -> RuntimeCardBase:
        iid = InstanceId(str(instance_id))
        record = self.resources.instances.require(iid)
        definition = self.resources.cards.get(str(record.definition_id))
        index = state.ctx.zones.private.cardIndex.get(iid)
        meta = state.ctx.zones.private.cardMeta.get(iid, CardMeta())
        return RuntimeCardBase(
            instanceId=iid,
            definitionId=str(record.definition_id),
            ownerID=index.ownerID if index is not None else record.owner_id,
            controllerID=index.controllerID if index is not None else record.owner_id,
            zoneID=index.zoneKey if index is not None else None,
            zoneIndex=index.index if index is not None else None,
            meta=meta,
            definition=definition,
        )

    def base_runtime_card(self, state: MatchState, instance_id: InstanceId | str) -> RuntimeCardBase:
        return self._base_runtime_card(state, instance_id)

    def _registry_for(self, state: MatchState):
        from lorcana_engine_v2.registries.static_registry import StaticRegistry

        return StaticRegistry().build(state, self)

    def _build_card_view(
        self,
        state: MatchState,
        instance_id: InstanceId | str,
        *,
        actor_player_id: PlayerId | str | None = None,
        registry: object | None = None,
    ) -> RuntimeCard:
        iid = InstanceId(str(instance_id))
        self._clear_cache_if_needed(state)
        resolved_actor = (
            PlayerId(str(actor_player_id))
            if actor_player_id is not None
            else self.actorPlayerId
        )
        if self.cacheViews and actor_player_id is None and registry is None:
            cached = self._card_view_cache.get(iid)
            if cached is not None:
                return cached

        base = self._base_runtime_card(state, iid)
        effective_registry = registry if registry is not None else self._registry_for(state)
        deriver = self.deriveRuntimeCard or create_lorcana_runtime_card_deriver(effective_registry)
        derived = dict(
            deriver(
                state,
                base,
                self.resources,
                resolved_actor,
                self.runtimeCardCache,
            )
        )
        runtime_card = RuntimeCard(
            instanceId=base.instanceId,
            definitionId=base.definitionId,
            ownerID=base.ownerID,
            controllerID=base.controllerID,
            zoneID=base.zoneID,
            zoneIndex=base.zoneIndex,
            meta=base.meta,
            definition=base.definition,
            strength=int(derived.get("strength", 0) or 0),
            willpower=int(derived.get("willpower", 0) or 0),
            lore=int(derived.get("lore", 0) or 0),
            playCost=int(derived.get("playCost", 0) or 0),
            shiftInkCost=derived.get("shiftInkCost") if isinstance(derived.get("shiftInkCost"), int) else None,
            shiftPlayCost=derived.get("shiftPlayCost") if isinstance(derived.get("shiftPlayCost"), int) else None,
            moveCost=int(derived.get("moveCost", 0) or 0),
            damage=int(derived.get("damage", 0) or 0),
            exerted=bool(derived.get("exerted", False)),
            drying=bool(derived.get("drying", False)),
            canBePutInInkwell=bool(derived.get("canBePutInInkwell", False)),
            hasSupport=bool(derived.get("hasSupport", False)),
            hasRush=bool(derived.get("hasRush", False)),
            hasReckless=bool(derived.get("hasReckless", False)),
            hasEvasive=bool(derived.get("hasEvasive", False)),
            hasQuestRestriction=bool(derived.get("hasQuestRestriction", False)),
            fullName=str(derived.get("fullName", base.definition.full_name)),
            keywords=tuple(str(item) for item in derived.get("keywords", ()) or ()),
            keywordValues=dict(derived.get("keywordValues", {}) or {}),
            classifications=tuple(str(item) for item in derived.get("classifications", ()) or ()),
            temporaryAbilities=dict(derived.get("temporaryAbilities", {}) or {}),
            temporaryAbilityStarts=dict(derived.get("temporaryAbilityStarts", {}) or {}),
            temporaryRestrictions=dict(derived.get("temporaryRestrictions", {}) or {}),
            temporaryRestrictionStarts=dict(derived.get("temporaryRestrictionStarts", {}) or {}),
            grantedAbilityTextEntries=tuple(derived.get("grantedAbilityTextEntries", ()) or ()),
        )
        if self.cacheViews and actor_player_id is None and registry is None:
            self._card_view_cache[iid] = runtime_card
        return runtime_card

    def get(self, cardId: InstanceId | str) -> RuntimeCard | None:
        return self.runtime_card(self._state, cardId) if hasattr(self, "_state") else None

    def require_from_state(self, state: MatchState, card_id: InstanceId | str) -> RuntimeCard:
        return self.runtime_card(state, card_id)

    def getDefinition(self, state: MatchState, card_id: InstanceId | str) -> CardDefinition | None:
        try:
            record = self.resources.instances.require(InstanceId(str(card_id)))
        except KeyError:
            return None
        return self.resources.cards.get(str(record.definition_id))

    def getDefinitionById(self, definition_id: str) -> CardDefinition | None:
        try:
            return self.resources.cards.get(str(definition_id))
        except KeyError:
            return None

    def getMeta(self, state: MatchState, card_id: InstanceId | str) -> CardMeta | None:
        return state.ctx.zones.private.cardMeta.get(InstanceId(str(card_id)))

    def inZone(self, state: MatchState, zone_id: ZoneId | str) -> tuple[RuntimeCard, ...]:
        card_ids = state.ctx.zones.private.zoneCards.get(ZoneId(str(zone_id)), ())
        return tuple(self.runtime_card(state, card_id) for card_id in card_ids)

    def queryRuntime(
        self,
        state: MatchState,
        target_dsl: Mapping[str, object],
        projector: Callable[[RuntimeCard], Any] | None = None,
        *,
        actor_player_id: PlayerId | str | None = None,
        source_card_id: InstanceId | str | None = None,
    ) -> tuple[Any, ...]:
        actor = PlayerId(str(actor_player_id)) if actor_player_id is not None else self.actorPlayerId
        owner = target_dsl.get("owner") or "any"
        zones = self._collect_zone_ids(state, target_dsl.get("zones"))
        source_id = InstanceId(str(source_card_id or target_dsl.get("sourceCardId"))) if source_card_id or target_dsl.get("sourceCardId") else None
        exclude_self = target_dsl.get("excludeSelf") is True
        card_types_raw = target_dsl.get("cardTypes") or target_dsl.get("cardType") or ()
        if isinstance(card_types_raw, str):
            card_types = {card_types_raw}
        else:
            card_types = {str(item) for item in card_types_raw if isinstance(item, str)}

        seen: set[InstanceId] = set()
        cards: list[RuntimeCard] = []
        for zone_id in zones:
            for card_id in state.ctx.zones.private.zoneCards.get(zone_id, ()):
                if card_id in seen:
                    continue
                if exclude_self and source_id is not None and card_id == source_id:
                    continue
                runtime_card = self.runtime_card(state, card_id, actor_player_id=actor)
                if owner == "you" and (actor is None or runtime_card.ownerID != actor):
                    continue
                if owner == "opponent" and actor is not None and runtime_card.ownerID == actor:
                    continue
                if card_types and runtime_card.definition.card_type not in card_types and "card" not in card_types:
                    continue
                seen.add(card_id)
                cards.append(runtime_card)

        if projector is not None:
            return tuple(projector(card) for card in cards)
        return tuple(cards)

    queryTargetDsl = queryRuntime

    def _collect_zone_ids(self, state: MatchState, requested_zones: object) -> tuple[ZoneId, ...]:
        zone_ids = tuple(state.ctx.zones.private.zoneCards)
        if not requested_zones:
            return zone_ids
        raw_zones = (requested_zones,) if isinstance(requested_zones, str) else tuple(requested_zones)
        selected: list[ZoneId] = []
        seen: set[ZoneId] = set()
        for raw_zone in raw_zones:
            zone = str(raw_zone)
            candidates = [ZoneId(zone)] if ":" in zone else [ZoneId(zone)] + [
                zone_id for zone_id in zone_ids if str(zone_id).startswith(f"{zone}:")
            ]
            for candidate in candidates:
                if candidate in state.ctx.zones.private.zoneCards and candidate not in seen:
                    seen.add(candidate)
                    selected.append(candidate)
        return tuple(selected)

    def runtime_card(
        self,
        state: MatchState,
        instance_id: InstanceId | str,
        *,
        actor_player_id: PlayerId | str | None = None,
        registry: object | None = None,
    ) -> RuntimeCard:
        return self._build_card_view(
            state,
            instance_id,
            actor_player_id=actor_player_id,
            registry=registry,
        )

    def card(self, state: MatchState, instance_id: InstanceId | str) -> CardDefinition:
        return self._base_runtime_card(state, instance_id).definition

    def get_meta(self, state: MatchState, instance_id: InstanceId | str) -> CardMeta:
        return state.ctx.zones.private.cardMeta.get(InstanceId(str(instance_id)), CardMeta())

    def owner(self, state: MatchState, instance_id: InstanceId | str) -> PlayerId:
        return self._base_runtime_card(state, instance_id).ownerID

    def controller(self, state: MatchState, instance_id: InstanceId | str) -> PlayerId:
        return self._base_runtime_card(state, instance_id).controllerID

    def zone(self, state: MatchState, instance_id: InstanceId | str) -> ZoneId | None:
        return self._base_runtime_card(state, instance_id).zoneID

    def in_zone(self, state: MatchState, zone_key: ZoneId | str) -> tuple[RuntimeCard, ...]:
        return self.inZone(state, zone_key)

    def public_in_play_ids(self, state: MatchState) -> tuple[InstanceId, ...]:
        ids: list[InstanceId] = []
        for zone_key, card_ids in state.ctx.zones.private.zoneCards.items():
            if base_zone_from_key(zone_key) != ZoneId("play"):
                continue
            for card_id in card_ids:
                meta = state.ctx.zones.private.cardMeta.get(card_id, CardMeta())
                if meta.stackParentId is None:
                    ids.append(card_id)
        return tuple(ids)

    def controlled_public_in_play_ids(self, state: MatchState, player: PlayerId | str) -> tuple[InstanceId, ...]:
        pid = PlayerId(str(player))
        return tuple(card_id for card_id in self.public_in_play_ids(state) if self.controller(state, card_id) == pid)

    def characters_in_play(self, state: MatchState, player: PlayerId | str | None = None) -> tuple[InstanceId, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            pid = PlayerId(str(player))
            ids = tuple(card_id for card_id in ids if self.controller(state, card_id) == pid)
        return tuple(card_id for card_id in ids if self.card(state, card_id).card_type == "character")

    def items_in_play(self, state: MatchState, player: PlayerId | str | None = None) -> tuple[InstanceId, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            pid = PlayerId(str(player))
            ids = tuple(card_id for card_id in ids if self.controller(state, card_id) == pid)
        return tuple(card_id for card_id in ids if self.card(state, card_id).card_type == "item")

    def locations_in_play(self, state: MatchState, player: PlayerId | str | None = None) -> tuple[InstanceId, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            pid = PlayerId(str(player))
            ids = tuple(card_id for card_id in ids if self.controller(state, card_id) == pid)
        return tuple(card_id for card_id in ids if self.card(state, card_id).card_type == "location")

    def has_classification(self, state: MatchState, instance_id: InstanceId | str, classification: str) -> bool:
        runtime_card = self.runtime_card(state, instance_id)
        return any(item.lower() == classification.lower() for item in runtime_card.classifications)


__all__ = [
    "QueryService",
    "RuntimeCard",
    "RuntimeCardBase",
    "RuntimeCardDeriver",
    "create_lorcana_runtime_card_deriver",
]

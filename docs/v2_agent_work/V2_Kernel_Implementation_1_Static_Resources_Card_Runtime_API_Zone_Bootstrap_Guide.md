# LorcanaChamp v2 Kernel Development Phase 1 Guide

## Phase name

`V2 Kernel Implementation 1: Static Resources, Card Runtime API, and Zone Bootstrap`

## Decision

The first v2 implementation should not implement gameplay actions, effects, or unsupported report movement. The first implementation should align the v2 kernel with Lorcanito's fundamental engine model:

```text
immutable card definitions
+ immutable per-match card instance registry
+ mutable serializable zone/card-meta state
+ runtime card query API that combines those layers
```

This is a larger refactor than preserving the scaffold's current `MatchState.cards[instance_id].card_id` shape. The larger refactor is required because the current scaffold shape would push future targeting/static/effect code toward direct mutable card-state access, which is not Lorcanito-aligned.

---

## 1. Lorcanito source findings

### Files inspected

```text
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/index.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/sync.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/catalog-data.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-cards/src/utils/fromDeckToCardInstances.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/static-resources.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/card-runtime.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.init.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.queries.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/zones/runtime-zone-config.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-game/definition.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/runtime-card-derived.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/engine-initialization.ts
```

### Confirmed Lorcanito behavior

Lorcanito card definitions are stored as typed/generated card objects under `lorcana-cards/src/cards/<set>/...`, then aggregated into `allCards` and `allCardsById` in `catalog-data.ts`. `cards/index.ts` and `cards/sync.ts` expose `getLorcanaCardCatalog()` / `getLorcanaCardCatalogSync()` by wrapping `allCardsById` in `createRecordCardCatalog("lorcana:cards", allCardsById)`.

Decks are converted to per-match runtime cards by `fromDeckToCardInstances.ts`, which creates:

```text
cardInstances: instanceId -> cardDefinitionId
owners: ownerId -> instanceIds
```

`static-resources.ts` then builds `MatchStaticResources` from those maps:

```text
MatchStaticResources.cards      -> immutable CardCatalog
MatchStaticResources.instances  -> immutable CardInstanceRegistry
MatchStaticResources.zoneDefinitions -> immutable zone config
```

Lorcanito validates static resources before runtime use:

```text
- cards catalog ref must exist
- card instance registry ref must exist
- every instance record must have instanceId and definitionId
- every instance definitionId must exist in the card catalog
- duplicate owner assignment is invalid
- missing owner assignment is invalid
```

`card-runtime.ts` exposes the runtime card access pattern. A runtime card view is built by resolving:

```text
instanceId
  -> staticResources.instances.get(instanceId)
  -> definitionId
  -> staticResources.cards.get(definitionId)
  -> ctx.zones.private.cardIndex[instanceId]
  -> ctx.zones.private.cardMeta[instanceId]
  -> derived runtime card view
```

`runtime-zone-config.ts` defines Lorcana zones as first-class runtime resources: `deck`, `hand`, `play`, `discard`, `inkwell`, `limbo`; all are owner-scoped and have visibility/order/facedown metadata.

`runtime-game/definition.ts` board setup initializes owner-scoped deck zones from `staticResources.instances.entries()`. It places every player's owned instance IDs in that player's `deck:<player>` zone and creates card index entries with owner/controller/zone/index.

### Exact Lorcanito model to match in Python

```text
CardCatalog: immutable cardId -> card definition
CardInstanceRegistry: immutable instanceId -> definitionId + ownerId
MatchStaticResources: card catalog + instance registry + zone definitions
MatchState.framework.zones.zoneCards: mutable zone -> ordered instanceIds
MatchState.framework.zones.cardIndex: mutable instanceId -> zone/controller/owner/index
MatchState.framework.zones.cardMeta: mutable instanceId -> damage/exertion/location/cards-under/etc.
CardQueryAPI: combines all of the above to produce runtime card views
```

---

## 2. Current LorcanaChamp v2 scaffold findings

### Files inspected

```text
lorcana_engine_v2/cards/catalog.py
lorcana_engine_v2/cards/models.py
lorcana_engine_v2/core/ids.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/core/context.py
lorcana_engine_v2/core/runtime.py
lorcana_engine_v2/rules/queries.py
lorcana_engine_v2/rules/target_resolver.py
lorcana_engine_v2/rules/amount_resolver.py
lorcana_engine_v2/rules/condition_evaluator.py
lorcana_engine_v2/rules/derived_state.py
lorcana_engine_v2/registries/static_registry.py
tests/v2/test_card_catalog_loads_real_lorcanito_data.py
tests/v2/test_static_registry_v2.py
tests/v2/test_target_resolver_v2.py
tests/v2/test_amount_resolver_v2.py
tests/v2/test_first_real_card_parity_v2.py
```

### Current scaffold behavior

The current scaffold has a useful v2 package boundary and real-card tests. However, it still stores card definition identity directly in mutable `MatchState.cards[instance_id].card_id`. Query, targeting, amount, derived state, and static registry services read card identity directly from `state.cards`.

That shape conflicts with Lorcanito's runtime model. Lorcanito stores definition identity in `MatchStaticResources.instances`, not mutable match state.

### Exact mismatch

Current scaffold:

```text
MatchState.cards[instanceId] -> CardInstance(card_id, owner, controller, zone, damage, exerted)
```

Lorcanito:

```text
MatchStaticResources.instances[instanceId] -> definitionId + ownerId
MatchState.ctx.zones.cardIndex[instanceId] -> zone/controller/index
MatchState.ctx.zones.cardMeta[instanceId] -> damage/exertion/location/cards-under
```

### Required larger refactor

The correct answer is a larger v2 foundation refactor. Do not preserve the current scaffold's `CardInstance` state shape, because preserving it would fight Lorcanito parity and cause future systems to keep reading card definitions from mutable state.

---

## 3. Required implementation actions

### Files to add

```text
lorcana_engine_v2/core/static_resources.py
lorcana_engine_v2/core/zones.py
lorcana_engine_v2/core/bootstrap.py
tests/v2/__init__.py
tests/v2/helpers.py
tests/v2/test_static_resources_v2.py
tests/v2/test_zone_bootstrap_v2.py
tests/v2/test_card_runtime_query_api_v2.py
```

### Files to replace

```text
lorcana_engine_v2/__init__.py
lorcana_engine_v2/cards/__init__.py
lorcana_engine_v2/cards/models.py
lorcana_engine_v2/cards/catalog.py
lorcana_engine_v2/core/__init__.py
lorcana_engine_v2/core/ids.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/core/context.py
lorcana_engine_v2/core/runtime.py
lorcana_engine_v2/rules/queries.py
lorcana_engine_v2/rules/target_resolver.py
lorcana_engine_v2/rules/amount_resolver.py
lorcana_engine_v2/rules/condition_evaluator.py
lorcana_engine_v2/rules/derived_state.py
lorcana_engine_v2/registries/static_registry.py
lorcana_engine_v2/registries/__init__.py
tests/v2/test_card_catalog_loads_real_lorcanito_data.py
tests/v2/test_amount_resolver_v2.py
tests/v2/test_static_registry_v2.py
tests/v2/test_target_resolver_v2.py
tests/v2/test_first_real_card_parity_v2.py
```

---

## 4. Full copy-paste implementation code

### `lorcana_engine_v2/core/ids.py`

```python
from __future__ import annotations

from typing import NewType

CardId = NewType("CardId", str)
InstanceId = NewType("InstanceId", str)
PlayerId = NewType("PlayerId", str)
ZoneId = NewType("ZoneId", str)

```

### `lorcana_engine_v2/cards/models.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SourceEffect:
    """Preserved Lorcanito source effect shape.

    v2 intentionally keeps the raw Lorcanito-derived object available.  Runtime
    support will be added by mapping these source shapes into typed executable
    specs, not by mutating the card definition or losing source fidelity.
    """
    kind: str
    raw: dict[str, Any]

    @property
    def target(self) -> Any:
        return self.raw.get("target")

    @property
    def amount(self) -> Any:
        if "amount" in self.raw:
            return self.raw["amount"]
        if "modifier" in self.raw:
            return self.raw["modifier"]
        if "reduction" in self.raw:
            return self.raw["reduction"]
        return None


@dataclass(frozen=True, slots=True)
class SourceAbility:
    """Preserved Lorcanito source ability shape."""
    kind: str
    raw: dict[str, Any]
    id: str | None = None
    name: str | None = None
    text: str | None = None
    source_zones: tuple[str, ...] = ()
    effects: tuple[SourceEffect, ...] = ()


@dataclass(frozen=True, slots=True)
class CardDefinition:
    """Immutable card definition loaded from Lorcanito-derived card data.

    This is v2's equivalent of Lorcanito's BaseCardDefinition / typed card
    object.  It must remain immutable and must not contain per-match mutable
    state such as zone, damage, exertion, controller, or cards-under data.
    """
    id: str
    name: str
    version: str | None
    full_name: str
    card_type: str
    cost: int
    inkable: bool
    canonical_id: str | None = None
    reprints: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    strength: int = 0
    willpower: int = 0
    lore: int = 0
    move_cost: int | None = None
    abilities: tuple[SourceAbility, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    def static_abilities(self) -> tuple[SourceAbility, ...]:
        return tuple(ability for ability in self.abilities if ability.kind == "static")

```

### `lorcana_engine_v2/cards/catalog.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Iterable, Mapping

from .models import CardDefinition, SourceAbility, SourceEffect


@dataclass(frozen=True, slots=True)
class CardCatalog:
    """Immutable card catalog, equivalent to Lorcanito's CardCatalog.

    The catalog stores static card definitions only.  Runtime instance identity
    lives in MatchStaticResources.instances, not inside MatchState.
    """
    cards: Mapping[str, CardDefinition]
    ref: str = "lorcana:cards"

    def get(self, card_id: str) -> CardDefinition:
        try:
            return self.cards[card_id]
        except KeyError as exc:
            raise KeyError(f"Unknown card id: {card_id}") from exc

    def has(self, card_id: str) -> bool:
        return card_id in self.cards

    def all_cards(self) -> tuple[CardDefinition, ...]:
        return tuple(self.cards.values())

    @classmethod
    def from_lorcanito_normalized_json(
        cls,
        path: str | Path,
        *,
        ref: str = "lorcana:cards",
    ) -> "CardCatalog":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("cards", payload if isinstance(payload, list) else [])
        cards: dict[str, CardDefinition] = {}
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            card = _parse_card(record)
            cards[card.id] = card
        return cls(cards=cards, ref=ref)


def _parse_card(raw: dict[str, Any]) -> CardDefinition:
    abilities = tuple(_parse_ability(item) for item in raw.get("abilities", ()) if isinstance(item, dict))
    name = str(raw.get("name") or "")
    version = raw.get("version")
    full_name = str(raw.get("fullName") or raw.get("full_name") or (f"{name} - {version}" if version else name))
    colors = raw.get("inkType") or raw.get("colors") or raw.get("ink") or ()
    if isinstance(colors, str):
        colors = (colors,)
    reprints = raw.get("reprints") or ()
    if isinstance(reprints, str):
        reprints = (reprints,)
    return CardDefinition(
        id=str(raw["id"]),
        canonical_id=str(raw.get("canonicalId") or raw.get("canonical_id")) if raw.get("canonicalId") or raw.get("canonical_id") else None,
        reprints=tuple(str(item) for item in reprints),
        name=name,
        version=str(version) if version is not None else None,
        full_name=full_name,
        card_type=str(raw.get("cardType") or raw.get("card_type") or "card"),
        cost=int(raw.get("cost") or 0),
        inkable=bool(raw.get("inkable", False)),
        colors=tuple(str(item).lower() for item in colors),
        classifications=tuple(str(item) for item in raw.get("classifications", ()) or ()),
        strength=int(raw.get("strength") or 0),
        willpower=int(raw.get("willpower") or 0),
        lore=int(raw.get("lore") or 0),
        move_cost=int(raw["moveCost"]) if raw.get("moveCost") is not None else None,
        abilities=abilities,
        raw=dict(raw),
    )


def _parse_ability(raw: dict[str, Any]) -> SourceAbility:
    source_zones = raw.get("sourceZones") or raw.get("source_zones") or ()
    if isinstance(source_zones, str):
        source_zones = (source_zones,)
    effects = tuple(_parse_effects(raw.get("effect")))
    return SourceAbility(
        kind=str(raw.get("type") or raw.get("kind") or "unknown"),
        raw=dict(raw),
        id=str(raw.get("id")) if raw.get("id") is not None else None,
        name=str(raw.get("name")) if raw.get("name") is not None else None,
        text=str(raw.get("text")) if raw.get("text") is not None else None,
        source_zones=tuple(str(zone) for zone in source_zones),
        effects=effects,
    )


def _parse_effects(value: Any) -> Iterable[SourceEffect]:
    if isinstance(value, list):
        for item in value:
            yield from _parse_effects(item)
        return
    if isinstance(value, dict):
        kind = str(value.get("type") or value.get("kind") or "unknown")
        yield SourceEffect(kind=kind, raw=dict(value))

```

### `lorcana_engine_v2/cards/__init__.py`

```python
from .models import CardDefinition, SourceAbility, SourceEffect
from .catalog import CardCatalog

__all__ = ["CardDefinition", "SourceAbility", "SourceEffect", "CardCatalog"]

```

### `lorcana_engine_v2/core/static_resources.py`

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping

from lorcana_engine_v2.cards.catalog import CardCatalog

from .ids import CardId, InstanceId, PlayerId, ZoneId
from .zones import ZoneConfig


@dataclass(frozen=True, slots=True)
class CardsMaps:
    """Per-match immutable card instance input.

    Mirrors Lorcanito's CardsMaps:
      cardInstances: instanceId -> definitionId
      owners: ownerId -> instanceIds
    """
    card_instances: Mapping[InstanceId, CardId]
    owners: Mapping[PlayerId, tuple[InstanceId, ...]]

    @classmethod
    def from_raw(cls, raw: Mapping[str, object]) -> "CardsMaps":
        card_instances_raw = raw.get("cardInstances") or raw.get("card_instances") or {}
        owners_raw = raw.get("owners") or {}
        if not isinstance(card_instances_raw, Mapping):
            raise TypeError("CardsMaps.cardInstances must be a mapping")
        if not isinstance(owners_raw, Mapping):
            raise TypeError("CardsMaps.owners must be a mapping")
        card_instances = {
            InstanceId(str(instance_id)): CardId(str(definition_id))
            for instance_id, definition_id in card_instances_raw.items()
        }
        owners = {
            PlayerId(str(owner_id)): tuple(InstanceId(str(instance_id)) for instance_id in instance_ids)
            for owner_id, instance_ids in owners_raw.items()
            if isinstance(instance_ids, (list, tuple))
        }
        return cls(card_instances=card_instances, owners=owners)

    def to_raw(self) -> dict[str, object]:
        return {
            "cardInstances": {str(k): str(v) for k, v in self.card_instances.items()},
            "owners": {str(k): [str(v) for v in values] for k, values in self.owners.items()},
        }


@dataclass(frozen=True, slots=True)
class CardInstanceRecord:
    """Immutable runtime instance identity.

    Definition identity and owner are static for the match.  Zone, controller,
    damage, exertion, and other mutable state belong in MatchState zones/meta.
    """
    instance_id: InstanceId
    definition_id: CardId
    owner_id: PlayerId


@dataclass(frozen=True, slots=True)
class CardInstanceRegistry:
    ref: str
    records: Mapping[InstanceId, CardInstanceRecord]

    def get(self, instance_id: InstanceId | str) -> CardInstanceRecord | None:
        return self.records.get(InstanceId(str(instance_id)))

    def require(self, instance_id: InstanceId | str) -> CardInstanceRecord:
        record = self.get(instance_id)
        if record is None:
            raise KeyError(f"CARD_INSTANCE_NOT_REGISTERED: {instance_id}")
        return record

    def has(self, instance_id: InstanceId | str) -> bool:
        return InstanceId(str(instance_id)) in self.records

    def entries(self) -> tuple[CardInstanceRecord, ...]:
        return tuple(self.records.values())


@dataclass(frozen=True, slots=True)
class MatchStaticResources:
    """Immutable resources shared by all runtime queries for a match."""
    cards: CardCatalog
    instances: CardInstanceRegistry
    zone_definitions: Mapping[ZoneId, ZoneConfig]


@dataclass(frozen=True, slots=True)
class StaticResourceRefs:
    cards_catalog_ref: str
    card_instances_ref: str


def _hash_string(input_value: str) -> str:
    # FNV-1a 32-bit, matching Lorcanito's stable lightweight ref strategy.
    value = 2166136261
    for char in input_value:
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value:
        value, idx = divmod(value, 36)
        out = alphabet[idx] + out
    return out


def _cards_maps_ref(cards_maps: CardsMaps) -> str:
    signature = json.dumps(cards_maps.to_raw(), sort_keys=True, separators=(",", ":"))
    return f"cards-maps:{len(cards_maps.card_instances)}:{_hash_string(signature)}"


def build_records_from_cards_maps(cards_maps: CardsMaps) -> dict[InstanceId, CardInstanceRecord]:
    records: dict[InstanceId, CardInstanceRecord] = {}
    seen: set[InstanceId] = set()
    for owner_id, instance_ids in cards_maps.owners.items():
        for instance_id in instance_ids:
            if instance_id in seen:
                raise ValueError(
                    f"CARDS_MAPS_INVALID: duplicate instance '{instance_id}' assigned to multiple owners"
                )
            definition_id = cards_maps.card_instances.get(instance_id)
            if definition_id is None:
                raise ValueError(
                    f"CARDS_MAPS_INVALID: owner '{owner_id}' references unknown instance '{instance_id}'"
                )
            records[instance_id] = CardInstanceRecord(
                instance_id=instance_id,
                definition_id=definition_id,
                owner_id=owner_id,
            )
            seen.add(instance_id)
    for instance_id in cards_maps.card_instances:
        if instance_id not in seen:
            raise ValueError(f"CARDS_MAPS_INVALID: missing owner for instance '{instance_id}'")
    return records


def create_card_instance_registry_from_cards_maps(cards_maps: CardsMaps) -> CardInstanceRegistry:
    return CardInstanceRegistry(ref=_cards_maps_ref(cards_maps), records=build_records_from_cards_maps(cards_maps))


def create_match_static_resources_from_cards_maps(
    cards_maps: CardsMaps,
    card_catalog: CardCatalog,
    zone_definitions: Mapping[ZoneId, ZoneConfig],
) -> MatchStaticResources:
    resources = MatchStaticResources(
        cards=card_catalog,
        instances=create_card_instance_registry_from_cards_maps(cards_maps),
        zone_definitions=dict(zone_definitions),
    )
    validate_match_static_resources(resources)
    return resources


def create_cards_maps_from_static_resources(resources: MatchStaticResources) -> CardsMaps:
    card_instances: dict[InstanceId, CardId] = {}
    owners: dict[PlayerId, list[InstanceId]] = {}
    for record in resources.instances.entries():
        card_instances[record.instance_id] = record.definition_id
        owners.setdefault(record.owner_id, []).append(record.instance_id)
    return CardsMaps(
        card_instances=card_instances,
        owners={owner: tuple(ids) for owner, ids in owners.items()},
    )


def get_static_resource_refs(resources: MatchStaticResources) -> StaticResourceRefs:
    return StaticResourceRefs(
        cards_catalog_ref=resources.cards.ref,
        card_instances_ref=resources.instances.ref,
    )


def validate_match_static_resources(resources: MatchStaticResources) -> None:
    if not resources.cards.ref:
        raise ValueError("STATIC_RESOURCES_INVALID: cards catalog ref is required")
    if not resources.instances.ref:
        raise ValueError("STATIC_RESOURCES_INVALID: card instance registry ref is required")
    for record in resources.instances.entries():
        if not record.instance_id or not record.definition_id:
            raise ValueError("STATIC_RESOURCES_INVALID: invalid card instance record")
        if not resources.cards.has(str(record.definition_id)):
            raise ValueError(
                f"STATIC_RESOURCES_INVALID: missing card definition '{record.definition_id}' "
                f"for instance '{record.instance_id}'"
            )

```

### `lorcana_engine_v2/core/zones.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .ids import InstanceId, PlayerId, ZoneId


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    id: ZoneId
    name: str
    visibility: str
    ordered: bool
    owner_scoped: bool
    face_down: bool = False
    max_size: int | None = None


@dataclass(frozen=True, slots=True)
class PublicZoneSummary:
    revision: int = 0
    count: int = 0
    top_public_card_id: InstanceId | None = None


@dataclass(frozen=True, slots=True)
class ZoneCardIndexEntry:
    zone_key: ZoneId
    index: int | None
    owner_id: PlayerId
    controller_id: PlayerId


@dataclass(frozen=True, slots=True)
class CardMeta:
    damage: int = 0
    exerted: bool = False
    drying: bool = False
    location_instance_id: InstanceId | None = None
    stack_parent_id: InstanceId | None = None
    cards_under: tuple[InstanceId, ...] = ()
    flags: Mapping[str, object] = field(default_factory=dict)

    def with_updates(self, **updates: object) -> "CardMeta":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class ZoneRuntimeState:
    zone_cards: Mapping[ZoneId, tuple[InstanceId, ...]]
    card_index: Mapping[InstanceId, ZoneCardIndexEntry]
    card_meta: Mapping[InstanceId, CardMeta]
    zone_summaries: Mapping[ZoneId, PublicZoneSummary]


LORCANA_RUNTIME_ZONES: dict[ZoneId, ZoneConfig] = {
    ZoneId("deck"): ZoneConfig(ZoneId("deck"), "Deck", "secret", ordered=True, owner_scoped=True, face_down=True),
    ZoneId("hand"): ZoneConfig(ZoneId("hand"), "Hand", "private", ordered=False, owner_scoped=True),
    ZoneId("play"): ZoneConfig(ZoneId("play"), "Play", "public", ordered=False, owner_scoped=True),
    ZoneId("discard"): ZoneConfig(ZoneId("discard"), "Discard", "public", ordered=True, owner_scoped=True),
    ZoneId("inkwell"): ZoneConfig(ZoneId("inkwell"), "Inkwell", "public", ordered=False, owner_scoped=True, face_down=True),
    ZoneId("limbo"): ZoneConfig(ZoneId("limbo"), "Limbo", "public", ordered=True, owner_scoped=True),
}


def scoped_zone(base_zone: str | ZoneId, player_id: str | PlayerId) -> ZoneId:
    return ZoneId(f"{base_zone}:{player_id}")


def zone_owner_from_key(zone_key: str | ZoneId) -> PlayerId | None:
    parts = str(zone_key).split(":")
    if len(parts) <= 1:
        return None
    return PlayerId(parts[-1])


def base_zone_from_key(zone_key: str | ZoneId) -> ZoneId:
    return ZoneId(str(zone_key).split(":", 1)[0])


def build_zone_registry(
    zone_definitions: Mapping[ZoneId, ZoneConfig],
    player_ids: tuple[PlayerId, ...],
) -> dict[ZoneId, ZoneConfig]:
    registry: dict[ZoneId, ZoneConfig] = {}
    for zone_id, zone_def in zone_definitions.items():
        registry[zone_id] = zone_def
        if not zone_def.owner_scoped:
            continue
        for player_id in player_ids:
            key = scoped_zone(zone_id, player_id)
            registry[key] = replace(zone_def, id=key)
    return registry


def initialize_zone_state_from_registry(registry: Mapping[ZoneId, ZoneConfig]) -> ZoneRuntimeState:
    return ZoneRuntimeState(
        zone_cards={zone_id: () for zone_id in registry},
        card_index={},
        card_meta={},
        zone_summaries={zone_id: PublicZoneSummary() for zone_id in registry},
    )


def put_cards_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    card_ids: tuple[InstanceId, ...],
    owner_id: PlayerId,
    controller_id: PlayerId | None = None,
) -> ZoneRuntimeState:
    controller = controller_id if controller_id is not None else owner_id
    zone_cards = {key: tuple(value) for key, value in zone_state.zone_cards.items()}
    card_index = dict(zone_state.card_index)
    card_meta = dict(zone_state.card_meta)
    zone_summaries = dict(zone_state.zone_summaries)

    current = list(zone_cards.get(zone_key, ()))
    for card_id in card_ids:
        current.append(card_id)
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=len(current) - 1,
            owner_id=owner_id,
            controller_id=controller,
        )
        card_meta.setdefault(card_id, CardMeta())
    zone_cards[zone_key] = tuple(current)
    zone_summaries[zone_key] = PublicZoneSummary(revision=1, count=len(current))
    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
    )

```

### `lorcana_engine_v2/core/state.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .ids import PlayerId
from .zones import ZoneRuntimeState, build_zone_registry, initialize_zone_state_from_registry, LORCANA_RUNTIME_ZONES


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0

    def with_updates(self, **updates: Any) -> "PlayerState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class FrameworkState:
    """Serializable framework-owned match state.

    Mirrors Lorcanito's TCGCtx split at v2 scale: zones and runtime indexing live
    here, not in static card definitions.
    """
    player_ids: tuple[PlayerId, PlayerId]
    zones: ZoneRuntimeState
    state_id: int = 0
    active_player: PlayerId = PlayerId("p0")
    turn_number: int = 1
    phase: str = "main"
    seed: str = "v2-default-seed"
    winner: PlayerId | None = None

    def with_updates(self, **updates: Any) -> "FrameworkState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class GameState:
    """Game-owned serializable state.

    This intentionally stays small in Phase 1.  Future phases will add bag,
    pending effects, turn metrics, replacements, and floating triggers here.
    """
    players: Mapping[PlayerId, PlayerState]
    event_log: tuple[Any, ...] = ()
    turn_metrics: Mapping[str, Any] = field(default_factory=dict)

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.players[PlayerId(str(player))]

    def with_updates(self, **updates: Any) -> "GameState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class MatchState:
    """Authoritative v2 match state envelope.

    Static card identity is deliberately not stored here.  Resolve instance IDs
    through MatchStaticResources.instances, then CardCatalog.
    """
    framework: FrameworkState
    game: GameState

    def opponent(self, player: PlayerId | str) -> PlayerId:
        player_id = PlayerId(str(player))
        for candidate in self.framework.player_ids:
            if candidate != player_id:
                return candidate
        raise ValueError(f"Unknown player id: {player}")

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.game.player(player)

    @staticmethod
    def empty(player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1"))) -> "MatchState":
        registry = build_zone_registry(LORCANA_RUNTIME_ZONES, player_ids)
        zones = initialize_zone_state_from_registry(registry)
        return MatchState(
            framework=FrameworkState(player_ids=player_ids, zones=zones, active_player=player_ids[0]),
            game=GameState(players={player_id: PlayerState(player_id) for player_id in player_ids}),
        )

```

### `lorcana_engine_v2/core/bootstrap.py`

```python
from __future__ import annotations

from .ids import PlayerId
from .state import FrameworkState, GameState, MatchState, PlayerState
from .static_resources import MatchStaticResources
from .zones import build_zone_registry, initialize_zone_state_from_registry, put_cards_in_zone, scoped_zone


def initialize_match_state_from_static_resources(
    resources: MatchStaticResources,
    player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1")),
    *,
    seed: str = "v2-default-seed",
    active_player: PlayerId | None = None,
    shuffle: bool = False,
) -> MatchState:
    """Create an initial MatchState with each owner's instances in deck.

    Phase 1 intentionally keeps order deterministic by default.  Future runtime
    random APIs can supply Lorcanito-style seeded shuffling at game start.
    """
    registry = build_zone_registry(resources.zone_definitions, player_ids)
    zones = initialize_zone_state_from_registry(registry)

    records_by_owner = {player_id: [] for player_id in player_ids}
    for record in resources.instances.entries():
        owner_id = record.owner_id
        if owner_id not in records_by_owner:
            raise ValueError(f"CARDS_MAPS_INVALID: owner '{owner_id}' is not a match player")
        records_by_owner[owner_id].append(record.instance_id)

    for player_id in player_ids:
        instance_ids = tuple(records_by_owner[player_id])
        if shuffle:
            # Placeholder hook.  Do not silently randomize until v2 has a seeded
            # random API matching Lorcanito's runtime random service.
            raise NotImplementedError("v2 seeded shuffle is not implemented yet")
        zones = put_cards_in_zone(
            zones,
            zone_key=scoped_zone("deck", player_id),
            card_ids=instance_ids,
            owner_id=player_id,
            controller_id=player_id,
        )

    active = active_player if active_player is not None else player_ids[0]
    return MatchState(
        framework=FrameworkState(player_ids=player_ids, zones=zones, active_player=active, seed=seed),
        game=GameState(players={player_id: PlayerState(player_id) for player_id in player_ids}),
    )

```

### `lorcana_engine_v2/core/context.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorcana_engine_v2.core.static_resources import MatchStaticResources
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState


@dataclass(frozen=True, slots=True)
class RulesContext:
    """Shared rules context, backed by Lorcanito-style static resources."""
    resources: "MatchStaticResources"
    query: "QueryService"
    targets: "TargetResolver"
    conditions: "ConditionEvaluator"
    amounts: "AmountResolver"
    static: "StaticRegistry"
    derived: "DerivedState"

    @property
    def catalog(self):
        return self.resources.cards


def build_rules_context(resources: "MatchStaticResources") -> RulesContext:
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState

    query = QueryService(resources)
    targets = TargetResolver()
    conditions = ConditionEvaluator()
    amounts = AmountResolver()
    static = StaticRegistry()
    derived = DerivedState()
    return RulesContext(
        resources=resources,
        query=query,
        targets=targets,
        conditions=conditions,
        amounts=amounts,
        static=static,
        derived=derived,
    )

```

### `lorcana_engine_v2/core/runtime.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from .commands import Command
from .context import RulesContext, build_rules_context
from .results import TransitionResult
from .state import MatchState
from .static_resources import MatchStaticResources


@dataclass(slots=True)
class MatchRuntime:
    """Central deterministic runtime shell for v2.

    Runtime is created from immutable MatchStaticResources, not directly from a
    mutable card dictionary.  Future move modules will continue to receive a
    RulesContext rather than importing card catalogs or legacy v1 runtime code.
    """
    resources: MatchStaticResources

    def context(self) -> RulesContext:
        return build_rules_context(self.resources)

    def legal_moves(self, state: MatchState, player: str):
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        return AvailableMoveService().legal_moves(state, player, self.context())

    def apply(self, state: MatchState, command: Command) -> TransitionResult:
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        service = AvailableMoveService()
        return service.apply(state, command, self.context())

```

### `lorcana_engine_v2/core/__init__.py`

```python
from .ids import CardId, InstanceId, PlayerId, ZoneId
from .state import FrameworkState, GameState, MatchState, PlayerState
from .runtime import MatchRuntime
from .context import RulesContext, build_rules_context
from .commands import Command
from .results import TransitionResult
from .static_resources import (
    CardsMaps,
    CardInstanceRecord,
    CardInstanceRegistry,
    MatchStaticResources,
    create_match_static_resources_from_cards_maps,
)
from .zones import CardMeta, ZoneConfig, ZoneRuntimeState, LORCANA_RUNTIME_ZONES, scoped_zone

__all__ = [
    "CardId",
    "InstanceId",
    "PlayerId",
    "ZoneId",
    "FrameworkState",
    "GameState",
    "MatchState",
    "PlayerState",
    "MatchRuntime",
    "RulesContext",
    "build_rules_context",
    "Command",
    "TransitionResult",
    "CardsMaps",
    "CardInstanceRecord",
    "CardInstanceRegistry",
    "MatchStaticResources",
    "create_match_static_resources_from_cards_maps",
    "CardMeta",
    "ZoneConfig",
    "ZoneRuntimeState",
    "LORCANA_RUNTIME_ZONES",
    "scoped_zone",
]

```

### `lorcana_engine_v2/rules/queries.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.cards.models import CardDefinition
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.static_resources import MatchStaticResources
from lorcana_engine_v2.core.zones import CardMeta, base_zone_from_key


@dataclass(frozen=True, slots=True)
class RuntimeCard:
    instance_id: InstanceId
    definition_id: str
    owner_id: PlayerId
    controller_id: PlayerId
    zone_id: ZoneId | None
    zone_index: int | None
    meta: CardMeta
    definition: CardDefinition


@dataclass(frozen=True, slots=True)
class QueryService:
    resources: MatchStaticResources

    def card(self, state, instance_id: InstanceId | str) -> CardDefinition:
        return self.runtime_card(state, instance_id).definition

    def runtime_card(self, state, instance_id: InstanceId | str) -> RuntimeCard:
        iid = InstanceId(str(instance_id))
        record = self.resources.instances.require(iid)
        definition = self.resources.cards.get(str(record.definition_id))
        index = state.framework.zones.card_index.get(iid)
        meta = state.framework.zones.card_meta.get(iid, CardMeta())
        return RuntimeCard(
            instance_id=iid,
            definition_id=str(record.definition_id),
            owner_id=index.owner_id if index is not None else record.owner_id,
            controller_id=index.controller_id if index is not None else record.owner_id,
            zone_id=index.zone_key if index is not None else None,
            zone_index=index.index if index is not None else None,
            meta=meta,
            definition=definition,
        )

    def get_meta(self, state, instance_id: InstanceId | str) -> CardMeta:
        return self.runtime_card(state, instance_id).meta

    def owner(self, state, instance_id: InstanceId | str) -> PlayerId:
        return self.runtime_card(state, instance_id).owner_id

    def controller(self, state, instance_id: InstanceId | str) -> PlayerId:
        return self.runtime_card(state, instance_id).controller_id

    def zone(self, state, instance_id: InstanceId | str) -> ZoneId | None:
        return self.runtime_card(state, instance_id).zone_id

    def in_zone(self, state, zone_key: ZoneId | str) -> tuple[RuntimeCard, ...]:
        card_ids = state.framework.zones.zone_cards.get(ZoneId(str(zone_key)), ())
        return tuple(self.runtime_card(state, card_id) for card_id in card_ids)

    def public_in_play_ids(self, state) -> tuple[InstanceId, ...]:
        ids: list[InstanceId] = []
        for zone_key, card_ids in state.framework.zones.zone_cards.items():
            if base_zone_from_key(zone_key) != ZoneId("play"):
                continue
            for card_id in card_ids:
                meta = state.framework.zones.card_meta.get(card_id, CardMeta())
                if meta.stack_parent_id is None:
                    ids.append(card_id)
        return tuple(ids)

    def controlled_public_in_play_ids(self, state, player: PlayerId | str) -> tuple[InstanceId, ...]:
        pid = PlayerId(str(player))
        return tuple(card_id for card_id in self.public_in_play_ids(state) if self.controller(state, card_id) == pid)

    def characters_in_play(self, state, player: PlayerId | str | None = None) -> tuple[InstanceId, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            pid = PlayerId(str(player))
            ids = tuple(card_id for card_id in ids if self.controller(state, card_id) == pid)
        return tuple(card_id for card_id in ids if self.card(state, card_id).card_type == "character")

    def items_in_play(self, state, player: PlayerId | str | None = None) -> tuple[InstanceId, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            pid = PlayerId(str(player))
            ids = tuple(card_id for card_id in ids if self.controller(state, card_id) == pid)
        return tuple(card_id for card_id in ids if self.card(state, card_id).card_type == "item")

    def has_classification(self, state, instance_id: InstanceId | str, classification: str) -> bool:
        card = self.card(state, instance_id)
        return any(item.lower() == classification.lower() for item in card.classifications)

```

### `lorcana_engine_v2/rules/target_resolver.py`

```python
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

```

### `lorcana_engine_v2/rules/amount_resolver.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class AmountContext:
    actor: PlayerId | str
    source_id: InstanceId | str
    target_id: InstanceId | str | None = None

    @property
    def source_instance_id(self) -> InstanceId:
        return InstanceId(str(self.source_id))


class AmountResolver:
    def resolve(self, state, ctx, raw_amount: Any, context: AmountContext) -> int:
        if raw_amount is None:
            return 0
        if isinstance(raw_amount, bool):
            return int(raw_amount)
        if isinstance(raw_amount, int):
            return raw_amount
        if isinstance(raw_amount, str):
            return int(raw_amount) if raw_amount.lstrip("+-").isdigit() else 0
        if not isinstance(raw_amount, dict):
            return 0
        kind = raw_amount.get("type")
        if kind == "static":
            return int(raw_amount.get("amount") or raw_amount.get("value") or 0)
        if kind == "items-in-play":
            player = self._controller_from_raw(state, ctx, raw_amount, context)
            return len(ctx.query.items_in_play(state, player))
        if kind == "characters-in-play":
            player = self._controller_from_raw(state, ctx, raw_amount, context)
            return len(ctx.query.characters_in_play(state, player))
        if kind == "damage-on-self":
            return int(ctx.query.get_meta(state, context.source_instance_id).damage)
        if kind == "filtered-count":
            return self._filtered_count(state, ctx, raw_amount, context)
        return 0

    def _controller_from_raw(self, state, ctx, raw: dict[str, Any], context: AmountContext) -> PlayerId:
        source_controller = ctx.query.controller(state, context.source_instance_id)
        controller = raw.get("controller") or raw.get("owner")
        if controller == "opponent":
            return state.opponent(source_controller)
        return source_controller

    def _filtered_count(self, state, ctx, raw: dict[str, Any], context: AmountContext) -> int:
        from .target_resolver import TargetQueryContext
        target = {
            "selector": "all",
            "zones": raw.get("zones") or ("play",),
            "cardTypes": raw.get("cardType") or raw.get("cardTypes") or (),
            "owner": raw.get("owner"),
            "controller": raw.get("controller"),
            "filters": raw.get("filters") or raw.get("filter") or (),
            "excludeSelf": raw.get("excludeSelf") or raw.get("exclude_self"),
            "count": "all",
        }
        source_controller = ctx.query.controller(state, context.source_instance_id)
        q = TargetQueryContext(actor=source_controller, source_id=context.source_instance_id)
        count = len(ctx.targets.resolve(state, ctx, target, q))
        return count * int(raw.get("multiplier") or 1)

```

### `lorcana_engine_v2/rules/condition_evaluator.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class ConditionContext:
    actor: PlayerId | str
    source_id: InstanceId | str | None = None
    target_id: InstanceId | str | None = None
    event_payload: dict[str, Any] | None = None


class ConditionEvaluator:
    def evaluate(self, state, ctx, raw_condition: Any, context: ConditionContext) -> bool:
        if raw_condition is None:
            return True
        if not isinstance(raw_condition, dict):
            return False
        kind = raw_condition.get("type") or raw_condition.get("kind")
        if kind in {None, "always"}:
            return True
        if kind in {"no-damage", "has-no-damage"}:
            target = context.target_id if context.target_id is not None else context.source_id
            return target is not None and ctx.query.get_meta(state, InstanceId(str(target))).damage <= 0
        if kind == "not":
            return not self.evaluate(state, ctx, raw_condition.get("condition"), context)
        if kind == "and":
            return all(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        if kind == "or":
            return any(self.evaluate(state, ctx, item, context) for item in raw_condition.get("conditions", ()))
        return False

```

### `lorcana_engine_v2/rules/derived_state.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.enums import Stat
from lorcana_engine_v2.core.ids import InstanceId


@dataclass(frozen=True, slots=True)
class DerivedState:
    """Read-only derived rules queries built from static materialization."""

    def effective_strength(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.strength + self._stat_delta(state, ctx, iid, Stat.STRENGTH.value))

    def effective_willpower(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.willpower + self._stat_delta(state, ctx, iid, Stat.WILLPOWER.value))

    def effective_lore(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.lore + self._stat_delta(state, ctx, iid, Stat.LORE.value))

    def keywords(self, state, ctx, instance_id: InstanceId | str) -> frozenset[str]:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        base = set()
        for ability in card.abilities:
            if ability.kind == "keyword" and ability.raw.get("keyword"):
                base.add(str(ability.raw["keyword"]).upper().replace(" ", "_"))
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "gain-keyword" and iid in effect.target_ids:
                keyword = effect.payload.get("keyword")
                if keyword:
                    base.add(str(keyword).upper().replace(" ", "_"))
        return frozenset(base)

    def _stat_delta(self, state, ctx, instance_id: InstanceId, stat: str) -> int:
        total = 0
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "modify-stat" and effect.payload.get("stat") == stat and instance_id in effect.target_ids:
                total += int(effect.payload.get("amount", 0))
        return total

```

### `lorcana_engine_v2/registries/static_registry.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.rules.amount_resolver import AmountContext
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext


@dataclass(frozen=True, slots=True)
class MaterializedStaticEffect:
    source_id: InstanceId
    source_controller: PlayerId
    kind: str
    target_ids: tuple[InstanceId, ...]
    payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class StaticRegistry:
    """Materialize continuous effects from active public source cards.

    This mirrors Lorcanito's derived/static-read model: source cards are found
    via the runtime card query API, definitions come from static resources, and
    mutable zone/meta state is read from MatchState.
    """

    def materialize(self, state, ctx) -> tuple[MaterializedStaticEffect, ...]:
        effects: list[MaterializedStaticEffect] = []
        for source_id in ctx.query.public_in_play_ids(state):
            source_card = ctx.query.card(state, source_id)
            source_controller = ctx.query.controller(state, source_id)
            for ability in source_card.static_abilities():
                condition = ability.raw.get("condition")
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    condition,
                    ConditionContext(actor=str(source_controller), source_id=str(source_id), target_id=str(source_id)),
                ):
                    continue
                for effect in ability.effects:
                    materialized = self._materialize_effect(state, ctx, source_id, effect.raw)
                    effects.extend(materialized)
        return tuple(effects)

    def _materialize_effect(self, state, ctx, source_id: InstanceId, raw: dict[str, Any]) -> tuple[MaterializedStaticEffect, ...]:
        kind = raw.get("type")
        raw_target = raw.get("target") or "SELF"
        actor = ctx.query.controller(state, source_id)
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

```

### `lorcana_engine_v2/registries/__init__.py`

```python
from .static_registry import MaterializedStaticEffect, StaticRegistry

__all__ = ["MaterializedStaticEffect", "StaticRegistry"]

```

### `tests/v2/__init__.py`

```python

```

### `tests/v2/helpers.py`

```python
from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import CardsMaps, create_match_static_resources_from_cards_maps
from lorcana_engine_v2.core.zones import LORCANA_RUNTIME_ZONES, CardMeta, put_cards_in_zone, scoped_zone


def real_catalog() -> CardCatalog:
    return CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))


def resources_for(card_instances: dict[str, str], owners: dict[str, tuple[str, ...]] | None = None):
    if owners is None:
        owners = {"p0": tuple(card_instances)}
    cards_maps = CardsMaps(
        card_instances={InstanceId(iid): CardId(cid) for iid, cid in card_instances.items()},
        owners={PlayerId(pid): tuple(InstanceId(iid) for iid in ids) for pid, ids in owners.items()},
    )
    return create_match_static_resources_from_cards_maps(cards_maps, real_catalog(), LORCANA_RUNTIME_ZONES)


def state_with_play(resources, p0: tuple[str, ...] = (), p1: tuple[str, ...] = (), meta: dict[str, CardMeta] | None = None):
    state = initialize_match_state_from_static_resources(resources)
    zones = state.framework.zones
    zones = put_cards_in_zone(zones, zone_key=scoped_zone("play", "p0"), card_ids=tuple(InstanceId(i) for i in p0), owner_id=PlayerId("p0"), controller_id=PlayerId("p0"))
    zones = put_cards_in_zone(zones, zone_key=scoped_zone("play", "p1"), card_ids=tuple(InstanceId(i) for i in p1), owner_id=PlayerId("p1"), controller_id=PlayerId("p1"))
    if meta:
        card_meta = dict(zones.card_meta)
        for key, value in meta.items():
            card_meta[InstanceId(key)] = value
        zones = type(zones)(
            zone_cards=zones.zone_cards,
            card_index=zones.card_index,
            card_meta=card_meta,
            zone_summaries=zones.zone_summaries,
        )
    return type(state)(framework=state.framework.with_updates(zones=zones), game=state.game)


def context_for(resources):
    return build_rules_context(resources)

```

### `tests/v2/test_card_catalog_loads_real_lorcanito_data.py`

```python
from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog


def _source_json() -> Path:
    return Path("data/lorcanito_runtime_extracted/cards.normalized.json")


def test_v2_catalog_loads_real_lorcanito_data():
    catalog = CardCatalog.from_lorcanito_normalized_json(_source_json())
    assert len(catalog.cards) >= 2500
    assert catalog.ref == "lorcana:cards"
    chi_fu = catalog.get("XGm")
    assert chi_fu.full_name == "Chi-Fu - Imperial Advisor"
    assert any(ability.kind == "static" for ability in chi_fu.abilities)


def test_v2_catalog_has_lorcanito_catalog_semantics():
    catalog = CardCatalog.from_lorcanito_normalized_json(_source_json(), ref="test:cards")
    assert catalog.ref == "test:cards"
    assert catalog.has("Z2D") is True
    assert catalog.has("missing-card") is False

```

### `tests/v2/test_static_resources_v2.py`

```python
import pytest

from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.static_resources import (
    CardsMaps,
    create_cards_maps_from_static_resources,
    create_match_static_resources_from_cards_maps,
    get_static_resource_refs,
)
from lorcana_engine_v2.core.zones import LORCANA_RUNTIME_ZONES

from .helpers import real_catalog


def test_static_resources_build_instance_registry_from_cards_maps():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("a1"): CardId("XGm"), InstanceId("a2"): CardId("Z2D")},
        owners={PlayerId("p0"): (InstanceId("a1"),), PlayerId("p1"): (InstanceId("a2"),)},
    )
    resources = create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)

    assert resources.cards.get("XGm").full_name == "Chi-Fu - Imperial Advisor"
    assert resources.instances.require("a1").definition_id == "XGm"
    assert resources.instances.require("a1").owner_id == "p0"
    assert resources.instances.require("a2").owner_id == "p1"
    assert resources.instances.ref.startswith("cards-maps:2:")

    refs = get_static_resource_refs(resources)
    assert refs.cards_catalog_ref == "lorcana:cards"
    assert refs.card_instances_ref == resources.instances.ref


def test_static_resources_round_trip_to_cards_maps():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("c1"): CardId("XGm")},
        owners={PlayerId("p0"): (InstanceId("c1"),)},
    )
    resources = create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)
    round_tripped = create_cards_maps_from_static_resources(resources)
    assert round_tripped.to_raw() == cards_maps.to_raw()


def test_static_resources_reject_missing_card_definition():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("bad1"): CardId("missing")},
        owners={PlayerId("p0"): (InstanceId("bad1"),)},
    )
    with pytest.raises(ValueError, match="missing card definition"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)


def test_static_resources_reject_missing_owner_for_instance():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("bad1"): CardId("XGm")},
        owners={PlayerId("p0"): ()},
    )
    with pytest.raises(ValueError, match="missing owner"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)


def test_static_resources_reject_duplicate_owner_assignment():
    catalog = real_catalog()
    cards_maps = CardsMaps(
        card_instances={InstanceId("dup"): CardId("XGm")},
        owners={PlayerId("p0"): (InstanceId("dup"),), PlayerId("p1"): (InstanceId("dup"),)},
    )
    with pytest.raises(ValueError, match="duplicate instance"):
        create_match_static_resources_from_cards_maps(cards_maps, catalog, LORCANA_RUNTIME_ZONES)

```

### `tests/v2/test_zone_bootstrap_v2.py`

```python
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.zones import scoped_zone

from .helpers import resources_for


def test_zone_bootstrap_creates_owner_scoped_deck_zones_from_static_resources():
    resources = resources_for(
        {"p0a": "XGm", "p0b": "Z2D", "p1a": "HyV"},
        owners={"p0": ("p0a", "p0b"), "p1": ("p1a",)},
    )
    state = initialize_match_state_from_static_resources(resources)

    assert state.framework.player_ids == (PlayerId("p0"), PlayerId("p1"))
    assert state.framework.zones.zone_cards[scoped_zone("deck", "p0")] == ("p0a", "p0b")
    assert state.framework.zones.zone_cards[scoped_zone("deck", "p1")] == ("p1a",)

    p0a = state.framework.zones.card_index["p0a"]
    assert p0a.zone_key == scoped_zone("deck", "p0")
    assert p0a.index == 0
    assert p0a.owner_id == "p0"
    assert p0a.controller_id == "p0"

    assert state.framework.zones.zone_summaries[scoped_zone("deck", "p0")].count == 2
    assert state.framework.zones.zone_summaries[scoped_zone("deck", "p1")].count == 1


def test_zone_bootstrap_rejects_owner_not_in_match():
    resources = resources_for({"x1": "XGm"}, owners={"stranger": ("x1",)})
    try:
        initialize_match_state_from_static_resources(resources)
    except ValueError as exc:
        assert "not a match player" in str(exc)
    else:
        raise AssertionError("expected owner outside match to fail")

```

### `tests/v2/test_card_runtime_query_api_v2.py`

```python
from lorcana_engine_v2.core.zones import CardMeta, put_cards_in_zone, scoped_zone

from .helpers import context_for, resources_for
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId


def test_runtime_card_api_resolves_instance_to_definition_through_static_resources():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.instance_id == "c1"
    assert runtime_card.definition_id == "XGm"
    assert runtime_card.owner_id == "p0"
    assert runtime_card.controller_id == "p0"
    assert runtime_card.definition.full_name == "Chi-Fu - Imperial Advisor"
    assert runtime_card.zone_id == scoped_zone("deck", "p0")
    assert runtime_card.zone_index == 0


def test_runtime_card_api_reads_zone_and_meta_state_without_card_definition_in_state():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)
    zones = put_cards_in_zone(
        state.framework.zones,
        zone_key=scoped_zone("play", "p0"),
        card_ids=(InstanceId("c1"),),
        owner_id=PlayerId("p0"),
        controller_id=PlayerId("p0"),
    )
    meta = dict(zones.card_meta)
    meta[InstanceId("c1")] = CardMeta(damage=2, exerted=True)
    zones = type(zones)(
        zone_cards=zones.zone_cards,
        card_index=zones.card_index,
        card_meta=meta,
        zone_summaries=zones.zone_summaries,
    )
    state = type(state)(framework=state.framework.with_updates(zones=zones), game=state.game)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.zone_id == scoped_zone("play", "p0")
    assert runtime_card.meta.damage == 2
    assert runtime_card.meta.exerted is True
    assert ctx.query.public_in_play_ids(state) == ("c1",)
    assert ctx.query.characters_in_play(state, "p0") == ("c1",)

```

### `tests/v2/test_amount_resolver_v2.py`

```python
from lorcana_engine_v2.rules.amount_resolver import AmountContext

from .helpers import context_for, resources_for, state_with_play


def test_items_in_play_amount_provider_counts_real_items_through_query_api():
    resources = resources_for({"source": "Z2D", "item": "Bf0"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("source", "item"))

    assert resources.cards.get("Bf0").card_type == "item"
    assert ctx.amounts.resolve(
        state,
        ctx,
        {"type": "items-in-play", "controller": "you"},
        AmountContext(actor="p0", source_id="source"),
    ) == 1


def test_damage_on_self_amount_provider_reads_card_meta():
    from lorcana_engine_v2.core.zones import CardMeta

    resources = resources_for({"source": "2q9"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("source",), meta={"source": CardMeta(damage=3)})

    assert ctx.amounts.resolve(
        state,
        ctx,
        {"type": "damage-on-self"},
        AmountContext(actor="p0", source_id="source"),
    ) == 3

```

### `tests/v2/test_static_registry_v2.py`

```python
from .helpers import context_for, resources_for, state_with_play


def test_static_registry_materializes_real_chi_fu_static_using_static_resources():
    resources = resources_for({"chi": "XGm"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("chi",))

    effects = ctx.static.materialize(state, ctx)
    assert len(effects) == 1
    assert effects[0].kind == "modify-stat"
    assert effects[0].source_id == "chi"
    assert effects[0].source_controller == "p0"
    assert effects[0].target_ids == ("chi",)
    assert effects[0].payload == {"stat": "lore", "amount": 2}

```

### `tests/v2/test_target_resolver_v2.py`

```python
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext

from .helpers import context_for, resources_for, state_with_play


def test_your_hero_characters_alias_resolves_real_hero_card_through_runtime_query_api():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    result = ctx.targets.resolve(state, ctx, "YOUR_HERO_CHARACTERS", TargetQueryContext(actor="p0", source_id="ling"))
    assert result == ("hero",)

```

### `tests/v2/test_first_real_card_parity_v2.py`

```python
from lorcana_engine_v2.core.zones import CardMeta

from .helpers import context_for, resources_for, state_with_play


def test_chi_fu_real_static_lore_materializes_from_lorcanito_data():
    resources = resources_for({"chi": "XGm"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("chi",))

    assert resources.cards.get("XGm").full_name == "Chi-Fu - Imperial Advisor"
    assert ctx.derived.effective_lore(state, ctx, "chi") == 3


def test_mr_incredible_real_filtered_count_static_strength():
    resources = resources_for({"mr": "qoz", "ally": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("mr", "ally"))

    assert resources.cards.get("qoz").full_name == "Mr. Incredible - Super Strong"
    assert ctx.derived.effective_strength(state, ctx, "mr") == 8


def test_tamatoa_real_items_in_play_lore_amount_provider():
    resources = resources_for({"tamatoa": "Z2D", "item": "Bf0"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("tamatoa", "item"))

    assert resources.cards.get("Z2D").full_name == "Tamatoa - So Shiny!"
    assert resources.cards.get("Bf0").card_type == "item"
    assert ctx.derived.effective_lore(state, ctx, "tamatoa") == resources.cards.get("Z2D").lore + 1


def test_ling_real_classification_target_static_strength():
    resources = resources_for({"ling": "HyV", "hero": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("ling", "hero"))

    assert resources.cards.get("HyV").full_name == "Ling - Imperial Soldier"
    assert "Hero" in resources.cards.get("Y1z").classifications
    assert ctx.derived.effective_strength(state, ctx, "hero") == resources.cards.get("Y1z").strength + 1


def test_aurora_real_ward_grant_excludes_self():
    resources = resources_for({"aurora": "Au0", "ally": "Y1z"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("aurora", "ally"))

    assert resources.cards.get("Au0").full_name == "Aurora - Dreaming Guardian"
    assert "WARD" not in ctx.derived.keywords(state, ctx, "aurora")
    assert "WARD" in ctx.derived.keywords(state, ctx, "ally")


def test_donald_damage_on_self_static_lore_reads_card_meta():
    resources = resources_for({"donald": "2q9"})
    ctx = context_for(resources)
    state = state_with_play(resources, p0=("donald",), meta={"donald": CardMeta(damage=2)})

    assert resources.cards.get("2q9").full_name == "Donald Duck - Not Again!"
    assert ctx.derived.effective_lore(state, ctx, "donald") == resources.cards.get("2q9").lore + 2

```


---

## 5. Why each fix is required

### `InstanceId` and `PlayerId` become string IDs

Lorcanito runtime instance IDs and player IDs are strings. The scaffold used integer IDs for convenience, but keeping integer IDs would create friction in parity tests, zone keys, cardsMaps, and ML action serialization. This phase changes v2 to string IDs.

### `MatchStaticResources` is added

This is the central Lorcanito model: immutable card catalog + immutable card instance registry + zone definitions. Future v2 rules must resolve card definitions through this resource object.

### `MatchState.cards` is removed

Mutable match state should not own card definitions. Zone and meta state are mutable; definition identity is static. Removing `MatchState.cards` prevents future code from recreating v1's direct mutable-card shape.

### `ZoneRuntimeState` is added

Lorcanito's authoritative runtime state has zone cards, card index, and card meta. This phase adds the Python equivalent.

### `QueryService` becomes the only card runtime access point

Targeting, static materialization, amount resolution, and derived state now ask `ctx.query.runtime_card()` / `ctx.query.card()` instead of reading state directly. This matches Lorcanito's `CardQueryAPI`.

### Tests move to static resources

The real-card tests now prove that cards resolve through `MatchStaticResources.instances`, not mutable card instances. That is the parity point of this phase.

---

## 6. How the fix matches Lorcanito

| Lorcanito | LorcanaChamp v2 after this phase |
|---|---|
| `CardCatalog` | `CardCatalog(ref, cards)` |
| `CardsMaps.cardInstances` | `CardsMaps.card_instances` |
| `CardsMaps.owners` | `CardsMaps.owners` |
| `CardInstanceRecord` | `CardInstanceRecord` |
| `CardInstanceRegistry` | `CardInstanceRegistry` |
| `MatchStaticResources` | `MatchStaticResources` |
| `lorcanaRuntimeZones` | `LORCANA_RUNTIME_ZONES` |
| `buildZoneRegistry` | `build_zone_registry` |
| `initializeZoneStateFromRegistry` | `initialize_zone_state_from_registry` |
| `boardSetup` putting owned instances into deck zones | `initialize_match_state_from_static_resources()` |
| `CardQueryAPI.get/require/getDefinition/inZone` | `QueryService.runtime_card/card/in_zone` |

---

## 7. Tests

### Exact commands

Run only v2 tests:

```bash
python3 -m pytest tests/v2 -q
```

Expected result after applying this phase:

```text
23 passed
```

Compile the changed v2 files:

```bash
python3 -m py_compile \
  lorcana_engine_v2/core/ids.py \
  lorcana_engine_v2/cards/models.py \
  lorcana_engine_v2/cards/catalog.py \
  lorcana_engine_v2/core/static_resources.py \
  lorcana_engine_v2/core/zones.py \
  lorcana_engine_v2/core/state.py \
  lorcana_engine_v2/core/bootstrap.py \
  lorcana_engine_v2/core/context.py \
  lorcana_engine_v2/core/runtime.py \
  lorcana_engine_v2/rules/queries.py \
  lorcana_engine_v2/rules/target_resolver.py \
  lorcana_engine_v2/rules/amount_resolver.py \
  lorcana_engine_v2/rules/condition_evaluator.py \
  lorcana_engine_v2/rules/derived_state.py \
  lorcana_engine_v2/registries/static_registry.py
```

Expected: no output / successful exit.

Run full suite after v2 tests pass:

```bash
python3 -m pytest -q
```

Expected: current full suite remains passing.

---

## 8. Unsupported report integration rules

This phase must not claim unsupported report movement.

Reason: this phase changes v2 runtime substrate only. It does not connect v2 runtime support to the current unsupported report generator.

Rules going forward:

```text
1. Do not mark source card shapes executable because v2 has a scaffold class.
2. Only move unsupported records when v2 runtime services can execute or derive the behavior end to end.
3. Report integration must query v2's actual support surface, not v1 helper state.
4. No v2 report movement should happen until a report adapter validates runtime support through real services and real-card tests.
```

Expected unsupported report movement for this phase:

```text
none
```

---

## 9. Parity proof

### Proof A — static resources

Lorcanito `static-resources.ts` builds `MatchStaticResources` from `CardsMaps`, validates missing definitions, duplicate owners, and missing owners.

LorcanaChamp v2 now has `CardsMaps`, `CardInstanceRecord`, `CardInstanceRegistry`, `MatchStaticResources`, `create_match_static_resources_from_cards_maps()`, and `validate_match_static_resources()`.

Tests proving this:

```text
tests/v2/test_static_resources_v2.py
```

### Proof B — zone bootstrap

Lorcanito `runtime-game/definition.ts` boardSetup places each owner's instance IDs into that player's owner-scoped deck zone and creates card index entries.

LorcanaChamp v2 now has `initialize_match_state_from_static_resources()` that creates `deck:p0` / `deck:p1` zone entries and card indexes from static resources.

Tests proving this:

```text
tests/v2/test_zone_bootstrap_v2.py
```

### Proof C — runtime card query API

Lorcanito `card-runtime.ts` resolves runtime card views from static resources + zone index + card meta + derived data.

LorcanaChamp v2 now has `QueryService.runtime_card()` resolving from `MatchStaticResources.instances` + `CardCatalog` + `ZoneRuntimeState`.

Tests proving this:

```text
tests/v2/test_card_runtime_query_api_v2.py
```

### Proof D — real-card static parity still works

The earlier v2 real-card static tests now run through static resources and runtime card query API instead of the old scaffold `MatchState.cards` map.

Tests proving this:

```text
tests/v2/test_first_real_card_parity_v2.py
tests/v2/test_static_registry_v2.py
tests/v2/test_amount_resolver_v2.py
tests/v2/test_target_resolver_v2.py
```

---

## 10. Relevant edge cases and risks

### Risk: Existing scaffold tests imported `CardInstance`

This phase removes that concept from v2 public state. Tests must be updated. Keeping `CardInstance` would preserve the wrong model.

### Risk: `InstanceId` changes from int to string

This is intentional and Lorcanito-aligned. It may require updating any local v2 experiments that used integer instance IDs.

### Risk: deck order is deterministic, not shuffled

Lorcanito shuffles deck setup through its random API during board setup. This phase intentionally does not implement seeded random. Deterministic deck ordering is acceptable for static resource tests. The bootstrap function has a `shuffle` parameter that raises `NotImplementedError` until a Lorcanito-aligned random service exists.

### Risk: v2 still does not implement gameplay

Correct. This phase is the engine substrate. Gameplay actions should be implemented only after static resources and card query APIs are stable.

### Risk: no unsupported report movement

Correct. This phase creates runtime architecture, not report support. Report movement must wait for v2 report integration backed by runtime behavior.

---

## 11. Next migration gate after this phase

After this phase passes, the next v2 phase should be:

```text
V2 Kernel Implementation 2: Runtime Card Derivation Cache + Derived State Projection
```

That phase should add a Lorcanito-style derived runtime card view with state-version-aware caching before implementing legal moves.

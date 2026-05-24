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
        owners: dict[PlayerId, tuple[InstanceId, ...]] = {}
        for owner_id, instance_ids in owners_raw.items():
            if not isinstance(instance_ids, (list, tuple)):
                raise TypeError("CardsMaps.owners values must be lists of instance IDs")
            owners[PlayerId(str(owner_id))] = tuple(InstanceId(str(instance_id)) for instance_id in instance_ids)
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
    # Lorcanito hashes sorted entries, not the raw object shape.  Keep this
    # byte-for-byte aligned with createCardsMapsRef in static-resources.ts.
    signature = json.dumps(
        {
            "cardInstances": sorted(
                (str(instance_id), str(definition_id))
                for instance_id, definition_id in cards_maps.card_instances.items()
            ),
            "owners": [
                (str(owner_id), [str(instance_id) for instance_id in instance_ids])
                for owner_id, instance_ids in sorted(cards_maps.owners.items(), key=lambda item: str(item[0]))
            ],
        },
        separators=(",", ":"),
    )
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

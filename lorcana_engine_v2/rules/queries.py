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

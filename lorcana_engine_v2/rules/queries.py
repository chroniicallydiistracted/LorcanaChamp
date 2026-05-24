from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.cards.catalog import CardCatalog
from lorcana_engine_v2.core.state import MatchState, CardInstance


@dataclass(frozen=True, slots=True)
class QueryService:
    catalog: CardCatalog

    def card(self, state: MatchState, instance_id: int):
        return self.catalog.get(str(state.cards[instance_id].card_id))

    def public_in_play_ids(self, state: MatchState) -> tuple[int, ...]:
        return tuple(
            int(cid)
            for cid, inst in state.cards.items()
            if inst.zone == "play" and inst.stack_parent_id is None
        )

    def controlled_public_in_play_ids(self, state: MatchState, player: int) -> tuple[int, ...]:
        return tuple(cid for cid in self.public_in_play_ids(state) if int(state.cards[cid].controller) == int(player))

    def characters_in_play(self, state: MatchState, player: int | None = None) -> tuple[int, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            ids = tuple(cid for cid in ids if int(state.cards[cid].controller) == int(player))
        return tuple(cid for cid in ids if self.card(state, cid).card_type == "character")

    def items_in_play(self, state: MatchState, player: int | None = None) -> tuple[int, ...]:
        ids = self.public_in_play_ids(state)
        if player is not None:
            ids = tuple(cid for cid in ids if int(state.cards[cid].controller) == int(player))
        return tuple(cid for cid in ids if self.card(state, cid).card_type == "item")

    def has_classification(self, state: MatchState, instance_id: int, classification: str) -> bool:
        card = self.card(state, instance_id)
        return any(item.lower() == classification.lower() for item in card.classifications)

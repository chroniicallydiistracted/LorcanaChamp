from __future__ import annotations

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.zones import CardMeta
from lorcana_engine_v2.effects.temporary_effects import (
    has_temporary_player_restriction,
    has_temporary_restriction,
)


class RestrictionRegistry:
    def has_card_restriction(
        self,
        meta: CardMeta | None,
        *,
        current_turn: int,
        restriction: str,
    ) -> bool:
        return has_temporary_restriction(meta, current_turn, restriction)

    def has_player_restriction(
        self,
        state,
        player_id: PlayerId | str,
        *,
        current_turn: int,
        restriction: str,
    ) -> bool:
        return has_temporary_player_restriction(
            state.G.temporaryPlayerRestrictions,
            player_id,
            current_turn,
            restriction,
        )


__all__ = ["RestrictionRegistry"]

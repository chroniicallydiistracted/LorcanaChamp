from __future__ import annotations

from lorcana_engine_v2.moves.play import PLAY_CARD, PlayCardMove
from lorcana_engine_v2.rules.play_card_rules import (
    get_sing_together_threshold,
    get_singer_threshold,
    get_singer_threshold_for_instance,
    is_song_card,
)


class Move(PlayCardMove):
    """Temporary module-level alias for song costs through Lorcanito `playCard`."""


__all__ = [
    "PLAY_CARD",
    "Move",
    "PlayCardMove",
    "get_sing_together_threshold",
    "get_singer_threshold",
    "get_singer_threshold_for_instance",
    "is_song_card",
]

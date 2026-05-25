from __future__ import annotations

from lorcana_engine_v2.moves.play import PLAY_CARD, PlayCardMove
from lorcana_engine_v2.moves.shared.execute_shift_play import attach_shift_stack, execute_shift_play
from lorcana_engine_v2.rules.play_card_rules import get_shift_rules, resolve_shift_target_candidates


class Move(PlayCardMove):
    """Temporary module-level alias for Shift cost play through Lorcanito `playCard`."""


__all__ = [
    "PLAY_CARD",
    "Move",
    "PlayCardMove",
    "attach_shift_stack",
    "execute_shift_play",
    "get_shift_rules",
    "resolve_shift_target_candidates",
]

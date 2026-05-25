from __future__ import annotations

from .state import MatchState
from .zones import expire_reveals


def advance_state_id_and_expire_reveals(state: MatchState) -> MatchState:
    next_state_id = state.ctx._stateID + 1
    zones = expire_reveals(state.ctx.zones, current_state_id=next_state_id)
    return MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            _stateID=next_state_id,
            zones=zones,
        ),
    )

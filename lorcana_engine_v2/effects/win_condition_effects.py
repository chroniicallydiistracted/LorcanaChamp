from __future__ import annotations

from collections.abc import Mapping

from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import base_zone_from_key


def _state_of(target: MatchState | object) -> MatchState:
    if isinstance(target, MatchState):
        return target
    state = getattr(target, "state", None)
    if isinstance(state, MatchState):
        return state
    raise TypeError("recompute_lore_to_win requires MatchState or runtime context")


def _write(target: MatchState | object, state: MatchState) -> MatchState:
    if isinstance(target, MatchState):
        return state
    if hasattr(target, "set_state"):
        target.set_state(state)
    elif hasattr(target, "_draft") and hasattr(target._draft, "set_state"):
        target._draft.set_state(state)
    if hasattr(target, "G"):
        target.G = state.G
    return state


def _definition(target: MatchState | object, card_id):
    cards = getattr(target, "cards", None)
    if cards is not None:
        try:
            return cards.getDefinition(card_id)
        except Exception:
            return None
    return None


def recompute_lore_to_win(context: MatchState | object) -> MatchState:
    state = _state_of(context)
    overrides: dict[PlayerId, int] = {}
    for card_id, entry in state.ctx.zones.private.cardIndex.items():
        if str(base_zone_from_key(entry.zoneKey)) != "play":
            continue
        controller = entry.controllerID or entry.ownerID
        definition = _definition(context, card_id)
        if definition is None:
            continue
        for ability in definition.abilities:
            if ability.kind != "static":
                continue
            effect = ability.raw.get("effect")
            if not isinstance(effect, Mapping) or effect.get("type") != "win-condition-modification":
                continue
            lore_required = effect.get("loreRequired")
            if not isinstance(lore_required, int):
                continue
            target = str(effect.get("target") or "").upper()
            if target in {"OPPONENT", "OPPONENTS", "EACH_OPPONENT"}:
                players = tuple(player for player in state.G.lore if player != controller)
            elif target in {"ALL", "ALL_PLAYERS", "EACH_PLAYER"}:
                players = tuple(state.G.lore)
            else:
                players = ()
            for player_id in players:
                overrides[player_id] = max(overrides.get(player_id, 20), lore_required)
    non_default = {player_id: value for player_id, value in overrides.items() if value != 20}
    next_state = MatchState(G=state.G.with_updates(loreToWin=non_default or None), ctx=state.ctx)
    return _write(context, next_state)


recomputeLoreToWin = recompute_lore_to_win


__all__ = ["recomputeLoreToWin", "recompute_lore_to_win"]

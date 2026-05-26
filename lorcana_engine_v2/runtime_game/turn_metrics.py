from __future__ import annotations

from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState


def _state_of(target: MatchState | object) -> MatchState:
    if isinstance(target, MatchState):
        return target
    state = getattr(target, "state", None)
    if isinstance(state, MatchState):
        return state
    raise TypeError("turn metric helper requires MatchState or runtime context")


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


def _append_unique(values: tuple[InstanceId, ...], card_id: InstanceId | str) -> tuple[InstanceId, ...]:
    cid = InstanceId(str(card_id))
    return values if cid in values else values + (cid,)


def record_card_played_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(turnMetadata=replace(metadata, cardsPlayedThisTurn=_append_unique(metadata.cardsPlayedThisTurn, card_id))),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_shift_played_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(turnMetadata=replace(metadata, shiftPlayedThisTurn=_append_unique(metadata.shiftPlayedThisTurn, card_id))),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_discard_exit_this_turn(target: MatchState | object, amount: int = 1) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(turnMetadata=replace(metadata, discardCardsLeftThisTurn=metadata.discardCardsLeftThisTurn + max(0, amount))),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_banished_character_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(turnMetadata=replace(metadata, banishedCharactersThisTurn=_append_unique(metadata.banishedCharactersThisTurn, card_id))),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_card_put_into_discard_this_turn(target: MatchState | object, owner_id: PlayerId | str, amount: int = 1) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    owner = PlayerId(str(owner_id))
    by_owner = dict(metadata.cardsPutIntoDiscardThisTurnByOwner)
    by_owner[owner] = int(by_owner.get(owner, 0)) + max(0, amount)
    next_state = MatchState(G=state.G.with_updates(turnMetadata=replace(metadata, cardsPutIntoDiscardThisTurnByOwner=by_owner)), ctx=state.ctx)
    return _write(target, next_state)


def record_cards_under_this_turn(target: MatchState | object, parent_id: InstanceId | str, card_ids) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    parent = InstanceId(str(parent_id))
    current = dict(metadata.cardsUnderThisTurn or {})
    existing = tuple(current.get(parent, ()))
    for card_id in tuple(InstanceId(str(item)) for item in card_ids):
        if card_id not in existing:
            existing = existing + (card_id,)
    current[parent] = existing
    next_state = MatchState(G=state.G.with_updates(turnMetadata=replace(metadata, cardsUnderThisTurn=current)), ctx=state.ctx)
    return _write(target, next_state)


__all__ = [
    "record_banished_character_this_turn",
    "record_card_played_this_turn",
    "record_card_put_into_discard_this_turn",
    "record_cards_under_this_turn",
    "record_discard_exit_this_turn",
    "record_shift_played_this_turn",
]

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState


def _state_of(target: MatchState | object) -> MatchState:
    if isinstance(target, MatchState):
        return target
    state = getattr(target, "state", None)
    if isinstance(state, MatchState):
        return state
    draft = getattr(target, "_draft", None)
    draft_state = getattr(draft, "state", None)
    if isinstance(draft_state, MatchState):
        return draft_state
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


def _definition(target: MatchState | object, state: MatchState, card_id: InstanceId):
    cards = getattr(target, "cards", None)
    if cards is not None:
        getter = getattr(cards, "getDefinition", None) or getattr(cards, "get_definition", None)
        if callable(getter):
            try:
                return getter(card_id)
            except Exception:
                pass
        try:
            return cards.require(card_id).definition
        except Exception:
            pass

    resources = getattr(target, "resources", None)
    if resources is None:
        query = getattr(getattr(target, "cards", None), "_query", None)
        resources = getattr(query, "resources", None)
    if resources is None:
        return None

    record = resources.instances.get(card_id)
    return resources.cards.get(record.definition_id) if record is not None else None


def _card_owner(target: MatchState | object, state: MatchState, card_id: InstanceId) -> PlayerId | None:
    framework = getattr(target, "framework", None)
    zones_api = getattr(framework, "zones", None)
    getter = getattr(zones_api, "getCardOwner", None) or getattr(zones_api, "get_card_owner", None)
    if callable(getter):
        try:
            owner = getter(card_id)
            return PlayerId(str(owner)) if owner is not None else None
        except Exception:
            pass

    entry = state.ctx.zones.private.cardIndex.get(card_id)
    return entry.ownerID if entry is not None else None


def _is_character(target: MatchState | object, state: MatchState, card_id: InstanceId) -> bool:
    definition = _definition(target, state, card_id)
    return (
        getattr(definition, "card_type", None) == "character"
        or getattr(definition, "cardType", None) == "character"
    )


def _increment_record(record, player_id: PlayerId | str, amount: int = 1):
    player = PlayerId(str(player_id))
    next_record = dict(record or {})
    next_record[player] = int(next_record.get(player, 0)) + amount
    return next_record


def _append_unique(values: tuple[InstanceId, ...], card_id: InstanceId | str) -> tuple[InstanceId, ...]:
    cid = InstanceId(str(card_id))
    return values if cid in values else values + (cid,)


def _append(values: tuple[InstanceId, ...], card_id: InstanceId | str) -> tuple[InstanceId, ...]:
    return values + (InstanceId(str(card_id)),)


def record_card_played_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                cardsPlayedThisTurn=_append(metadata.cardsPlayedThisTurn, card_id),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_shift_played_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                shiftPlayedThisTurn=_append(metadata.shiftPlayedThisTurn, card_id),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_challenge_by_player_this_turn(target: MatchState | object, player_id: PlayerId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                challengesByPlayerThisTurn=_increment_record(
                    metadata.challengesByPlayerThisTurn,
                    player_id,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_damaged_character_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    cid = InstanceId(str(card_id))
    if not _is_character(target, state, cid):
        return state

    owner = _card_owner(target, state, cid)
    if owner is None:
        return state

    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                damagedCharactersByOwnerThisTurn=_increment_record(
                    metadata.damagedCharactersByOwnerThisTurn,
                    owner,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_damage_removed_this_turn(
    target: MatchState | object,
    player_id: PlayerId | str,
    amount: int,
) -> MatchState:
    if amount <= 0:
        return _state_of(target)

    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                damageRemovedByPlayerThisTurn=_increment_record(
                    metadata.damageRemovedByPlayerThisTurn,
                    player_id,
                    amount,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_banished_character_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    cid = InstanceId(str(card_id))
    if not _is_character(target, state, cid):
        return state

    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                banishedCharactersThisTurn=_append_unique(metadata.banishedCharactersThisTurn, cid),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_banished_character_in_challenge_this_turn(
    target: MatchState | object,
    card_id: InstanceId | str,
) -> MatchState:
    state = _state_of(target)
    cid = InstanceId(str(card_id))
    if not _is_character(target, state, cid):
        return state

    owner = _card_owner(target, state, cid)
    if owner is None:
        return state

    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                banishedCharactersInChallengeByOwnerThisTurn=_increment_record(
                    metadata.banishedCharactersInChallengeByOwnerThisTurn,
                    owner,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_challenged_character_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    cid = InstanceId(str(card_id))
    if not _is_character(target, state, cid):
        return state

    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                challengedCharactersThisTurn=_append_unique(metadata.challengedCharactersThisTurn, cid),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_discard_exit_this_turn(target: MatchState | object, amount: int = 1) -> MatchState:
    if amount <= 0:
        return _state_of(target)

    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                discardCardsLeftThisTurn=metadata.discardCardsLeftThisTurn + amount,
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_card_put_into_discard_this_turn(
    target: MatchState | object,
    owner_id: PlayerId | str,
    amount: int = 1,
) -> MatchState:
    if amount <= 0:
        return _state_of(target)

    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                cardsPutIntoDiscardThisTurnByOwner=_increment_record(
                    metadata.cardsPutIntoDiscardThisTurnByOwner,
                    owner_id,
                    amount,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_card_put_into_inkwell_this_turn(target: MatchState | object, card_id: InstanceId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                cardsPutIntoInkwellThisTurn=_append_unique(
                    metadata.cardsPutIntoInkwellThisTurn,
                    card_id,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def is_discard_zone_key(zone_key: object) -> bool:
    text = str(zone_key) if zone_key is not None else ""
    return text == "discard" or text.startswith("discard:")


def record_card_drawn_this_turn(target: MatchState | object, player_id: PlayerId | str) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(
                metadata,
                cardsDrawnThisTurnByPlayer=_increment_record(
                    metadata.cardsDrawnThisTurnByPlayer,
                    player_id,
                ),
            )
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_card_put_under_this_turn(
    target: MatchState | object,
    parent_id: InstanceId | str,
    child_id: InstanceId | str,
) -> MatchState:
    state = _state_of(target)
    metadata = state.G.turnMetadata
    parent = InstanceId(str(parent_id))
    child = InstanceId(str(child_id))
    cards_under = dict(metadata.cardsUnderThisTurn or {})
    existing = tuple(cards_under.get(parent, ()))
    if child not in existing:
        cards_under[parent] = existing + (child,)

    next_state = MatchState(
        G=state.G.with_updates(
            turnMetadata=replace(metadata, cardsUnderThisTurn=cards_under),
        ),
        ctx=state.ctx,
    )
    return _write(target, next_state)


def record_cards_under_this_turn(
    target: MatchState | object,
    parent_id: InstanceId | str,
    card_ids: Iterable[InstanceId | str],
) -> MatchState:
    state = _state_of(target)
    for card_id in card_ids:
        state = record_card_put_under_this_turn(
            target if not isinstance(target, MatchState) else state,
            parent_id,
            card_id,
        )
    return _state_of(target) if not isinstance(target, MatchState) else state


__all__ = [
    "is_discard_zone_key",
    "record_banished_character_in_challenge_this_turn",
    "record_banished_character_this_turn",
    "record_card_drawn_this_turn",
    "record_card_played_this_turn",
    "record_card_put_into_discard_this_turn",
    "record_card_put_into_inkwell_this_turn",
    "record_card_put_under_this_turn",
    "record_cards_under_this_turn",
    "record_challenge_by_player_this_turn",
    "record_challenged_character_this_turn",
    "record_damage_removed_this_turn",
    "record_damaged_character_this_turn",
    "record_discard_exit_this_turn",
    "record_shift_played_this_turn",
]
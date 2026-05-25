from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState, TemporaryPlayerRestrictionsState
from lorcana_engine_v2.core.zones import CardMeta, ZoneRuntimePrivateState, ZoneRuntimeState
from lorcana_engine_v2.rules.effect_registry import is_effect_expired, resolve_effect_window
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


def _effect_map(raw: Mapping[str, int] | None) -> dict[str, int]:
    if raw is None:
        return {}
    return {str(key): int(value) for key, value in raw.items() if isinstance(value, int)}


def _payload_map(raw: Mapping[str, object] | None) -> dict[str, object]:
    if raw is None:
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(key, str)}


def _temporary_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def resolve_temporary_effect_window(
    current_turn: int,
    duration: object,
    *,
    current_player_id: PlayerId | str | None = None,
    target_owner_id: PlayerId | str | None = None,
):
    return resolve_effect_window(
        current_turn,
        duration,
        current_player_id=current_player_id,
        target_owner_id=target_owner_id,
    )


def resolve_temporary_effect_expiry_turn(
    current_turn: int,
    duration: object,
    *,
    current_player_id: PlayerId | str | None = None,
    target_owner_id: PlayerId | str | None = None,
) -> int:
    return resolve_temporary_effect_window(
        current_turn,
        duration,
        current_player_id=current_player_id,
        target_owner_id=target_owner_id,
    ).expiresAtTurn


def _add_expiring_key(
    values: Mapping[str, int] | None,
    starts: Mapping[str, int] | None,
    key: str,
    expires_at_turn: int,
    starts_at_turn: int | None,
) -> tuple[dict[str, int], dict[str, int]]:
    value_map = _effect_map(values)
    start_map = _effect_map(starts)
    start = starts_at_turn if isinstance(starts_at_turn, int) and starts_at_turn >= 1 else 1
    current_expiry = value_map.get(key, 0)
    if expires_at_turn > current_expiry:
        value_map[key] = expires_at_turn
        start_map[key] = start
    elif expires_at_turn == current_expiry:
        start_map[key] = min(start_map.get(key, start), start)
    return value_map, start_map


def add_temporary_keyword(
    meta: CardMeta,
    keyword: str,
    expires_at_turn: int,
    value: int | None = None,
    starts_at_turn: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> CardMeta:
    normalized = _temporary_key(keyword)
    if not normalized or expires_at_turn < 1:
        return meta
    keywords, starts = _add_expiring_key(
        meta.temporaryKeywords,
        meta.temporaryKeywordStarts,
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    values = _effect_map(meta.temporaryKeywordValues)
    if isinstance(value, int) and value > 0:
        values[normalized] = values.get(normalized, 0) + value
    payloads = _payload_map(meta.temporaryKeywordPayloads)
    if payload and isinstance(payload.get("type"), str):
        payloads[normalized] = dict(payload)
    return meta.with_updates(
        temporaryKeywords=keywords or None,
        temporaryKeywordStarts=starts or None,
        temporaryKeywordValues=values or None,
        temporaryKeywordPayloads=payloads or None,
    )


def add_temporary_lost_keyword(
    meta: CardMeta,
    keyword: str,
    expires_at_turn: int,
    starts_at_turn: int | None = None,
) -> CardMeta:
    normalized = _temporary_key(keyword)
    if not normalized or expires_at_turn < 1:
        return meta
    lost, starts = _add_expiring_key(
        meta.temporaryLostKeywords,
        meta.temporaryLostKeywordStarts,
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    return meta.with_updates(
        temporaryLostKeywords=lost or None,
        temporaryLostKeywordStarts=starts or None,
    )


def has_temporary_keyword(meta: CardMeta | None, current_turn: int, keyword: str) -> bool:
    normalized = _temporary_key(keyword)
    if meta is None or normalized is None:
        return False
    keywords = _effect_map(meta.temporaryKeywords)
    starts = _effect_map(meta.temporaryKeywordStarts)
    return starts.get(normalized, 1) <= current_turn <= keywords.get(normalized, 0)


def has_temporary_lost_keyword(meta: CardMeta | None, current_turn: int, keyword: str) -> bool:
    normalized = _temporary_key(keyword)
    if meta is None or normalized is None:
        return False
    lost = _effect_map(meta.temporaryLostKeywords)
    starts = _effect_map(meta.temporaryLostKeywordStarts)
    return starts.get(normalized, 1) <= current_turn <= lost.get(normalized, 0)


def get_temporary_keyword_value(meta: CardMeta | None, current_turn: int, keyword: str) -> int:
    if not has_temporary_keyword(meta, current_turn, keyword) or meta is None:
        return 0
    normalized = _temporary_key(keyword)
    return _effect_map(meta.temporaryKeywordValues).get(normalized or "", 0)


def add_temporary_classification(
    meta: CardMeta,
    classification: str,
    expires_at_turn: int,
    starts_at_turn: int | None = None,
) -> CardMeta:
    normalized = _temporary_key(classification)
    if not normalized or expires_at_turn < 1:
        return meta
    classifications, starts = _add_expiring_key(
        meta.temporaryClassifications,
        meta.temporaryClassificationStarts,
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    return meta.with_updates(
        temporaryClassifications=classifications or None,
        temporaryClassificationStarts=starts or None,
    )


def add_temporary_ability(
    meta: CardMeta,
    ability: str,
    expires_at_turn: int,
    starts_at_turn: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> CardMeta:
    normalized = _temporary_key(ability)
    if not normalized or expires_at_turn < 1:
        return meta
    abilities, starts = _add_expiring_key(
        meta.temporaryAbilities,
        meta.temporaryAbilityStarts,
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    payloads = _payload_map(meta.temporaryAbilityPayloads)
    if payload and isinstance(payload.get("type"), str):
        payloads[normalized] = dict(payload)
    return meta.with_updates(
        temporaryAbilities=abilities or None,
        temporaryAbilityStarts=starts or None,
        temporaryAbilityPayloads=payloads or None,
    )


def has_temporary_ability(meta: CardMeta | None, current_turn: int, ability: str) -> bool:
    normalized = _temporary_key(ability)
    if meta is None or normalized is None:
        return False
    abilities = _effect_map(meta.temporaryAbilities)
    starts = _effect_map(meta.temporaryAbilityStarts)
    return starts.get(normalized, 1) <= current_turn <= abilities.get(normalized, 0)


def get_temporary_ability_payload(meta: CardMeta | None, current_turn: int, ability: str) -> object | None:
    if not has_temporary_ability(meta, current_turn, ability) or meta is None:
        return None
    normalized = _temporary_key(ability)
    return _payload_map(meta.temporaryAbilityPayloads).get(normalized or "")


def add_temporary_restriction(
    meta: CardMeta,
    restriction: str,
    expires_at_turn: int,
    starts_at_turn: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> CardMeta:
    normalized = _temporary_key(restriction)
    if not normalized or expires_at_turn < 1:
        return meta
    restrictions, starts = _add_expiring_key(
        meta.temporaryRestrictions,
        meta.temporaryRestrictionStarts,
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    payloads = _payload_map(meta.temporaryRestrictionPayloads)
    if payload and isinstance(payload.get("type"), str):
        payloads[normalized] = dict(payload)
    return meta.with_updates(
        temporaryRestrictions=restrictions or None,
        temporaryRestrictionStarts=starts or None,
        temporaryRestrictionPayloads=payloads or None,
    )


def has_temporary_restriction(meta: CardMeta | None, current_turn: int, restriction: str) -> bool:
    normalized = _temporary_key(restriction)
    if meta is None or normalized is None:
        return False
    candidates = (
        (normalized, "cant-quest-or-challenge")
        if normalized in {"cant-quest", "cant-challenge"}
        else (normalized,)
    )
    restrictions = _effect_map(meta.temporaryRestrictions)
    starts = _effect_map(meta.temporaryRestrictionStarts)
    return any(starts.get(candidate, 1) <= current_turn <= restrictions.get(candidate, 0) for candidate in candidates)


def prune_expired_temporary_effects(meta: CardMeta | None, current_turn: int) -> CardMeta | None:
    if meta is None:
        return None

    def prune(values: Mapping[str, int] | None, *companions: Mapping[str, object] | None):
        active = {
            key: value
            for key, value in _effect_map(values).items()
            if not is_effect_expired({"expiresAtTurn": value}, current_turn)
        }
        pruned_companions = []
        for companion in companions:
            pruned_companions.append({key: value for key, value in _payload_map(companion).items() if key in active})
        return active, pruned_companions

    keywords, (keyword_starts, keyword_values, keyword_payloads) = prune(
        meta.temporaryKeywords,
        meta.temporaryKeywordStarts,
        meta.temporaryKeywordValues,
        meta.temporaryKeywordPayloads,
    )
    lost_keywords, (lost_keyword_starts,) = prune(
        meta.temporaryLostKeywords,
        meta.temporaryLostKeywordStarts,
    )
    classifications, (classification_starts,) = prune(
        meta.temporaryClassifications,
        meta.temporaryClassificationStarts,
    )
    abilities, (ability_starts, ability_payloads) = prune(
        meta.temporaryAbilities,
        meta.temporaryAbilityStarts,
        meta.temporaryAbilityPayloads,
    )
    restrictions, (restriction_starts, restriction_payloads) = prune(
        meta.temporaryRestrictions,
        meta.temporaryRestrictionStarts,
        meta.temporaryRestrictionPayloads,
    )
    return meta.with_updates(
        temporaryKeywords=keywords or None,
        temporaryKeywordStarts=keyword_starts or None,
        temporaryKeywordValues=keyword_values or None,
        temporaryKeywordPayloads=keyword_payloads or None,
        temporaryLostKeywords=lost_keywords or None,
        temporaryLostKeywordStarts=lost_keyword_starts or None,
        temporaryClassifications=classifications or None,
        temporaryClassificationStarts=classification_starts or None,
        temporaryAbilities=abilities or None,
        temporaryAbilityStarts=ability_starts or None,
        temporaryAbilityPayloads=ability_payloads or None,
        temporaryRestrictions=restrictions or None,
        temporaryRestrictionStarts=restriction_starts or None,
        temporaryRestrictionPayloads=restriction_payloads or None,
    )


def add_temporary_player_restriction(
    state: TemporaryPlayerRestrictionsState,
    player_id: PlayerId | str,
    restriction: str,
    expires_at_turn: int,
    starts_at_turn: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> TemporaryPlayerRestrictionsState:
    normalized = _temporary_key(restriction)
    if not normalized or expires_at_turn < 1:
        return state
    player = PlayerId(str(player_id))
    restrictions_by_player = {PlayerId(str(pid)): dict(values) for pid, values in state.restrictionsByPlayer.items()}
    starts_by_player = {PlayerId(str(pid)): dict(values) for pid, values in state.startsByPlayer.items()}
    payloads_by_player = {PlayerId(str(pid)): dict(values) for pid, values in state.payloadsByPlayer.items()}
    restrictions, starts = _add_expiring_key(
        restrictions_by_player.get(player),
        starts_by_player.get(player),
        normalized,
        expires_at_turn,
        starts_at_turn,
    )
    restrictions_by_player[player] = restrictions
    starts_by_player[player] = starts
    if payload and isinstance(payload.get("type"), str):
        payloads = payloads_by_player.get(player, {})
        payloads[normalized] = dict(payload)
        payloads_by_player[player] = payloads
    return TemporaryPlayerRestrictionsState(
        restrictionsByPlayer=restrictions_by_player,
        startsByPlayer=starts_by_player,
        payloadsByPlayer=payloads_by_player,
    )


def has_temporary_player_restriction(
    state: TemporaryPlayerRestrictionsState | None,
    player_id: PlayerId | str,
    current_turn: int,
    restriction: str,
) -> bool:
    if state is None:
        return False
    normalized = _temporary_key(restriction)
    if normalized is None:
        return False
    player = PlayerId(str(player_id))
    restrictions = _effect_map(state.restrictionsByPlayer.get(player))
    starts = _effect_map(state.startsByPlayer.get(player))
    return starts.get(normalized, 1) <= current_turn <= restrictions.get(normalized, 0)


def prune_expired_temporary_player_restrictions(
    state: TemporaryPlayerRestrictionsState | None,
    current_turn: int,
) -> TemporaryPlayerRestrictionsState | None:
    if state is None:
        return None
    restrictions_by_player: dict[PlayerId, dict[str, int]] = {}
    starts_by_player: dict[PlayerId, dict[str, int]] = {}
    payloads_by_player: dict[PlayerId, dict[str, object]] = {}
    players = set(state.restrictionsByPlayer) | set(state.startsByPlayer) | set(state.payloadsByPlayer)
    for player in players:
        restrictions = {
            key: value
            for key, value in _effect_map(state.restrictionsByPlayer.get(player)).items()
            if not is_effect_expired({"expiresAtTurn": value}, current_turn)
        }
        starts = {key: value for key, value in _effect_map(state.startsByPlayer.get(player)).items() if key in restrictions}
        payloads = {key: value for key, value in _payload_map(state.payloadsByPlayer.get(player)).items() if key in restrictions}
        if restrictions:
            restrictions_by_player[player] = restrictions
        if starts:
            starts_by_player[player] = starts
        if payloads:
            payloads_by_player[player] = payloads
    return TemporaryPlayerRestrictionsState(
        restrictionsByPlayer=restrictions_by_player,
        startsByPlayer=starts_by_player,
        payloadsByPlayer=payloads_by_player,
    )


def cleanup_expired_effects(
    target: MatchState | object,
    current_turn: int | None = None,
) -> MatchState:
    state = _state_of(target)
    turn = current_turn if current_turn is not None else (state.ctx.status.turn or 1)
    card_meta = dict(state.ctx.zones.private.cardMeta)
    for card_id, meta in tuple(card_meta.items()):
        pruned = prune_expired_temporary_effects(meta, turn)
        if pruned is None:
            card_meta.pop(card_id, None)
        else:
            card_meta[card_id] = pruned
    zones = ZoneRuntimeState(
        public=state.ctx.zones.public,
        reveals=state.ctx.zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=state.ctx.zones.private.zoneCards,
            cardIndex=state.ctx.zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )
    next_state = MatchState(
        G=state.G.with_updates(
            temporaryPlayerRestrictions=prune_expired_temporary_player_restrictions(
                state.G.temporaryPlayerRestrictions,
                turn,
            )
            or TemporaryPlayerRestrictionsState()
        ),
        ctx=state.ctx.with_updates(zones=zones),
    )

    from lorcana_engine_v2.effects.continuous_effects import cleanup_expired_continuous_effects
    from lorcana_engine_v2.effects.replacement_effects import prune_expired_replacement_effects

    next_state = cleanup_expired_continuous_effects(next_state, turn)
    next_state = prune_expired_replacement_effects(next_state, turn)
    return _write_state(target, next_state)


__all__ = [
    "add_temporary_ability",
    "add_temporary_classification",
    "add_temporary_keyword",
    "add_temporary_lost_keyword",
    "add_temporary_player_restriction",
    "add_temporary_restriction",
    "cleanup_expired_effects",
    "get_temporary_ability_payload",
    "get_temporary_keyword_value",
    "has_temporary_ability",
    "has_temporary_keyword",
    "has_temporary_lost_keyword",
    "has_temporary_player_restriction",
    "has_temporary_restriction",
    "prune_expired_temporary_effects",
    "prune_expired_temporary_player_restrictions",
    "resolve_temporary_effect_expiry_turn",
    "resolve_temporary_effect_window",
]

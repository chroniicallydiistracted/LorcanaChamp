from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from lorcana_engine_v2.core.turn_owner import resolve_turn_owner_id
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState, ReplacementEffectsState, ReplacementUsageLedger
from lorcana_engine_v2.core.zones import base_zone_from_key
from lorcana_engine_v2.rules.effect_registry import is_effect_expired, resolve_effect_window
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


MAX_REPLACEMENT_PASSES = 100


@dataclass(frozen=True, slots=True)
class ReplacementRegistration:
    id: str
    sourceId: InstanceId
    controllerId: PlayerId
    replacement: Mapping[str, object]
    targetId: InstanceId | None
    createdAtTurn: int
    startsAtTurn: int
    expiresAtTurn: int


@dataclass(frozen=True, slots=True)
class ReplacementCandidate:
    id: str
    applicationKey: str
    event: Mapping[str, object]
    consumeRegistrationId: str | None = None
    consumeUsageKey: tuple[InstanceId, str] | None = None


def _event_kind(event: Mapping[str, object]) -> str:
    return str(event.get("kind", ""))


def _event_amount(event: Mapping[str, object]) -> int:
    value = event.get("amount", 0)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0


def _owner_for_card(state: MatchState, card_id: InstanceId | str | None) -> PlayerId | None:
    if card_id is None:
        return None
    entry = state.ctx.zones.private.cardIndex.get(InstanceId(str(card_id)))
    return entry.ownerID if entry is not None else None


def _card_in_play(state: MatchState, card_id: InstanceId | str) -> bool:
    entry = state.ctx.zones.private.cardIndex.get(InstanceId(str(card_id)))
    return entry is not None and str(base_zone_from_key(entry.zoneKey)) == "play"


def _definition_for_card(target: MatchState | object, state: MatchState, card_id: InstanceId | str):
    cards = getattr(target, "cards", None)
    if cards is not None:
        try:
            return cards.getDefinition(card_id)
        except Exception:
            return None
    query = getattr(cards, "_query", None)
    resources = getattr(query, "resources", None)
    if resources is not None:
        try:
            record = resources.instances.require(InstanceId(str(card_id)))
            return resources.cards.get(str(record.definition_id))
        except Exception:
            return None
    resources = getattr(target, "resources", None)
    if resources is not None:
        try:
            record = resources.instances.require(InstanceId(str(card_id)))
            return resources.cards.get(str(record.definition_id))
        except Exception:
            return None
    return None


def _turn_player(state: MatchState) -> PlayerId | None:
    return resolve_turn_owner_id(state)


def _condition_matches(state: MatchState, controller_id: PlayerId, condition: object) -> bool:
    if condition is None:
        return True
    if not isinstance(condition, Mapping):
        return False
    if condition.get("type") in {"during-turn", "turn"}:
        whose = condition.get("whose")
        turn_player = _turn_player(state)
        if whose == "your":
            return turn_player == controller_id
        if whose == "opponent":
            return turn_player is not None and turn_player != controller_id
    return False


def _printed_replacement_candidates(
    target: MatchState | object,
    state: MatchState,
    event: Mapping[str, object],
) -> tuple[ReplacementCandidate, ...]:
    candidates: list[ReplacementCandidate] = []
    event_kind = _event_kind(event)
    amount = _event_amount(event)
    for card_id in state.ctx.zones.private.cardIndex:
        if not _card_in_play(state, card_id):
            continue
        definition = _definition_for_card(target, state, card_id)
        if definition is None:
            continue
        controller_id = _owner_for_card(state, card_id)
        if controller_id is None:
            continue
        for ability in getattr(definition, "abilities", ()):
            if getattr(ability, "kind", None) != "replacement":
                continue
            raw = getattr(ability, "raw", {})
            if not isinstance(raw, Mapping):
                continue
            ability_id = str(raw.get("id") or f"{card_id}:replacement")
            replacement = raw.get("replacement")
            replaces = raw.get("replaces")

            if replaces == "lose-lore" and replacement == "prevent":
                if event_kind == "lose-lore" and amount > 0 and event.get("playerId") == controller_id and _condition_matches(state, controller_id, raw.get("condition")):
                    next_event = {**event, "amount": 0}
                    candidates.append(ReplacementCandidate(f"{card_id}:{ability_id}:prevent-lose-lore", f"{card_id}:{ability_id}:prevent-lose-lore", next_event))
                continue

            if replaces == "discard" and replacement == "prevent":
                if event_kind == "discard" and not bool(event.get("prevented")) and event.get("targetPlayerId") == controller_id and _condition_matches(state, controller_id, raw.get("condition")):
                    next_event = {**event, "prevented": True}
                    candidates.append(ReplacementCandidate(f"{card_id}:{ability_id}:prevent-discard", f"{card_id}:{ability_id}:prevent-discard", next_event))
                continue

            if not isinstance(replacement, Mapping):
                continue

            if replacement.get("type") == "prevent-remove-damage":
                if event_kind == "remove-damage" and amount > 0:
                    candidates.append(
                        ReplacementCandidate(
                            f"{card_id}:{ability_id}:prevent-remove-damage",
                            f"{card_id}:{ability_id}:prevent-remove-damage",
                            {**event, "amount": 0},
                        )
                    )
                continue

            if replacement.get("type") == "redirect-damage":
                if event_kind not in {"deal-damage", "challenge-damage", "put-damage"} or amount <= 0:
                    continue
                if replacement.get("appliesTo") != "your-other-characters":
                    continue
                target_id = event.get("targetId")
                if target_id is None or InstanceId(str(target_id)) == card_id:
                    continue
                if _owner_for_card(state, InstanceId(str(target_id))) != controller_id:
                    continue
                candidates.append(
                    ReplacementCandidate(
                        f"{card_id}:{ability_id}:redirect-damage",
                        f"{card_id}:{ability_id}:redirect-damage",
                        {**event, "targetId": card_id},
                    )
                )
                continue

            if replacement.get("type") == "prevent-damage":
                if event_kind not in {"deal-damage", "challenge-damage", "put-damage"} or amount <= 0:
                    continue
                if replacement.get("appliesTo") != "self" or event.get("targetId") != card_id:
                    continue
                if replacement.get("during") == "opponents-turn" and _turn_player(state) == controller_id:
                    continue
                usage_key = (card_id, ability_id)
                if replacement.get("firstTimeEachTurn") == "opponent-turn" and _usage_count(state, card_id, ability_id) > 0:
                    continue
                candidates.append(
                    ReplacementCandidate(
                        f"{card_id}:{ability_id}:prevent-damage",
                        f"{card_id}:{ability_id}:prevent-damage",
                        {**event, "amount": 0},
                        consumeUsageKey=usage_key if replacement.get("firstTimeEachTurn") == "opponent-turn" else None,
                    )
                )
    return tuple(candidates)


def _usage_count(state: MatchState, source_id: InstanceId, ability_key: str) -> int:
    turn = state.ctx.status.turn or 1
    key = f"{turn}:{source_id}:{ability_key}"
    return int(state.G.replacementEffects.usageLedger.perTurn.get(key, 0))


def _increment_usage(state: MatchState, source_id: InstanceId, ability_key: str) -> MatchState:
    turn = state.ctx.status.turn or 1
    key = f"{turn}:{source_id}:{ability_key}"
    per_turn = dict(state.G.replacementEffects.usageLedger.perTurn)
    per_turn[key] = int(per_turn.get(key, 0)) + 1
    ledger = replace(state.G.replacementEffects.usageLedger, perTurn=per_turn)
    replacement_state = replace(state.G.replacementEffects, usageLedger=ledger)
    return MatchState(G=state.G.with_updates(replacementEffects=replacement_state), ctx=state.ctx)


def _event_kinds_for_replacement(replacement: Mapping[str, object]) -> tuple[str, ...]:
    event_kinds = replacement.get("eventKinds")
    if isinstance(event_kinds, (list, tuple)):
        return tuple(str(kind) for kind in event_kinds)
    if replacement.get("type") == "prevent-damage":
        return ("deal-damage", "challenge-damage", "put-damage")
    if replacement.get("type") == "zone-destination":
        return ("zone-change",)
    return ()


def _rebuild_by_event_kind(registrations: tuple[object, ...]) -> dict[str, tuple[str, ...]]:
    buckets: dict[str, list[str]] = {}
    for registration in registrations:
        if not isinstance(registration, ReplacementRegistration):
            continue
        for kind in _event_kinds_for_replacement(registration.replacement):
            buckets.setdefault(kind, []).append(registration.id)
    return {kind: tuple(ids) for kind, ids in buckets.items()}


def _resolve_registered_target_id(
    replacement: Mapping[str, object],
    card_played: Mapping[str, object],
    resolution_input: Mapping[str, object] | None,
) -> InstanceId | None:
    target_ref = replacement.get("targetRef")
    if target_ref == "source":
        return InstanceId(str(card_played.get("cardId")))
    if target_ref == "selected-target" and resolution_input is not None:
        targets = resolution_input.get("targets")
        if isinstance(targets, str):
            return InstanceId(targets)
        if isinstance(targets, (list, tuple)) and targets:
            return InstanceId(str(targets[0]))
    if target_ref == "chosen-card" and resolution_input is not None:
        snapshot = resolution_input.get("eventSnapshot")
        if isinstance(snapshot, Mapping) and snapshot.get("chosenCardId") is not None:
            return InstanceId(str(snapshot["chosenCardId"]))
    if target_ref == "trigger-subject" and resolution_input is not None:
        trigger_context = resolution_input.get("triggerContext")
        if isinstance(trigger_context, Mapping) and trigger_context.get("subjectCardId") is not None:
            return InstanceId(str(trigger_context["subjectCardId"]))
    return None


def register_replacement_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    replacement: Mapping[str, object],
    duration: object,
    resolution_input: Mapping[str, object] | None = None,
) -> MatchState:
    state = _state_of(target)
    current_turn = state.ctx.status.turn or 1
    source_id = InstanceId(str(card_played.get("cardId")))
    controller_id = PlayerId(str(card_played.get("playerId")))
    target_id = _resolve_registered_target_id(replacement, card_played, resolution_input)
    window = resolve_effect_window(
        current_turn,
        duration,
        current_player_id=controller_id,
        target_owner_id=_owner_for_card(state, target_id),
    )
    replacement_state = state.G.replacementEffects
    registration = ReplacementRegistration(
        id=f"replacement:{replacement_state.nextSeq}",
        sourceId=source_id,
        controllerId=controller_id,
        replacement=dict(replacement),
        targetId=target_id,
        createdAtTurn=current_turn,
        startsAtTurn=window.startsAtTurn,
        expiresAtTurn=window.expiresAtTurn,
    )
    registrations = tuple(replacement_state.registrations) + (registration,)
    next_replacement_state = replace(
        replacement_state,
        nextSeq=replacement_state.nextSeq + 1,
        registrations=registrations,
        byEventKind=_rebuild_by_event_kind(registrations),
    )
    next_state = MatchState(G=state.G.with_updates(replacementEffects=next_replacement_state), ctx=state.ctx)
    return _write_state(target, next_state)


def _registered_replacement_candidates(
    state: MatchState,
    event: Mapping[str, object],
) -> tuple[ReplacementCandidate, ...]:
    event_kind = _event_kind(event)
    current_turn = state.ctx.status.turn or 1
    ids = set(state.G.replacementEffects.byEventKind.get(event_kind, ()))
    candidates: list[ReplacementCandidate] = []
    for registration in state.G.replacementEffects.registrations:
        if not isinstance(registration, ReplacementRegistration) or registration.id not in ids:
            continue
        if current_turn < registration.startsAtTurn or current_turn > registration.expiresAtTurn:
            continue
        replacement = registration.replacement
        if replacement.get("type") == "prevent-damage":
            if event_kind not in {"deal-damage", "challenge-damage", "put-damage"}:
                continue
            if _event_amount(event) <= 0 or event.get("targetId") != registration.targetId:
                continue
            candidates.append(
                ReplacementCandidate(
                    registration.id,
                    str(replacement.get("applicationKey") or f"{registration.sourceId}:prevent-damage:{registration.targetId}"),
                    {**event, "amount": 0},
                    consumeRegistrationId=registration.id if replacement.get("consumeOnApply") is not False else None,
                )
            )
        if replacement.get("type") == "zone-destination":
            if event_kind != "zone-change" or event.get("toZone") != replacement.get("toZone"):
                continue
            if registration.targetId is not None and event.get("cardId") != registration.targetId:
                continue
            from_zones = replacement.get("fromZones")
            if isinstance(from_zones, (list, tuple)) and from_zones and event.get("fromZone") not in from_zones:
                continue
            candidates.append(
                ReplacementCandidate(
                    registration.id,
                    str(replacement.get("applicationKey") or f"{registration.sourceId}:zone-destination:{registration.targetId}"),
                    {
                        **event,
                        "toZone": replacement.get("replacementZone"),
                        "position": replacement.get("replacementPosition"),
                    },
                    consumeRegistrationId=registration.id if replacement.get("consumeOnApply") is not False else None,
                )
            )
    return tuple(candidates)


def _consume_candidate(state: MatchState, candidate: ReplacementCandidate) -> MatchState:
    next_state = state
    if candidate.consumeRegistrationId:
        registrations = tuple(
            registration
            for registration in next_state.G.replacementEffects.registrations
            if not (isinstance(registration, ReplacementRegistration) and registration.id == candidate.consumeRegistrationId)
        )
        replacement_state = replace(
            next_state.G.replacementEffects,
            registrations=registrations,
            byEventKind=_rebuild_by_event_kind(registrations),
        )
        next_state = MatchState(G=next_state.G.with_updates(replacementEffects=replacement_state), ctx=next_state.ctx)
    if candidate.consumeUsageKey is not None:
        next_state = _increment_usage(next_state, candidate.consumeUsageKey[0], candidate.consumeUsageKey[1])
    return next_state


def apply_replacement_effects(
    target: MatchState | object,
    event: Mapping[str, object],
) -> dict[str, object]:
    state = _state_of(target)
    current_event = dict(event)
    applied: set[str] = set()
    current_state = state

    for _ in range(MAX_REPLACEMENT_PASSES):
        candidates = (
            _printed_replacement_candidates(target, current_state, current_event)
            + _registered_replacement_candidates(current_state, current_event)
        )
        candidates = tuple(candidate for candidate in candidates if candidate.id not in applied)
        if not candidates:
            _write_state(target, current_state)
            return current_event
        chosen = candidates[0]
        applied.add(chosen.id)
        current_event = dict(chosen.event)
        current_state = _consume_candidate(current_state, chosen)

    raise RuntimeError(f"Exceeded {MAX_REPLACEMENT_PASSES} replacement passes while resolving event {event.get('eventId')!r}")


def preview_replacement_effects(
    target: MatchState | object,
    event: Mapping[str, object],
) -> dict[str, object]:
    state = _state_of(target)
    current_event = dict(event)
    applied: set[str] = set()
    for _ in range(MAX_REPLACEMENT_PASSES):
        candidates = (
            _printed_replacement_candidates(target, state, current_event)
            + _registered_replacement_candidates(state, current_event)
        )
        candidates = tuple(candidate for candidate in candidates if candidate.id not in applied)
        if not candidates:
            return current_event
        chosen = candidates[0]
        applied.add(chosen.id)
        current_event = dict(chosen.event)
    raise RuntimeError(f"Exceeded {MAX_REPLACEMENT_PASSES} replacement passes while previewing event {event.get('eventId')!r}")


def prune_expired_replacement_effects(
    target: MatchState | object,
    current_turn: int,
) -> MatchState:
    state = _state_of(target)
    registrations = tuple(
        registration
        for registration in state.G.replacementEffects.registrations
        if not (isinstance(registration, ReplacementRegistration) and is_effect_expired(registration, current_turn))
    )
    per_turn = {
        key: value
        for key, value in state.G.replacementEffects.usageLedger.perTurn.items()
        if key.split(":", 1)[0].isdigit() and int(key.split(":", 1)[0]) >= current_turn - 1
    }
    replacement_state = replace(
        state.G.replacementEffects,
        registrations=registrations,
        usageLedger=ReplacementUsageLedger(perTurn=per_turn),
        byEventKind=_rebuild_by_event_kind(registrations),
    )
    next_state = MatchState(G=state.G.with_updates(replacementEffects=replacement_state), ctx=state.ctx)
    return _write_state(target, next_state)


__all__ = [
    "ReplacementEffectsState",
    "ReplacementRegistration",
    "apply_replacement_effects",
    "preview_replacement_effects",
    "prune_expired_replacement_effects",
    "register_replacement_effect",
]

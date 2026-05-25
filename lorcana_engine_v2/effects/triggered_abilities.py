from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from lorcana_engine_v2.cards.models import CardDefinition, SourceAbility
from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import (
    BagState,
    MatchState,
    TriggeredAbilitiesState,
    TriggeredAbilitiesUsageLedger,
)
from lorcana_engine_v2.core.zones import ZoneId, base_zone_from_key
from lorcana_engine_v2.resolution.action_effect_types import (
    ActionResolutionInput,
    BagItem,
    PendingActionEffect,
)
from lorcana_engine_v2.resolution.pending import _state_of, _write_state


TriggerWindow = str


def _normalize_event(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    match raw:
        case "ink" | "inkwell" | "put-into-inkwell" | "add-to-inkwell":
            return "ink"
        case "start-turn" | "start-of-turn":
            return "start-turn"
        case "end-turn" | "end-of-turn":
            return "end-turn"
        case _:
            return raw


def _expanded_events(raw: object) -> tuple[str, ...]:
    if raw == "leave-play":
        return ("banish", "banish-in-challenge", "return-to-hand", "ink")
    normalized = _normalize_event(raw)
    return (normalized,) if normalized else ()


def _event_get(event: object, key: str, default: object = None) -> object:
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _event_to_dict(event: Mapping[str, object]) -> dict[str, object]:
    return dict(event)


def _zone_for_card(state: MatchState, card_id: InstanceId | str) -> str | None:
    entry = state.ctx.zones.private.cardIndex.get(InstanceId(str(card_id)))
    if entry is None:
        return None
    return str(base_zone_from_key(entry.zoneKey))


def _owner_for_card(state: MatchState, card_id: InstanceId | str | None) -> PlayerId | None:
    if card_id is None:
        return None
    entry = state.ctx.zones.private.cardIndex.get(InstanceId(str(card_id)))
    return entry.ownerID if entry is not None else None


def _definition_for_card(target: MatchState | object, card_id: InstanceId | str | None) -> CardDefinition | None:
    if card_id is None:
        return None
    cards = getattr(target, "cards", None)
    if cards is not None:
        try:
            return cards.getDefinition(card_id)
        except Exception:
            return None
    resources = getattr(target, "resources", None)
    if resources is not None:
        try:
            return resources.cards.get(str(resources.instances.require(InstanceId(str(card_id))).definition_id))
        except Exception:
            return None
    return None


def _definition_from_state_resources(
    state: MatchState,
    resources: object | None,
    card_id: InstanceId | str,
) -> CardDefinition | None:
    if resources is None:
        return None
    try:
        record = resources.instances.require(InstanceId(str(card_id)))
        return resources.cards.get(str(record.definition_id))
    except Exception:
        return None


def _definition(target: MatchState | object, state: MatchState, card_id: InstanceId | str) -> CardDefinition | None:
    found = _definition_for_card(target, card_id)
    if found is not None:
        return found
    query = getattr(getattr(target, "cards", None), "_query", None)
    return _definition_from_state_resources(state, getattr(query, "resources", None), card_id)


def _card_type(definition: CardDefinition | None) -> str | None:
    return definition.card_type if definition is not None else None


def _card_played_payload(
    state: MatchState,
    definition: CardDefinition,
    card_id: InstanceId,
) -> dict[str, object]:
    owner = _owner_for_card(state, card_id)
    return {
        "playerId": owner,
        "cardId": card_id,
        "cardType": definition.card_type,
        "costType": "free",
    }


def _candidate_from_ability(
    state: MatchState,
    definition: CardDefinition,
    card_id: InstanceId,
    ability: SourceAbility,
    ability_index: int,
) -> dict[str, object] | None:
    if ability.kind != "triggered":
        return None
    owner = _owner_for_card(state, card_id)
    if owner is None:
        return None
    raw = ability.raw
    trigger = raw.get("trigger")
    effect = raw.get("effect")
    if not isinstance(trigger, Mapping) or effect is None:
        return None
    return {
        "abilityId": ability.id or f"{card_id}:printed-trigger:{ability_index}",
        "abilityIndex": ability_index,
        "controllerId": owner,
        "sourceId": card_id,
        "cardPlayed": _card_played_payload(state, definition, card_id),
        "ability": {
            "id": ability.id,
            "name": ability.name,
            "trigger": dict(trigger),
            "sourceZones": tuple(ability.source_zones or raw.get("sourceZones", ()) or ("play",)),
            "condition": raw.get("condition"),
            "effect": effect,
            "autoResolve": raw.get("autoResolve") is True,
        },
        "resolutionInput": {},
    }


def collect_printed_trigger_candidates(
    target: MatchState | object,
    *,
    resources: object | None = None,
    zones: Sequence[str] = ("play", "hand", "discard", "inkwell"),
) -> tuple[dict[str, object], ...]:
    state = _state_of(target)
    candidates: list[dict[str, object]] = []
    for card_id, entry in state.ctx.zones.private.cardIndex.items():
        zone = str(base_zone_from_key(entry.zoneKey))
        if zone not in zones:
            continue
        definition = _definition(target, state, card_id)
        if definition is None and resources is not None:
            definition = _definition_from_state_resources(state, resources, card_id)
        if definition is None:
            continue
        for index, ability in enumerate(definition.abilities):
            candidate = _candidate_from_ability(state, definition, card_id, ability, index)
            if candidate is None:
                continue
            source_zones = candidate["ability"].get("sourceZones")  # type: ignore[index]
            if source_zones and zone not in tuple(str(item) for item in source_zones):  # type: ignore[arg-type]
                continue
            candidates.append(candidate)
    return tuple(candidates)


def snapshot_triggered_candidates_for_card(
    target: MatchState | object,
    source_id: InstanceId | str,
    *,
    resources: object | None = None,
) -> tuple[dict[str, object], ...]:
    state = _state_of(target)
    card_id = InstanceId(str(source_id))
    definition = _definition(target, state, card_id)
    if definition is None and resources is not None:
        definition = _definition_from_state_resources(state, resources, card_id)
    if definition is None:
        return ()
    zone = _zone_for_card(state, card_id)
    if zone is None:
        return ()
    candidates: list[dict[str, object]] = []
    for index, ability in enumerate(definition.abilities):
        candidate = _candidate_from_ability(state, definition, card_id, ability, index)
        if candidate is None:
            continue
        source_zones = candidate["ability"].get("sourceZones")  # type: ignore[index]
        if source_zones and zone not in tuple(str(item) for item in source_zones):  # type: ignore[arg-type]
            continue
        candidates.append(candidate)
    return tuple(candidates)


def snapshot_board_trigger_candidates(
    target: MatchState | object,
    *,
    resources: object | None = None,
) -> tuple[dict[str, object], ...]:
    return collect_printed_trigger_candidates(target, resources=resources)


def _trigger_supported_events(trigger: Mapping[str, object]) -> tuple[str, ...]:
    supported: list[str] = []
    supported.extend(_expanded_events(trigger.get("event")))
    events = trigger.get("events")
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes, bytearray)):
        for entry in events:
            supported.extend(_expanded_events(entry.get("event") if isinstance(entry, Mapping) else entry))
    return tuple(dict.fromkeys(supported))


def _subject_matches(
    target: MatchState | object,
    state: MatchState,
    candidate: Mapping[str, object],
    event: Mapping[str, object],
    subject: object,
) -> bool:
    subject_card_id = event.get("subjectCardId")
    source_id = candidate.get("sourceId")
    controller = PlayerId(str(candidate.get("controllerId")))
    owner = _owner_for_card(state, InstanceId(str(subject_card_id))) if subject_card_id else None
    definition = _definition(target, state, InstanceId(str(subject_card_id))) if subject_card_id else None
    card_type = _card_type(definition)

    if subject is None:
        return True
    if isinstance(subject, Mapping):
        if subject.get("excludeSelf") and subject_card_id == source_id:
            return False
        if subject.get("controller") == "you" and owner != controller:
            return False
        if subject.get("controller") == "opponent" and owner == controller:
            return False
        requested_type = subject.get("cardType", subject.get("cardTypes"))
        if requested_type:
            requested = tuple(requested_type) if isinstance(requested_type, (list, tuple)) else (requested_type,)
            if card_type not in tuple(str(item) for item in requested):
                return False
        classification = subject.get("classification")
        if classification and (definition is None or str(classification) not in definition.classifications):
            return False
        return True

    normalized = str(subject)
    if normalized == "SELF":
        return subject_card_id == source_id
    if normalized == "YOUR_CHARACTERS":
        return owner == controller and card_type == "character"
    if normalized == "YOUR_OTHER_CHARACTERS":
        return owner == controller and card_type == "character" and subject_card_id != source_id
    if normalized in {"OPPONENT_CHARACTERS", "OPPOSING_CHARACTERS"}:
        return owner is not None and owner != controller and card_type == "character"
    if normalized == "OTHER_CHARACTERS":
        return card_type == "character" and subject_card_id != source_id
    if normalized == "ANY_CHARACTER":
        return card_type == "character"
    if normalized == "YOUR_ITEMS":
        return owner == controller and card_type == "item"
    if normalized == "ANY_ITEM":
        return card_type == "item"
    if normalized == "YOUR_LOCATIONS":
        return owner == controller and card_type == "location"
    if normalized in {"YOU", "CONTROLLER"}:
        return event.get("playerId") == controller
    if normalized == "OPPONENT":
        return event.get("playerId") is not None and event.get("playerId") != controller
    if normalized == "ANY_PLAYER":
        return event.get("playerId") is not None
    return False


def _restriction_matches(
    state: MatchState,
    candidate: Mapping[str, object],
    trigger: Mapping[str, object],
) -> bool:
    restrictions = trigger.get("restrictions", ())
    if not isinstance(restrictions, Sequence) or isinstance(restrictions, (str, bytes, bytearray)):
        return True
    controller = PlayerId(str(candidate.get("controllerId")))
    turn_player = state.ctx.status.turnOwnerId or state.ctx.priority.holder
    for restriction in restrictions:
        if not isinstance(restriction, Mapping):
            return False
        if restriction.get("type") == "during-turn":
            whose = restriction.get("whose")
            if whose == "your" and turn_player != controller:
                return False
            if whose == "opponent" and turn_player == controller:
                return False
    return True


def _trigger_matches_event(
    target: MatchState | object,
    state: MatchState,
    candidate: Mapping[str, object],
    event: Mapping[str, object],
) -> bool:
    ability = candidate.get("ability")
    if not isinstance(ability, Mapping):
        return False
    trigger = ability.get("trigger")
    if not isinstance(trigger, Mapping):
        return False
    event_name = _normalize_event(event.get("event"))
    if event_name is None or event_name not in _trigger_supported_events(trigger):
        return False
    if not _subject_matches(target, state, candidate, event, trigger.get("on")):
        return False
    return _restriction_matches(state, candidate, trigger)


def _usage_key(turn: int, source_id: object, ability_id: object) -> str:
    return f"{turn}:{source_id}:{ability_id}"


def _record_occurrence(
    state: MatchState,
    source_id: InstanceId,
    ability_id: str,
) -> tuple[MatchState, str, int]:
    turn = state.ctx.status.turn or 1
    ability_key = _usage_key(turn, source_id, ability_id)
    occurrences = dict(state.G.triggeredAbilities.usageLedger.occurrences)
    occurrence_index = int(occurrences.get(ability_key, 0)) + 1
    occurrences[ability_key] = occurrence_index
    ledger = replace(state.G.triggeredAbilities.usageLedger, occurrences=occurrences)
    triggered = replace(state.G.triggeredAbilities, usageLedger=ledger)
    return MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx), ability_key, occurrence_index


def _enqueue_bag_item(state: MatchState, item: BagItem) -> MatchState:
    bag = state.G.triggeredAbilities.bag
    next_bag = replace(bag, nextSeq=bag.nextSeq + 1, items=tuple(bag.items) + (item,))
    triggered = replace(state.G.triggeredAbilities, bag=next_bag)
    return MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)


def _build_resolution_input(
    candidate: Mapping[str, object],
    event: Mapping[str, object],
) -> ActionResolutionInput:
    base = ActionResolutionInput.from_value(candidate.get("resolutionInput"))
    event_snapshot = {
        **dict(base.eventSnapshot),
        "subjectCardId": event.get("subjectCardId"),
        "triggerSourceCardId": event.get("triggerSourceCardId"),
        "attackerId": event.get("attackerId"),
        "defenderId": event.get("defenderId"),
        "fromZone": event.get("fromZone"),
        "toZone": event.get("toZone"),
    }
    trigger_context = {
        "playerId": event.get("playerId"),
        "subjectCardId": event.get("subjectCardId"),
        "triggerSourceCardId": event.get("triggerSourceCardId"),
        "attackerId": event.get("attackerId"),
        "defenderId": event.get("defenderId"),
    }
    return replace(base, eventSnapshot=event_snapshot, triggerContext=trigger_context)


def record_event(
    target: MatchState | object,
    input: Mapping[str, object],
) -> MatchState:
    state = _state_of(target)
    event_name = _normalize_event(input.get("event"))
    if event_name is None:
        return state
    event_id = f"trigger-event:{state.ctx._stateID}:{event_name}:{len(state.G.triggeredAbilities.pendingEvents) + 1}"
    entry = {"id": event_id, **_event_to_dict(input), "event": event_name}
    triggered = replace(
        state.G.triggeredAbilities,
        pendingEvents=tuple(state.G.triggeredAbilities.pendingEvents) + (entry,),
    )
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state)


def open_window(
    target: MatchState | object,
    *,
    window: TriggerWindow,
    playerId: PlayerId | str | None = None,
    events: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> MatchState:
    state = _state_of(target)
    if window == "start-of-turn" and playerId is not None:
        state = record_event(state, {"event": "start-turn", "playerId": PlayerId(str(playerId))})
    if window == "end-of-turn" and playerId is not None:
        state = record_event(state, {"event": "end-turn", "playerId": PlayerId(str(playerId))})
    if events is None:
        return _write_state(target, state)
    entries = events if isinstance(events, Sequence) and not isinstance(events, Mapping) else (events,)
    for event in entries:
        if isinstance(event, Mapping):
            state = record_event(state, event)
    return _write_state(target, state)


def emit_triggered_lorcana_event(
    target: MatchState | object,
    custom_type: str,
    data: Mapping[str, object],
    triggered_event: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
) -> MatchState:
    framework = getattr(target, "framework", None)
    events_api = getattr(framework, "events", None)
    if events_api is not None and hasattr(events_api, "emit"):
        events_api.emit(GameEvent(kind=custom_type, payload=dict(data)))

    state = _state_of(target)
    if triggered_event is None:
        return state
    entries = (
        triggered_event
        if isinstance(triggered_event, Sequence) and not isinstance(triggered_event, Mapping)
        else (triggered_event,)
    )
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        payload = dict(entry)
        if custom_type == "cardPlayed":
            payload["cardPlayed"] = dict(data)
        state = record_event(state, payload)
    return _write_state(target, state)


def finalize_resolution_boundary(
    target: MatchState | object,
    *,
    resources: object | None = None,
    playerId: PlayerId | str | None = None,
    window: TriggerWindow | None = None,
) -> MatchState:
    state = _state_of(target)
    events = tuple(state.G.triggeredAbilities.pendingEvents)
    triggered = replace(state.G.triggeredAbilities, pendingEvents=())
    state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    _write_state(target, state)
    board_candidates = collect_printed_trigger_candidates(target, resources=resources)

    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            continue
        event_candidates = raw_event.get("triggerCandidates", ())
        candidates: list[Mapping[str, object]] = []
        if isinstance(event_candidates, Sequence) and not isinstance(event_candidates, (str, bytes, bytearray)):
            candidates.extend(candidate for candidate in event_candidates if isinstance(candidate, Mapping))
        candidates.extend(board_candidates)

        seen: set[str] = set()
        for candidate in candidates:
            key = f"{candidate.get('sourceId')}:{candidate.get('controllerId')}:{candidate.get('abilityId')}"
            if key in seen:
                continue
            seen.add(key)
            if not _trigger_matches_event(target, state, candidate, raw_event):
                continue
            ability = candidate.get("ability")
            if not isinstance(ability, Mapping):
                continue
            source_id = InstanceId(str(candidate.get("sourceId")))
            ability_id = str(candidate.get("abilityId"))
            state, ability_key, occurrence_index = _record_occurrence(state, source_id, ability_id)
            bag = state.G.triggeredAbilities.bag
            item = BagItem.create(
                id=f"bag:{state.ctx._stateID}:{bag.nextSeq}",
                abilityId=ability_id,
                abilityIndex=candidate.get("abilityIndex") if isinstance(candidate.get("abilityIndex"), int) else None,
                abilityKey=ability_key,
                abilityName=ability.get("name") if isinstance(ability.get("name"), str) else None,
                autoResolve=ability.get("autoResolve") is True,
                controllerId=PlayerId(str(candidate.get("controllerId"))),
                chooserId=PlayerId(str(candidate.get("controllerId"))),
                sourceId=source_id,
                cardPlayed=candidate.get("cardPlayed") if isinstance(candidate.get("cardPlayed"), Mapping) else {},
                trigger=ability.get("trigger") if isinstance(ability.get("trigger"), Mapping) else {},
                condition=ability.get("condition"),
                effect=ability.get("effect"),
                occurrenceIndex=occurrence_index,
                resolutionInput=_build_resolution_input(candidate, raw_event),
            )
            state = _enqueue_bag_item(state, item)

    next_resolver = get_next_bag_resolver(state)
    if next_resolver is not None:
        state = MatchState(
            G=state.G,
            ctx=state.ctx.with_updates(
                priority=state.ctx.priority.with_updates(holder=next_resolver)
            ),
        )
    return _write_state(target, state)


def can_resolve_bag_effect_by_restrictions(
    state_or_context: MatchState | object,
    bag_effect: BagItem,
) -> bool:
    restrictions = bag_effect.trigger.get("restrictions", ())
    if not isinstance(restrictions, Sequence) or isinstance(restrictions, (str, bytes, bytearray)):
        return True
    resolutions = _state_of(state_or_context).G.triggeredAbilities.usageLedger.resolutions
    if any(isinstance(r, Mapping) and r.get("type") in {"once-per-turn", "first-time-each-turn"} for r in restrictions):
        return int(resolutions.get(bag_effect.abilityKey, 0)) <= 0
    for restriction in restrictions:
        if isinstance(restriction, Mapping) and restriction.get("type") == "n-times-per-turn":
            count = int(restriction.get("count", 0))
            if count > 0 and int(resolutions.get(bag_effect.abilityKey, 0)) >= count:
                return False
    return True


def record_bag_effect_resolution(
    target: MatchState | object,
    bag_effect: BagItem,
) -> MatchState:
    state = _state_of(target)
    restrictions = bag_effect.trigger.get("restrictions", ())
    should_record = any(
        isinstance(restriction, Mapping)
        and restriction.get("type") in {"once-per-turn", "first-time-each-turn", "n-times-per-turn", "once-per-song"}
        for restriction in restrictions
    ) if isinstance(restrictions, Sequence) and not isinstance(restrictions, (str, bytes, bytearray)) else False
    if not should_record:
        return state
    resolutions = dict(state.G.triggeredAbilities.usageLedger.resolutions)
    resolutions[bag_effect.abilityKey] = int(resolutions.get(bag_effect.abilityKey, 0)) + 1
    ledger = replace(state.G.triggeredAbilities.usageLedger, resolutions=resolutions)
    triggered = replace(state.G.triggeredAbilities, usageLedger=ledger)
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state)


def get_next_bag_resolver(state_or_context: MatchState | object) -> PlayerId | None:
    state = _state_of(state_or_context)
    items = tuple(item for item in state.G.triggeredAbilities.bag.items if isinstance(item, BagItem))
    if not items:
        return None
    last = state.G.triggeredAbilities.bag.lastResolvedPlayerId
    if last is not None and any(item.controllerId == last for item in items):
        return last
    order = state.ctx.playerIds
    start = last or state.ctx.priority.holder or (order[0] if order else None)
    if start is None or not order:
        return items[0].controllerId
    start_index = max(0, order.index(start) if start in order else 0)
    for offset in range(len(order)):
        candidate = order[(start_index + offset) % len(order)]
        if any(item.controllerId == candidate for item in items):
            return candidate
    return None


def get_bag_items_for_current_resolver(state_or_context: MatchState | object) -> tuple[BagItem, ...]:
    resolver = get_next_bag_resolver(state_or_context)
    if resolver is None:
        return ()
    state = _state_of(state_or_context)
    return tuple(
        item for item in state.G.triggeredAbilities.bag.items if isinstance(item, BagItem) and item.controllerId == resolver
    )


def has_pending_bag_items(state_or_context: MatchState | object) -> bool:
    return bool(_state_of(state_or_context).G.triggeredAbilities.bag.items)


def remove_bag_effect(
    target: MatchState | object,
    bag_id: str,
) -> tuple[MatchState, BagItem | None]:
    state = _state_of(target)
    matched = next(
        (item for item in state.G.triggeredAbilities.bag.items if isinstance(item, BagItem) and item.id == bag_id),
        None,
    )
    if matched is None:
        return state, None
    remaining = tuple(
        item for item in state.G.triggeredAbilities.bag.items if not (isinstance(item, BagItem) and item.id == bag_id)
    )
    bag = replace(
        state.G.triggeredAbilities.bag,
        items=remaining,
        lastResolvedPlayerId=None if not remaining else state.G.triggeredAbilities.bag.lastResolvedPlayerId,
    )
    triggered = replace(state.G.triggeredAbilities, bag=bag)
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state), matched


def remove_bag_item_matching_pending_source(
    target: MatchState | object,
    pending: PendingActionEffect,
) -> MatchState:
    state = _state_of(target)
    remaining = tuple(
        item
        for item in state.G.triggeredAbilities.bag.items
        if not (
            isinstance(item, BagItem)
            and item.sourceId == pending.sourceCardId
            and (pending.abilityIndex is None or item.abilityIndex == pending.abilityIndex)
        )
    )
    bag = replace(
        state.G.triggeredAbilities.bag,
        items=remaining,
        lastResolvedPlayerId=None if not remaining else state.G.triggeredAbilities.bag.lastResolvedPlayerId,
    )
    triggered = replace(state.G.triggeredAbilities, bag=bag)
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state)


def update_bag_effect_resolution_input(
    target: MatchState | object,
    bag_id: str,
    partial_input: Mapping[str, object],
) -> MatchState:
    state = _state_of(target)
    items: list[object] = []
    for item in state.G.triggeredAbilities.bag.items:
        if isinstance(item, BagItem) and item.id == bag_id:
            items.append(replace(item, resolutionInput=item.resolutionInput.merge(partial_input)))
        else:
            items.append(item)
    bag = replace(state.G.triggeredAbilities.bag, items=tuple(items))
    triggered = replace(state.G.triggeredAbilities, bag=bag)
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state)


def set_last_bag_resolver(target: MatchState | object, player_id: PlayerId | str) -> MatchState:
    state = _state_of(target)
    bag = replace(state.G.triggeredAbilities.bag, lastResolvedPlayerId=PlayerId(str(player_id)))
    triggered = replace(state.G.triggeredAbilities, bag=bag)
    next_state = MatchState(G=state.G.with_updates(triggeredAbilities=triggered), ctx=state.ctx)
    return _write_state(target, next_state)


queue_triggered_event = record_event
flush_triggered_events_to_bag = finalize_resolution_boundary


__all__ = [
    "BagItem",
    "TriggeredAbilitiesState",
    "can_resolve_bag_effect_by_restrictions",
    "collect_printed_trigger_candidates",
    "emit_triggered_lorcana_event",
    "finalize_resolution_boundary",
    "flush_triggered_events_to_bag",
    "get_bag_items_for_current_resolver",
    "get_next_bag_resolver",
    "has_pending_bag_items",
    "open_window",
    "queue_triggered_event",
    "record_bag_effect_resolution",
    "record_event",
    "remove_bag_effect",
    "remove_bag_item_matching_pending_source",
    "set_last_bag_resolver",
    "snapshot_board_trigger_candidates",
    "snapshot_triggered_candidates_for_card",
    "update_bag_effect_resolution_input",
]

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.turn_owner import resolve_turn_owner_id
from lorcana_engine_v2.core.zones import (
    CardMeta,
    ZoneRef,
    ZoneRuntimePrivateState,
    ZoneRuntimeState,
    base_zone_from_key,
    move_card_to_zone,
    patch_card_meta,
    scoped_zone,
)
from lorcana_engine_v2.effects.replacement_effects import apply_replacement_effects, register_replacement_effect
from lorcana_engine_v2.effects.continuous_effects import add_stat_modifier_effect
from lorcana_engine_v2.effects.play_from_under_permissions import add_play_from_under_permission
from lorcana_engine_v2.effects.temporary_effects import (
    add_temporary_keyword,
    add_temporary_lost_keyword,
    add_temporary_restriction,
    resolve_temporary_effect_window,
)
from lorcana_engine_v2.effects.triggered_abilities import emit_triggered_lorcana_event
from lorcana_engine_v2.resolution.action_effect_types import (
    ActionResolutionInput,
    PendingResolutionResult,
)
from lorcana_engine_v2.resolution.pending import (
    _state_of,
    _write_state,
    create_pending_action_effect,
    enqueue_pending_action_effect,
)
from lorcana_engine_v2.runtime_game.turn_metrics import (
    is_discard_zone_key,
    record_banished_character_this_turn,
    record_card_drawn_this_turn,
    record_card_put_into_discard_this_turn,
    record_card_put_under_this_turn,
    record_damage_removed_this_turn,
    record_damaged_character_this_turn,
    record_discard_exit_this_turn,
)


def _as_effect_mapping(effect: object) -> Mapping[str, object] | None:
    return effect if isinstance(effect, Mapping) else None


def _card_played_player_id(card_played: Mapping[str, object]) -> PlayerId:
    return PlayerId(str(card_played.get("playerId", "")))


def _card_played_card_id(card_played: Mapping[str, object]) -> InstanceId:
    return InstanceId(str(card_played.get("cardId", "")))


def _targets_from_input(resolution_input: ActionResolutionInput) -> tuple[str, ...]:
    value = resolution_input.currentTargets if resolution_input.currentTargets is not None else resolution_input.targets
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value if isinstance(item, str) and item)
    return ()


def _selected_card_ids(resolution_input: ActionResolutionInput) -> tuple[InstanceId, ...]:
    return tuple(InstanceId(item) for item in _targets_from_input(resolution_input))


def resolve_variable_amount(amount: object, default: int = 0, *, all_value: int = 10**9) -> int:
    if amount is None:
        return max(0, default)
    if isinstance(amount, bool):
        return int(amount)
    if isinstance(amount, int):
        return max(0, amount)
    if isinstance(amount, float):
        return max(0, int(amount))
    if isinstance(amount, str):
        normalized = amount.strip().lower()
        if normalized == "all":
            return all_value
        if normalized.lstrip("-").isdigit():
            return max(0, int(normalized))
    if isinstance(amount, Mapping):
        kind = amount.get("type")
        if kind in {"fixed", "number", "up-to"}:
            return resolve_variable_amount(amount.get("value", amount.get("amount")), default, all_value=all_value)
        if kind == "trigger-amount":
            snapshot = amount.get("eventSnapshot")
            if isinstance(snapshot, Mapping):
                return resolve_variable_amount(snapshot.get("triggerAmount"), default, all_value=all_value)
    return max(0, default)


def _effect_requires_target_selection(effect: Mapping[str, object]) -> bool:
    target = effect.get("target")
    if isinstance(target, Mapping):
        return target.get("selector") == "chosen"
    if not isinstance(target, str):
        return False
    normalized = target.upper()
    if normalized in {
        "SELF",
        "SOURCE",
        "YOU",
        "CONTROLLER",
        "OPPONENT",
        "EACH_OPPONENT",
        "ALL_PLAYERS",
        "EACH_PLAYER",
        "ANY_PLAYER",
        "CURRENT_TURN",
    }:
        return False
    return "CHOSEN" in normalized or "TARGET" in normalized


def _definition(target: MatchState | object, state: MatchState, card_id: InstanceId):
    cards = getattr(target, "cards", None)
    if cards is not None:
        try:
            return cards.require(card_id).definition
        except Exception:
            return None
    resources = getattr(target, "resources", None)
    if resources is None:
        return None
    record = resources.instances.get(card_id)
    return resources.cards.get(record.definition_id) if record is not None else None


def _card_type(target: MatchState | object, state: MatchState, card_id: InstanceId) -> str | None:
    definition = _definition(target, state, card_id)
    return getattr(definition, "card_type", None)


def _card_cost(target: MatchState | object, state: MatchState, card_id: InstanceId) -> int | None:
    definition = _definition(target, state, card_id)
    cost = getattr(definition, "cost", None)
    return int(cost) if isinstance(cost, int) else None


def _all_cards_in_base_zone(state: MatchState, zone: str = "play") -> tuple[InstanceId, ...]:
    ids: list[InstanceId] = []
    for zone_key, card_ids in state.ctx.zones.private.zoneCards.items():
        if str(base_zone_from_key(zone_key)) == zone:
            ids.extend(card_ids)
    return tuple(ids)


def _source_card_target(card_played: Mapping[str, object]) -> tuple[InstanceId, ...]:
    card_id = _card_played_card_id(card_played)
    return (card_id,) if str(card_id) else ()


def _matches_filter(
    target: MatchState | object,
    state: MatchState,
    card_id: InstanceId,
    raw_filter: object,
) -> bool:
    if not isinstance(raw_filter, Mapping):
        return True
    card_type = raw_filter.get("cardType")
    if isinstance(card_type, str) and _card_type(target, state, card_id) != card_type:
        return False
    max_cost = raw_filter.get("maxCost")
    if isinstance(max_cost, int):
        cost = _card_cost(target, state, card_id)
        if cost is None or cost > max_cost:
            return False
    return True


def _candidate_cards_from_target(
    target: MatchState | object,
    card_played: Mapping[str, object],
    state: MatchState,
    controller_id: PlayerId,
    raw_target: object,
    resolution_input: ActionResolutionInput,
    *,
    default_zone: str = "play",
) -> tuple[InstanceId, ...]:
    selected = _selected_card_ids(resolution_input)
    if selected:
        return selected

    if isinstance(raw_target, Mapping):
        zones = raw_target.get("zones")
        zone_names = tuple(str(zone) for zone in zones) if isinstance(zones, Sequence) and not isinstance(zones, (str, bytes, bytearray)) else (default_zone,)
        owner = str(raw_target.get("owner") or "any")
        card_types = raw_target.get("cardTypes") or raw_target.get("card_types")
        if isinstance(card_types, str):
            card_types = (card_types,)
        elif isinstance(card_types, Sequence) and not isinstance(card_types, (str, bytes, bytearray)):
            card_types = tuple(str(item) for item in card_types)
        else:
            card_types = ()
        candidates: list[InstanceId] = []
        for zone_name in zone_names:
            for card_id in _all_cards_in_base_zone(state, zone_name):
                entry = state.ctx.zones.private.cardIndex.get(card_id)
                if entry is None:
                    continue
                if owner == "you" and entry.controllerID != controller_id:
                    continue
                if owner == "opponent" and entry.controllerID == controller_id:
                    continue
                if card_types and _card_type(target, state, card_id) not in card_types and "card" not in card_types:
                    continue
                if not _matches_filter(target, state, card_id, raw_target.get("filter")):
                    continue
                candidates.append(card_id)
        count = raw_target.get("count")
        if isinstance(count, int):
            return tuple(candidates[:count])
        return tuple(candidates)

    normalized = str(raw_target or "").upper()
    if normalized in {"SELF", "SOURCE"}:
        return _source_card_target(card_played)
    if normalized in {"ALL_CARDS", "ALL_IN_PLAY"}:
        return _all_cards_in_base_zone(state, default_zone)
    if normalized in {"ALL_CHARACTERS", "CHARACTERS"}:
        return tuple(card_id for card_id in _all_cards_in_base_zone(state, default_zone) if _card_type(target, state, card_id) == "character")
    if normalized in {"YOUR_CHARACTERS", "ALL_YOUR_CHARACTERS"}:
        return tuple(
            card_id
            for card_id in _all_cards_in_base_zone(state, default_zone)
            if state.ctx.zones.private.cardIndex[card_id].controllerID == controller_id
            and _card_type(target, state, card_id) == "character"
        )
    if normalized in {"ALL_OPPOSING_CHARACTERS", "OPPOSING_CHARACTERS"}:
        return tuple(
            card_id
            for card_id in _all_cards_in_base_zone(state, default_zone)
            if state.ctx.zones.private.cardIndex[card_id].controllerID != controller_id
            and _card_type(target, state, card_id) == "character"
        )
    return ()


def _player_targets(state: MatchState, controller_id: PlayerId, raw_target: object) -> tuple[PlayerId, ...]:
    normalized = str(raw_target or "CONTROLLER").upper()
    if normalized in {"SELF", "YOU", "CONTROLLER", "CARD_OWNER"}:
        return (controller_id,)
    if normalized == "OPPONENT":
        return tuple(player_id for player_id in state.ctx.playerIds if player_id != controller_id)[:1]
    if normalized in {"OPPONENTS", "EACH_OPPONENT"}:
        return tuple(player_id for player_id in state.ctx.playerIds if player_id != controller_id)
    if normalized in {"ALL_PLAYERS", "EACH_PLAYER", "ANY_PLAYER"}:
        return state.ctx.playerIds
    if normalized == "CURRENT_TURN":
        return (resolve_turn_owner_id(state) or controller_id,)
    return (controller_id,)


def _write_zones(target: MatchState | object, state: MatchState, zones) -> MatchState:
    return _write_state(target, MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))


def _patch_card_meta(target: MatchState | object, state: MatchState, card_id: InstanceId, meta: CardMeta) -> MatchState:
    return _write_zones(target, state, patch_card_meta(state.ctx.zones, card_id, meta))


def _clear_card_meta(zones, card_id: InstanceId):
    card_meta = dict(zones.private.cardMeta)
    card_meta.pop(card_id, None)
    return ZoneRuntimeState(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )


def _metric_target(target: MatchState | object, state: MatchState) -> MatchState | object:
    return state if isinstance(target, MatchState) else target


def _duration_window(state: MatchState, controller_id: PlayerId, card_id: InstanceId | None, duration: object):
    owner = None
    if card_id is not None:
        entry = state.ctx.zones.private.cardIndex.get(card_id)
        owner = entry.ownerID if entry is not None else None
    return resolve_temporary_effect_window(
        state.ctx.status.turn or 1,
        duration or "this-turn",
        current_player_id=controller_id,
        target_owner_id=owner,
    )


def _update_lore(target: MatchState | object, state: MatchState, player_ids: tuple[PlayerId, ...], amount: int) -> MatchState:
    lore = {PlayerId(str(player_id)): int(value) for player_id, value in state.G.lore.items()}
    for player_id in player_ids:
        replacement_event = apply_replacement_effects(
            target,
            {
                "kind": "gain-lore" if amount >= 0 else "lose-lore",
                "eventId": f"lore:{player_id}",
                "playerId": player_id,
                "amount": abs(amount),
            },
        )
        effective = int(replacement_event.get("amount", abs(amount)))
        delta = effective if amount >= 0 else -effective
        lore[player_id] = max(0, int(lore.get(player_id, 0)) + delta)
    return _write_state(target, MatchState(G=_state_of(target).G.with_updates(lore=lore), ctx=_state_of(target).ctx))


def _suspend_effect(
    target: MatchState | object,
    *,
    kind: str,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
    ability_index: int | None = None,
    continuation: object | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    chooser_id = PlayerId(str(resolution_input.chooserPlayerId or controller_id))
    pending = create_pending_action_effect(
        state,
        kind=kind,
        sourceCardId=_card_played_card_id(card_played),
        controllerId=controller_id,
        chooserId=chooser_id,
        cardPlayed=card_played,
        effect=dict(effect),
        resolutionInput=resolution_input,
        abilityIndex=ability_index,
        continuation=continuation,
    )
    next_state = enqueue_pending_action_effect(target, pending)
    return PendingResolutionResult(status="suspended", state=next_state, pendingEffect=pending, resolutionInput=resolution_input)


def resolve_composed_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
    options: Mapping[str, object] | None = None,
) -> PendingResolutionResult:
    effect_type = str(effect.get("type") or "")
    state = _state_of(target)

    if effect_type == "sequence":
        steps = effect.get("effects", effect.get("steps", ()))
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes, bytearray)):
            return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)
        for index, step in enumerate(steps):
            step_options = dict(options or {})
            remaining = tuple(steps[index + 1 :])
            if remaining:
                existing = step_options.get("continuation")
                continuation = dict(existing) if isinstance(existing, Mapping) else {}
                continuation["remainingEffects"] = remaining + tuple(continuation.get("remainingEffects", ()))
                step_options["continuation"] = continuation
            result = resolve_action_effect(target, card_played, step, resolution_input, step_options)
            if result.status == "suspended":
                return result
        return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)

    if effect_type == "conditional":
        branch = effect.get("then", effect.get("effect"))
        if not _evaluate_action_condition(target, card_played, effect.get("condition"), resolution_input):
            branch = effect.get("else", effect.get("ifFalse"))
            if branch is None:
                return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)
        return resolve_action_effect(target, card_played, branch, resolution_input, options)

    if effect_type in {"optional", "may"}:
        if resolution_input.resolveOptional is False:
            return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)
        if resolution_input.resolveOptional is None:
            return _suspend_effect(
                target,
                kind="optional-selection",
                card_played=card_played,
                effect=effect,
                resolution_input=resolution_input,
                ability_index=_ability_index(options),
                continuation=(options or {}).get("continuation") if isinstance(options, Mapping) else None,
            )
        return resolve_action_effect(target, card_played, effect.get("effect"), resolution_input, options)

    if effect_type in {"or", "choice"}:
        options_value = effect.get("options", effect.get("choices", ()))
        if not isinstance(options_value, Sequence) or isinstance(options_value, (str, bytes, bytearray)):
            return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)
        if resolution_input.choiceIndex is None:
            return _suspend_effect(
                target,
                kind="choice-selection",
                card_played=card_played,
                effect=effect,
                resolution_input=resolution_input,
                ability_index=_ability_index(options),
                continuation=(options or {}).get("continuation") if isinstance(options, Mapping) else None,
            )
        if resolution_input.choiceIndex < 0 or resolution_input.choiceIndex >= len(options_value):
            return PendingResolutionResult(status="invalid", state=state, resolutionInput=resolution_input)
        return resolve_action_effect(target, card_played, options_value[resolution_input.choiceIndex], resolution_input, options)

    if effect_type in {"for-each", "for-each-opponent"}:
        nested = effect.get("effect")
        if effect_type == "for-each-opponent":
            state = _state_of(target)
            controller_id = _card_played_player_id(card_played)
            for player_id in (candidate for candidate in state.ctx.playerIds if candidate != controller_id):
                result = resolve_action_effect(
                    target,
                    card_played,
                    nested,
                    resolution_input.merge({"currentTargets": (str(player_id),)}),
                    options,
                )
                if result.status == "suspended":
                    return result
            return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)
        controller_id = _card_played_player_id(card_played)
        targets = _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input)
        for card_id in targets:
            result = resolve_action_effect(
                target,
                card_played,
                nested,
                resolution_input.merge({"currentTargets": (str(card_id),)}),
                options,
            )
            if result.status == "suspended":
                return result
        resolution_input.eventSnapshot["triggerAmount"] = len(targets)
        return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)

    if effect_type == "count":
        controller_id = _card_played_player_id(card_played)
        targets = _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input)
        resolution_input.eventSnapshot["count"] = len(targets)
        resolution_input.eventSnapshot["triggerAmount"] = len(targets)
        nested = effect.get("effect")
        if isinstance(nested, Mapping):
            return resolve_action_effect(target, card_played, nested, resolution_input, options)
        return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)

    if effect_type == "select-target":
        return _suspend_effect(
            target,
            kind="target-selection",
            card_played=card_played,
            effect=effect,
            resolution_input=resolution_input,
            ability_index=_ability_index(options),
            continuation=(options or {}).get("continuation") if isinstance(options, Mapping) else None,
        )

    if effect_type == "pay-cost":
        return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)

    return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)


def _evaluate_action_condition(
    target: MatchState | object,
    card_played: Mapping[str, object],
    condition: object,
    resolution_input: ActionResolutionInput,
) -> bool:
    if condition is None:
        return True
    state = _state_of(target)
    if not isinstance(condition, Mapping):
        return False
    try:
        from lorcana_engine_v2.core.context import build_rules_context
        from lorcana_engine_v2.rules.condition_evaluator import ConditionContext, ConditionEvaluator

        query = getattr(getattr(target, "cards", None), "_query", None)
        resources = getattr(query, "resources", None)
        if resources is not None:
            ctx = build_rules_context(resources)
            return ConditionEvaluator().evaluate(
                state,
                ctx,
                condition,
                ConditionContext(
                    actor=_card_played_player_id(card_played),
                    source_id=_card_played_card_id(card_played),
                    event_payload={
                        "eventSnapshot": dict(resolution_input.eventSnapshot),
                        "triggerContext": dict(resolution_input.triggerContext),
                    },
                ),
            )
    except Exception:
        pass

    kind = condition.get("type") or condition.get("kind")
    if kind in {"always", "if-you-do"}:
        return True
    if kind == "not":
        return not _evaluate_action_condition(target, card_played, condition.get("condition"), resolution_input)
    if kind == "and":
        values = condition.get("conditions")
        return isinstance(values, Sequence) and all(
            _evaluate_action_condition(target, card_played, entry, resolution_input)
            for entry in values
        )
    if kind == "or":
        values = condition.get("conditions")
        return isinstance(values, Sequence) and any(
            _evaluate_action_condition(target, card_played, entry, resolution_input)
            for entry in values
        )
    if kind in {"during-turn", "turn", "your-turn"}:
        turn_owner = state.ctx.status.turnOwnerId or state.ctx.priority.holder
        whose = condition.get("whose")
        controller = _card_played_player_id(card_played)
        if whose == "opponent":
            return turn_owner is not None and turn_owner != controller
        return turn_owner == controller
    return False


def _ability_index(options: Mapping[str, object] | None) -> int | None:
    if options and isinstance(options.get("sourceAbilityIndex"), int):
        return int(options["sourceAbilityIndex"])
    return None


def resolve_draw_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    amount = resolve_variable_amount(
        resolution_input.amount if resolution_input.amount is not None else effect.get("amount"),
        0,
    )
    total_drawn = 0
    target_player_ids = _player_targets(state, controller_id, effect.get("target"))

    for player_id in target_player_ids:
        if amount <= 0:
            continue

        if hasattr(target, "framework"):
            drawn = target.framework.zones.drawCards(
                from_zone=ZoneRef(zone="deck", playerId=player_id),
                to_zone=ZoneRef(zone="hand", playerId=player_id),
                count=amount,
            )
            state = _state_of(target)
        else:
            zones = state.ctx.zones
            from_zone = scoped_zone("deck", player_id)
            to_zone = scoped_zone("hand", player_id)
            source_cards = list(reversed(zones.private.zoneCards.get(from_zone, ())))
            drawn = tuple(source_cards[: max(0, min(amount, len(source_cards)))])
            for card_id in drawn:
                zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=to_zone)
            state = _write_zones(target, state, zones)

        drawn_cards = tuple(drawn)
        total_drawn += len(drawn_cards)

        for card_id in drawn_cards:
            state = record_card_drawn_this_turn(_metric_target(target, state), player_id)
            if hasattr(target, "framework"):
                draw_count = int(
                    _state_of(target).G.turnMetadata.cardsDrawnThisTurnByPlayer.get(player_id, 0)
                )
                emit_triggered_lorcana_event(
                    target,
                    "cardsDrawn",
                    {"playerId": player_id, "amount": 1, "cardIds": (card_id,)},
                    {
                        "event": "draw",
                        "playerId": player_id,
                        "subjectCardId": card_id,
                        "triggerSourceCardId": _card_played_card_id(card_played),
                        "eventSnapshot": {"drawCountForPlayerThisTurn": draw_count},
                    },
                )

    resolution_input.eventSnapshot["drawnCount"] = int(
        resolution_input.eventSnapshot.get("drawnCount", 0)
    ) + total_drawn
    resolution_input.eventSnapshot["lastEffectPerformed"] = total_drawn > 0
    return PendingResolutionResult(status="resolved", state=_state_of(target) if not isinstance(target, MatchState) else state, resolutionInput=resolution_input)


def _discard_candidates(state: MatchState, target_player_id: PlayerId, zone: str) -> tuple[InstanceId, ...]:
    return tuple(state.ctx.zones.private.zoneCards.get(scoped_zone(zone, target_player_id), ()))


def resolve_discard_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
    options: Mapping[str, object] | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    source_zone = str(effect.get("from") or "hand")
    amount = resolve_variable_amount(effect.get("amount"), 1)
    discard_all = effect.get("amount") == "all" or effect.get("all") is True
    selected = _selected_card_ids(resolution_input)
    discarded: list[InstanceId] = []

    for target_player_id in _player_targets(state, controller_id, effect.get("target")):
        replacement = apply_replacement_effects(
            target,
            {
                "kind": "discard",
                "eventId": f"discard:{target_player_id}:{_card_played_card_id(card_played)}",
                "sourceId": _card_played_card_id(card_played),
                "controllerId": controller_id,
                "targetPlayerId": target_player_id,
                "amount": amount,
                "prevented": False,
            },
        )
        if replacement.get("prevented") is True:
            continue

        current_state = _state_of(target) if not isinstance(target, MatchState) else state
        candidates = tuple(
            card_id
            for card_id in _discard_candidates(current_state, target_player_id, source_zone)
            if card_id != _card_played_card_id(card_played)
            and _matches_filter(target if not isinstance(target, MatchState) else current_state, current_state, card_id, effect.get("filter"))
        )
        effective_amount = len(candidates) if discard_all else min(amount, len(candidates))
        selected_from_candidates = tuple(card_id for card_id in selected if card_id in candidates)

        if source_zone == "hand" and effect.get("random") is not True and len(selected_from_candidates) < effective_amount:
            chooser_id = (
                controller_id
                if effect.get("chosenBy") == "you"
                else next((player_id for player_id in state.ctx.playerIds if player_id != controller_id), target_player_id)
                if effect.get("chosenBy") == "opponent"
                else target_player_id
            )
            return _suspend_effect(
                target,
                kind="discard-choice",
                card_played=card_played,
                effect=effect,
                resolution_input=replace(resolution_input, chooserPlayerId=chooser_id),
                ability_index=_ability_index(options),
            )

        cards_to_discard = selected_from_candidates[:effective_amount] if selected_from_candidates else candidates[:effective_amount]
        zones = current_state.ctx.zones
        for card_id in cards_to_discard:
            zones = move_card_to_zone(
                zones,
                card_id=card_id,
                destination_zone_key=scoped_zone("discard", target_player_id),
            )
            discarded.append(card_id)

        state = _write_zones(_metric_target(target, current_state), current_state, zones)

        for card_id in cards_to_discard:
            state = record_card_put_into_discard_this_turn(
                _metric_target(target, state),
                target_player_id,
            )

        if hasattr(target, "framework"):
            for card_id in cards_to_discard:
                emit_triggered_lorcana_event(
                    target,
                    "cardDiscarded",
                    {"playerId": target_player_id, "cardId": card_id, "sourceId": _card_played_card_id(card_played)},
                    {
                        "event": "discard",
                        "playerId": target_player_id,
                        "subjectCardId": card_id,
                        "triggerSourceCardId": _card_played_card_id(card_played),
                    },
                )

    resolution_input.eventSnapshot["triggerAmount"] = len(discarded)
    resolution_input.eventSnapshot["lastEffectPerformed"] = bool(discarded)
    return PendingResolutionResult(
        status="resolved",
        state=_state_of(target) if not isinstance(target, MatchState) else state,
        resolutionInput=resolution_input,
    )


def resolve_banish_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    targets = _candidate_cards_from_target(
        target,
        card_played,
        state,
        controller_id,
        effect.get("target"),
        resolution_input,
    )
    banished: list[InstanceId] = []
    owner_by_card: dict[InstanceId, PlayerId] = {}
    zones = state.ctx.zones

    for card_id in targets:
        entry = zones.private.cardIndex.get(card_id)
        if entry is None:
            continue
        owner_id = entry.ownerID
        owner_by_card[card_id] = owner_id
        zones = move_card_to_zone(
            zones,
            card_id=card_id,
            destination_zone_key=scoped_zone("discard", owner_id),
        )
        zones = _clear_card_meta(zones, card_id)
        banished.append(card_id)

    state = _write_zones(target, state, zones)

    if banished:
        state = _write_state(
            _metric_target(target, state),
            MatchState(
                G=state.G.with_updates(staticEffectsVersion=state.G.staticEffectsVersion + 1),
                ctx=state.ctx,
            ),
        )
        for card_id in banished:
            owner_id = owner_by_card[card_id]
            state = record_card_put_into_discard_this_turn(_metric_target(target, state), owner_id)
            state = record_banished_character_this_turn(_metric_target(target, state), card_id)

            if hasattr(target, "framework"):
                emit_triggered_lorcana_event(
                    target,
                    "cardBanished",
                    {
                        "cardId": card_id,
                        "sourceId": _card_played_card_id(card_played),
                        "reason": "banish effect",
                    },
                    {
                        "event": "banish",
                        "playerId": owner_id,
                        "subjectCardId": card_id,
                        "triggerSourceCardId": card_id,
                    },
                )

    resolution_input.eventSnapshot["triggerAmount"] = len(banished)
    resolution_input.eventSnapshot["lastEffectPerformed"] = bool(banished)
    return PendingResolutionResult(status="resolved", state=_state_of(target) if not isinstance(target, MatchState) else state, resolutionInput=resolution_input)


def resolve_damage_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    targets = _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input)
    amount = resolve_variable_amount(resolution_input.amount if resolution_input.amount is not None else effect.get("amount"), 0)
    effect_type = str(effect.get("type"))
    damaged_any = False

    for original_target in targets:
        event = apply_replacement_effects(
            target,
            {
                "kind": effect_type,
                "eventId": f"{effect_type}:{original_target}:{_card_played_card_id(card_played)}",
                "sourceId": _card_played_card_id(card_played),
                "controllerId": controller_id,
                "targetId": original_target,
                "amount": amount,
            },
        )
        target_id = InstanceId(str(event.get("targetId", original_target)))
        effective_amount = resolve_variable_amount(event.get("amount"), 0)
        if effective_amount <= 0:
            continue

        current_state = _state_of(target) if not isinstance(target, MatchState) else state
        meta = current_state.ctx.zones.private.cardMeta.get(target_id, CardMeta())
        next_damage = int(meta.damage or 0) + effective_amount
        state = _patch_card_meta(
            _metric_target(target, current_state),
            current_state,
            target_id,
            meta.with_updates(damage=next_damage),
        )
        state = record_damaged_character_this_turn(_metric_target(target, state), target_id)
        damaged_any = True

        definition = _definition(target if not isinstance(target, MatchState) else state, state, target_id)
        willpower = getattr(definition, "willpower", None)
        card_type = getattr(definition, "card_type", None)
        if isinstance(willpower, int) and card_type in {"character", "location"} and next_damage >= willpower:
            banish_result = resolve_banish_effect(
                target if not isinstance(target, MatchState) else state,
                card_played,
                {"type": "banish", "target": "CHOSEN_CARD"},
                ActionResolutionInput(targets=(str(target_id),)),
            )
            state = banish_result.state

        if hasattr(target, "framework"):
            emit_triggered_lorcana_event(
                target,
                "damageDealt",
                {
                    "targetId": target_id,
                    "amount": effective_amount,
                    "newDamage": next_damage,
                    "sourceId": _card_played_card_id(card_played),
                    "damageType": "effect",
                },
                [
                    {"event": "damage", "subjectCardId": target_id, "triggerSourceCardId": _card_played_card_id(card_played)},
                    {"event": "deal-damage", "subjectCardId": target_id, "triggerSourceCardId": _card_played_card_id(card_played)},
                ],
            )

    resolution_input.eventSnapshot["lastEffectPerformed"] = damaged_any
    if damaged_any:
        resolution_input.eventSnapshot["triggerAmount"] = amount
    return PendingResolutionResult(status="resolved", state=_state_of(target) if not isinstance(target, MatchState) else state, resolutionInput=resolution_input)


def resolve_ready_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    changed = False
    for card_id in _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input):
        current = _state_of(target)
        meta = current.ctx.zones.private.cardMeta.get(card_id, CardMeta())
        _patch_card_meta(target, current, card_id, meta.with_updates(state="ready"))
        changed = True
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_exert_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    changed = False
    for card_id in _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input):
        current = _state_of(target)
        meta = current.ctx.zones.private.cardMeta.get(card_id, CardMeta())
        _patch_card_meta(target, current, card_id, meta.with_updates(state="exerted"))
        changed = True
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_restriction_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    restriction = str(effect.get("restriction") or "")
    changed = False
    for card_id in _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input):
        current = _state_of(target)
        meta = current.ctx.zones.private.cardMeta.get(card_id, CardMeta())
        window = _duration_window(current, controller_id, card_id, effect.get("duration"))
        meta = add_temporary_restriction(
            meta,
            restriction,
            window.expiresAtTurn,
            starts_at_turn=window.startsAtTurn,
            payload=dict(effect),
        )
        _patch_card_meta(target, current, card_id, meta)
        changed = True
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_keyword_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
    *,
    lose: bool = False,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    raw_keywords = effect.get("keywords") if "keywords" in effect else effect.get("keyword", effect.get("ability", effect.get("classification")))
    keywords = tuple(str(item) for item in raw_keywords) if isinstance(raw_keywords, Sequence) and not isinstance(raw_keywords, (str, bytes, bytearray)) else (str(raw_keywords or ""),)
    changed = False
    for card_id in _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input):
        current = _state_of(target)
        meta = current.ctx.zones.private.cardMeta.get(card_id, CardMeta())
        window = _duration_window(current, controller_id, card_id, effect.get("duration"))
        for keyword in keywords:
            if not keyword:
                continue
            raw_value = effect.get("value")
            value = int(raw_value) if isinstance(raw_value, int) else None
            if lose:
                meta = add_temporary_lost_keyword(meta, keyword, window.expiresAtTurn, starts_at_turn=window.startsAtTurn)
            else:
                meta = add_temporary_keyword(meta, keyword, window.expiresAtTurn, value=value, starts_at_turn=window.startsAtTurn, payload=effect)
        _patch_card_meta(target, current, card_id, meta)
        changed = True
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_move_card_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    effect_type = str(effect.get("type") or "")
    to_zone = str(effect.get("to") or effect.get("toZone") or ("hand" if effect_type == "return-to-hand" else "discard"))
    raw_index = effect.get("index")
    move_index = 0 if raw_index in {"bottom", "deck-bottom"} or effect_type == "put-on-bottom" else None
    moved = False
    discard_entry_owners: list[PlayerId] = []
    discard_exit_count = 0
    zones = state.ctx.zones

    for card_id in _candidate_cards_from_target(
        target,
        card_played,
        state,
        controller_id,
        effect.get("target"),
        resolution_input,
    ):
        entry = zones.private.cardIndex.get(card_id)
        if entry is None:
            continue

        from_zone = str(base_zone_from_key(entry.zoneKey))
        destination_owner = entry.ownerID if to_zone in {"hand", "deck", "discard", "inkwell", "limbo"} else entry.controllerID
        zones = move_card_to_zone(
            zones,
            card_id=card_id,
            destination_zone_key=scoped_zone(to_zone, destination_owner),
            index=move_index,
        )
        moved = True

        if is_discard_zone_key(to_zone):
            discard_entry_owners.append(destination_owner)
        if from_zone == "discard" and not is_discard_zone_key(to_zone):
            discard_exit_count += 1

    state = _write_zones(_metric_target(target, state), state, zones)

    for owner_id in discard_entry_owners:
        state = record_card_put_into_discard_this_turn(_metric_target(target, state), owner_id)
    if discard_exit_count > 0:
        state = record_discard_exit_this_turn(_metric_target(target, state), discard_exit_count)

    resolution_input.eventSnapshot["lastEffectPerformed"] = moved
    return PendingResolutionResult(
        status="resolved",
        state=_state_of(target) if not isinstance(target, MatchState) else state,
        resolutionInput=resolution_input,
    )


def resolve_put_under_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)

    raw_under = effect.get("under", "SELF")
    if isinstance(raw_under, str) and raw_under.upper() in {"SELF", "SOURCE"}:
        destination_id = _card_played_card_id(card_played)
    else:
        under_target_ids = _candidate_cards_from_target(
            target,
            card_played,
            state,
            controller_id,
            raw_under,
            ActionResolutionInput(),
        )
        destination_id = under_target_ids[0] if under_target_ids else _card_played_card_id(card_played)

    source_zone = str(effect.get("source") or effect.get("from") or "chosen")
    if source_zone == "top-of-deck":
        amount = resolve_variable_amount(effect.get("amount"), 1)
        selected = tuple(reversed(state.ctx.zones.private.zoneCards.get(scoped_zone("deck", controller_id), ())))[:amount]
    else:
        selected = _candidate_cards_from_target(
            target,
            card_played,
            state,
            controller_id,
            effect.get("target"),
            resolution_input,
        )

    zones = state.ctx.zones
    moved: list[InstanceId] = []
    for card_id in selected:
        entry = zones.private.cardIndex.get(card_id)
        if entry is None or card_id == destination_id:
            continue
        zones = move_card_to_zone(
            zones,
            card_id=card_id,
            destination_zone_key=scoped_zone("limbo", entry.ownerID),
        )
        moved.append(card_id)

    card_meta = dict(zones.private.cardMeta)
    destination_meta = card_meta.get(destination_id, CardMeta())
    cards_under = tuple(destination_meta.cardsUnder or ()) + tuple(moved)
    card_meta[destination_id] = destination_meta.with_updates(cardsUnder=cards_under or None)

    for card_id in moved:
        card_meta[card_id] = card_meta.get(card_id, CardMeta()).with_updates(stackParentId=destination_id)

    zones = ZoneRuntimeState(
        public=zones.public,
        reveals=zones.reveals,
        private=ZoneRuntimePrivateState(
            zoneCards=zones.private.zoneCards,
            cardIndex=zones.private.cardIndex,
            cardMeta=card_meta,
        ),
    )

    state = _write_zones(target, state, zones)

    for moved_id in moved:
        metric_target = state if isinstance(target, MatchState) else target
        state = record_card_put_under_this_turn(metric_target, destination_id, moved_id)

    resolution_input.eventSnapshot["cardsUnder"] = tuple(str(card_id) for card_id in moved)
    resolution_input.eventSnapshot["lastEffectPerformed"] = bool(moved)
    return PendingResolutionResult(
        status="resolved",
        state=_state_of(target) if not isinstance(target, MatchState) else state,
        resolutionInput=resolution_input,
    )


def resolve_remove_damage_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    amount = resolve_variable_amount(
        resolution_input.amount if resolution_input.amount is not None else effect.get("amount"),
        0,
    )
    changed = False
    removed_total = 0

    for card_id in _candidate_cards_from_target(
        target,
        card_played,
        state,
        controller_id,
        effect.get("target"),
        resolution_input,
    ):
        current = _state_of(target) if not isinstance(target, MatchState) else state
        meta = current.ctx.zones.private.cardMeta.get(card_id, CardMeta())
        current_damage = int(meta.damage or 0)
        remove_amount = current_damage if effect.get("amount") == "all" else min(amount, current_damage)
        event = apply_replacement_effects(
            target,
            {
                "kind": "remove-damage",
                "eventId": f"remove-damage:{card_id}:{_card_played_card_id(card_played)}",
                "sourceId": _card_played_card_id(card_played),
                "controllerId": controller_id,
                "targetId": card_id,
                "amount": remove_amount,
            },
        )
        effective = resolve_variable_amount(event.get("amount"), 0)
        if effective <= 0:
            continue

        state = _patch_card_meta(
            _metric_target(target, current),
            current,
            card_id,
            meta.with_updates(damage=max(0, current_damage - effective)),
        )
        removed_total += effective
        changed = True

    if removed_total > 0:
        state = record_damage_removed_this_turn(
            _metric_target(target, state),
            _card_played_player_id(card_played),
            removed_total,
        )

    resolution_input.eventSnapshot["healedAmount"] = removed_total
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target) if not isinstance(target, MatchState) else state, resolutionInput=resolution_input)


def resolve_move_damage_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    selected = _selected_card_ids(resolution_input)
    if len(selected) < 2:
        return _suspend_effect(
            target,
            kind="target-selection",
            card_played=card_played,
            effect=effect,
            resolution_input=resolution_input,
        )

    amount = resolve_variable_amount(effect.get("amount"), 1)
    source_id, destination_id = selected[0], selected[1]
    state = _state_of(target)
    source_meta = state.ctx.zones.private.cardMeta.get(source_id, CardMeta())
    moved = min(amount, int(source_meta.damage or 0))
    if moved <= 0:
        resolution_input.eventSnapshot["lastEffectPerformed"] = False
        return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolution_input)

    state = _patch_card_meta(
        _metric_target(target, state),
        state,
        source_id,
        source_meta.with_updates(damage=max(0, int(source_meta.damage or 0) - moved)),
    )
    state = record_damage_removed_this_turn(_metric_target(target, state), _card_played_player_id(card_played), moved)

    current = _state_of(target) if not isinstance(target, MatchState) else state
    destination_meta = current.ctx.zones.private.cardMeta.get(destination_id, CardMeta())
    new_damage = int(destination_meta.damage or 0) + moved
    state = _patch_card_meta(
        _metric_target(target, current),
        current,
        destination_id,
        destination_meta.with_updates(damage=new_damage),
    )

    destination_definition = _definition(target if not isinstance(target, MatchState) else state, state, destination_id)
    destination_willpower = getattr(destination_definition, "willpower", None)
    destination_type = getattr(destination_definition, "card_type", None) or getattr(destination_definition, "cardType", None)
    if isinstance(destination_willpower, int) and destination_willpower > 0 and new_damage >= destination_willpower and destination_type in {"character", "location"}:
        banish_result = resolve_banish_effect(
            target if not isinstance(target, MatchState) else state,
            card_played,
            {"type": "banish", "target": "CHOSEN_CARD"},
            ActionResolutionInput(targets=(str(destination_id),)),
        )
        state = banish_result.state

    resolution_input.eventSnapshot["healedAmount"] = moved
    resolution_input.eventSnapshot["lastEffectPerformed"] = True
    return PendingResolutionResult(status="resolved", state=_state_of(target) if not isinstance(target, MatchState) else state, resolutionInput=resolution_input)

def resolve_create_replacement_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    replacement = effect.get("replacement")
    if not isinstance(replacement, Mapping):
        replacement = {key: value for key, value in effect.items() if key not in {"type", "duration"}}
    next_state = register_replacement_effect(
        target,
        card_played,
        replacement,
        effect.get("duration") or "this-turn",
        resolution_input.to_mapping(),
    )
    resolution_input.eventSnapshot["lastEffectPerformed"] = True
    return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolution_input)


def resolve_reveal_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    player_ids = _player_targets(state, controller_id, effect.get("target"))
    amount = resolve_variable_amount(effect.get("amount"), 1)
    revealed: list[InstanceId] = []
    for player_id in player_ids:
        cards = tuple(reversed(_state_of(target).ctx.zones.private.zoneCards.get(scoped_zone("deck", player_id), ())))[:amount]
        revealed.extend(cards)
        if hasattr(target, "framework") and cards:
            target.framework.zones.reveal(cards, "all")
    resolution_input.eventSnapshot["revealedCardIds"] = tuple(revealed)
    resolution_input.eventSnapshot["lastEffectPerformed"] = bool(revealed)
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_scry_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
    options: Mapping[str, object] | None = None,
) -> PendingResolutionResult:
    if resolution_input.destinations is None:
        return _suspend_effect(
            target,
            kind="scry-selection",
            card_played=card_played,
            effect=effect,
            resolution_input=resolution_input,
            ability_index=_ability_index(options),
        )
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    zones = state.ctx.zones
    for destination in resolution_input.destinations:
        if not isinstance(destination, Mapping):
            continue
        zone = str(destination.get("zone") or "")
        cards = destination.get("cards")
        if not isinstance(cards, Sequence) or isinstance(cards, (str, bytes, bytearray)):
            continue
        zone_name = "deck" if zone in {"deck-top", "deck-bottom"} else zone
        index = None if zone != "deck-bottom" else 0
        for raw_card_id in cards:
            card_id = InstanceId(str(raw_card_id))
            entry = zones.private.cardIndex.get(card_id)
            owner_id = entry.ownerID if entry is not None else controller_id
            zones = move_card_to_zone(zones, card_id=card_id, destination_zone_key=scoped_zone(zone_name, owner_id), index=index)
    _write_zones(target, state, zones)
    resolution_input.eventSnapshot["lastEffectPerformed"] = True
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_additional_inkwell_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    amount = resolve_variable_amount(effect.get("amount"), 1)
    turn_metadata = replace(
        state.G.turnMetadata,
        additionalInkwellActions=state.G.turnMetadata.additionalInkwellActions + amount,
    )
    next_state = _write_state(target, MatchState(G=state.G.with_updates(turnMetadata=turn_metadata), ctx=state.ctx))
    resolution_input.eventSnapshot["lastEffectPerformed"] = amount > 0
    return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolution_input)


def resolve_cost_reduction_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    window = _duration_window(state, controller_id, None, effect.get("duration"))
    amount = resolve_variable_amount(effect.get("amount", effect.get("reduction")), 0)
    entry = {
        "amount": amount,
        "expiresAtTurn": window.expiresAtTurn,
        "startsAtTurn": window.startsAtTurn,
        "consumeOnUse": effect.get("consumeOnUse", True),
        "cardType": effect.get("cardType"),
        "classification": effect.get("classification"),
        "playMethod": effect.get("playMethod", effect.get("method")),
    }
    pending = dict(state.G.turnMetadata.pendingCostReductionsByPlayer)
    pending[controller_id] = tuple(pending.get(controller_id, ())) + (entry,)
    next_state = _write_state(
        target,
        MatchState(
            G=state.G.with_updates(
                turnMetadata=replace(state.G.turnMetadata, pendingCostReductionsByPlayer=pending)
            ),
            ctx=state.ctx,
        ),
    )
    resolution_input.eventSnapshot["lastEffectPerformed"] = amount > 0
    return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolution_input)


def resolve_modify_stat_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    amount = resolve_variable_amount(effect.get("modifier", effect.get("amount")), 0)
    stat = str(effect.get("stat") or effect.get("attribute") or "strength")
    changed = False
    for card_id in _candidate_cards_from_target(target, card_played, state, controller_id, effect.get("target"), resolution_input):
        add_stat_modifier_effect(
            target,
            source_id=_card_played_card_id(card_played),
            target_id=card_id,
            stat=stat,
            modifier=amount,
            duration=str(effect.get("duration") or "this-turn"),
            controller_id=controller_id,
        )
        changed = True
    resolution_input.eventSnapshot["lastEffectPerformed"] = changed
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_mill_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    amount = resolve_variable_amount(effect.get("amount"), 1)
    moved = 0
    moved_by_player: dict[PlayerId, int] = {}
    zones = state.ctx.zones

    for player_id in _player_targets(state, controller_id, effect.get("target")):
        cards = tuple(reversed(zones.private.zoneCards.get(scoped_zone("deck", player_id), ())))[:amount]
        for card_id in cards:
            zones = move_card_to_zone(
                zones,
                card_id=card_id,
                destination_zone_key=scoped_zone("discard", player_id),
            )
            moved += 1
            moved_by_player[player_id] = moved_by_player.get(player_id, 0) + 1

    state = _write_zones(_metric_target(target, state), state, zones)

    for player_id, count in moved_by_player.items():
        state = record_card_put_into_discard_this_turn(
            _metric_target(target, state),
            player_id,
            count,
        )

    resolution_input.eventSnapshot["triggerAmount"] = moved
    resolution_input.eventSnapshot["lastEffectPerformed"] = moved > 0
    return PendingResolutionResult(
        status="resolved",
        state=_state_of(target) if not isinstance(target, MatchState) else state,
        resolutionInput=resolution_input,
    )

def resolve_shuffle_into_deck_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    zones = state.ctx.zones
    moved = False
    discard_exit_count = 0

    for card_id in _candidate_cards_from_target(
        target,
        card_played,
        state,
        controller_id,
        effect.get("target"),
        resolution_input,
        default_zone=str(effect.get("from") or "discard"),
    ):
        entry = zones.private.cardIndex.get(card_id)
        if entry is None:
            continue

        source_zone = str(entry.zoneKey)
        deck_player_id = controller_id if effect.get("intoDeck") == "controller" else entry.ownerID
        zones = move_card_to_zone(
            zones,
            card_id=card_id,
            destination_zone_key=scoped_zone("deck", deck_player_id),
        )
        moved = True

        if is_discard_zone_key(source_zone):
            discard_exit_count += 1

    state = _write_zones(_metric_target(target, state), state, zones)

    if discard_exit_count > 0:
        state = record_discard_exit_this_turn(
            _metric_target(target, state),
            discard_exit_count,
        )

    resolution_input.eventSnapshot["lastEffectPerformed"] = moved
    return PendingResolutionResult(
        status="resolved",
        state=_state_of(target) if not isinstance(target, MatchState) else state,
        resolutionInput=resolution_input,
    )


def resolve_draw_until_hand_size_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    hand_size = resolve_variable_amount(effect.get("handSize", effect.get("amount")), 0)
    total = 0
    for player_id in _player_targets(state, controller_id, effect.get("target")):
        current_hand = len(_state_of(target).ctx.zones.private.zoneCards.get(scoped_zone("hand", player_id), ()))
        draw_amount = max(0, hand_size - current_hand)
        if draw_amount:
            result = resolve_draw_effect(target, card_played, {"type": "draw", "target": player_id, "amount": draw_amount}, resolution_input)
            total += int(result.resolutionInput.eventSnapshot.get("drawnCount", 0))
    resolution_input.eventSnapshot["lastEffectPerformed"] = total > 0
    return PendingResolutionResult(status="resolved", state=_state_of(target), resolutionInput=resolution_input)


def resolve_enable_play_from_under_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    state = _state_of(target)
    controller_id = _card_played_player_id(card_played)
    window = _duration_window(state, controller_id, _card_played_card_id(card_played), effect.get("duration") or "this-turn")
    next_state = add_play_from_under_permission(
        target,
        controller_id,
        {
            "sourceItemId": str(_card_played_card_id(card_played)),
            "expiresAtTurn": window.expiresAtTurn,
            "startsAtTurn": window.startsAtTurn,
            "cardType": effect.get("cardType"),
            "controllerId": controller_id,
        },
    )
    resolution_input.eventSnapshot["lastEffectPerformed"] = True
    return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolution_input)


def unsupported_action_effect(
    target: MatchState | object,
    effect: Mapping[str, object],
    resolution_input: ActionResolutionInput,
) -> PendingResolutionResult:
    resolution_input.eventSnapshot["unsupportedActionEffect"] = str(effect.get("type") or "")
    return PendingResolutionResult(status="unsupported", state=_state_of(target), resolutionInput=resolution_input)


def resolve_action_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: object,
    resolution_input: object | None = None,
    options: Mapping[str, object] | None = None,
) -> PendingResolutionResult:
    state = _state_of(target)
    resolved_input = ActionResolutionInput.from_value(resolution_input)
    effect_mapping = _as_effect_mapping(effect)
    if effect_mapping is None:
        return PendingResolutionResult(status="resolved", state=state, resolutionInput=resolved_input)

    effect_type = str(effect_mapping.get("type") or "")
    if effect_type in {"sequence", "conditional", "optional", "may", "or", "choice", "for-each", "for-each-opponent", "count", "select-target", "pay-cost"}:
        return resolve_composed_effect(target, card_played, effect_mapping, resolved_input, options)

    if _effect_requires_target_selection(effect_mapping) and not _targets_from_input(resolved_input):
        return _suspend_effect(
            target,
            kind="target-selection",
            card_played=card_played,
            effect=effect_mapping,
            resolution_input=resolved_input,
            ability_index=_ability_index(options),
        )

    controller_id = _card_played_player_id(card_played)
    if effect_type == "gain-lore":
        amount = resolve_variable_amount(resolved_input.amount if resolved_input.amount is not None else effect_mapping.get("amount"), 0)
        next_state = _update_lore(target, state, _player_targets(state, controller_id, effect_mapping.get("target")), amount)
        return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolved_input)
    if effect_type == "lose-lore":
        amount = resolve_variable_amount(resolved_input.amount if resolved_input.amount is not None else effect_mapping.get("amount"), 0)
        next_state = _update_lore(target, state, _player_targets(state, controller_id, effect_mapping.get("target")), -amount)
        return PendingResolutionResult(status="resolved", state=next_state, resolutionInput=resolved_input)
    if effect_type == "draw":
        return resolve_draw_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "discard":
        return resolve_discard_effect(target, card_played, effect_mapping, resolved_input, options)
    if effect_type == "banish":
        return resolve_banish_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"deal-damage", "put-damage"}:
        return resolve_damage_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "ready":
        return resolve_ready_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "exert":
        return resolve_exert_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "restriction":
        return resolve_restriction_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"gain-keyword", "gain-keywords", "grant-keyword"}:
        return resolve_keyword_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"lose-keyword", "remove-keyword"}:
        return resolve_keyword_effect(target, card_played, effect_mapping, resolved_input, lose=True)
    if effect_type in {"return-to-hand", "move-card", "put-into-discard", "put-into-inkwell", "put-on-top", "put-on-bottom", "return-from-discard", "move-to-location"}:
        if effect_type == "put-on-top":
            effect_mapping = {**effect_mapping, "to": "deck", "index": "top"}
        elif effect_type == "put-on-bottom":
            effect_mapping = {**effect_mapping, "to": "deck", "index": "bottom"}
        elif effect_type == "return-from-discard":
            effect_mapping = {**effect_mapping, "to": "hand", "target": effect_mapping.get("target", {"zones": ("discard",), "owner": "you"})}
        return resolve_move_card_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "put-under":
        return resolve_put_under_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "remove-damage":
        return resolve_remove_damage_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "move-damage":
        return resolve_move_damage_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "additional-inkwell":
        return resolve_additional_inkwell_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "cost-reduction":
        return resolve_cost_reduction_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"modify-stat", "property-modification", "support"}:
        if effect_type == "property-modification" and effect_mapping.get("property") != "singer-threshold":
            return unsupported_action_effect(target, effect_mapping, resolved_input)
        if effect_type == "support":
            effect_mapping = {**effect_mapping, "type": "modify-stat", "stat": "strength"}
        return resolve_modify_stat_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "mill":
        return resolve_mill_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "shuffle-into-deck":
        return resolve_shuffle_into_deck_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "draw-until-hand-size":
        return resolve_draw_until_hand_size_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "enable-play-from-under":
        return resolve_enable_play_from_under_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"create-replacement-effect", "replacement"}:
        return resolve_create_replacement_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type in {"reveal", "reveal-hand", "reveal-inkwell", "reveal-top-card", "reveal-until-match", "reveal-and-route"}:
        return resolve_reveal_effect(target, card_played, effect_mapping, resolved_input)
    if effect_type == "scry":
        return resolve_scry_effect(target, card_played, effect_mapping, resolved_input, options)

    return unsupported_action_effect(target, effect_mapping, resolved_input)


def resolve_effect(
    target: MatchState | object,
    card_played: Mapping[str, object],
    effect: object,
    resolution_input: object | None = None,
    options: Mapping[str, object] | None = None,
) -> PendingResolutionResult:
    return resolve_action_effect(target, card_played, effect, resolution_input, options)


__all__ = [
    "resolve_action_effect",
    "resolve_composed_effect",
    "resolve_create_replacement_effect",
    "resolve_damage_effect",
    "resolve_discard_effect",
    "resolve_draw_effect",
    "resolve_effect",
    "resolve_restriction_effect",
    "resolve_variable_amount",
    "unsupported_action_effect",
]

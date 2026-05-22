from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_bot.actions import Action
from lorcana_bot.constants import (
    ACTION_CHALLENGE,
    ACTION_CONCEDE,
    ACTION_END_TURN,
    ACTION_INK_CARD,
    ACTION_KEEP_HAND,
    ACTION_MOVE_TO_LOCATION,
    ACTION_MULLIGAN,
    ACTION_PLAY_CARD,
    ACTION_QUEST,
    ACTION_RESOLVE_BAG,
    ACTION_RESOLVE_PENDING_EFFECT,
    ACTION_USE_ABILITY,
    CARD_ACTION,
)
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState

from .candidate_validator import validate_candidate
from .candidates import AutomatedActionCandidate, AutomatedActionFamily, candidate_to_dict, make_stable_key
from .caps import AutomationSearchCaps


@dataclass
class CandidateEnumerationResult:
    candidates: list[AutomatedActionCandidate] = field(default_factory=list)
    validation_rejections: list[dict[str, Any]] = field(default_factory=list)
    unsupported_skips: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def enumerate_automated_action_candidates(
    state: GameState,
    engine: GameEngine,
    actor: int,
    caps: AutomationSearchCaps = AutomationSearchCaps(),
) -> CandidateEnumerationResult:
    result = CandidateEnumerationResult()
    legal = sorted(engine.legal_actions(state, actor), key=_action_sort_key)
    raw_candidates: list[AutomatedActionCandidate] = []

    # B7: Use engine.legal_actions() as source of truth for candidate enumeration.
    # This avoids duplication because the engine already includes RESOLVE_PENDING_EFFECT
    # and RESOLVE_BAG when those are appropriate for the actor.
    for action in legal:
        candidate = _candidate_from_action(state, engine, action)
        if candidate is not None:
            raw_candidates.append(candidate)

    _record_activated_ability_skips(state, engine, actor, result)
    raw_candidates.extend(_mulligan_structural_candidates(state, engine, actor, legal))

    by_key: dict[str, AutomatedActionCandidate] = {}
    family_counts: dict[str, int] = {}
    for candidate in sorted(raw_candidates, key=lambda c: c.stable_key):
        family_counts[candidate.family] = family_counts.get(candidate.family, 0) + 1
        if family_counts[candidate.family] > caps.max_candidates_per_family:
            result.diagnostics.append(
                {
                    "family": candidate.family,
                    "cap": "max_candidates_per_family",
                    "original_count": family_counts[candidate.family],
                    "retained_count": caps.max_candidates_per_family,
                    "reason": "candidate family cap reached",
                }
            )
            continue
        validation = validate_candidate(state, engine, candidate)
        if validation.valid:
            by_key.setdefault(candidate.stable_key, candidate)
        else:
            rejected = candidate_to_dict(candidate)
            rejected.update({"code": validation.code, "reason": validation.reason})
            result.validation_rejections.append(rejected)

    result.candidates = [by_key[key] for key in sorted(by_key)]
    return result


def _pending_effect_candidates(
    state: GameState,
    engine: GameEngine,
    actor: int,
) -> list[AutomatedActionCandidate]:
    """Generate RESOLVE_EFFECT candidates from pending effects.

    This mirrors Lorcanito's resolution enumeration for pending action effects.
    Priority ordering:
    1. Optional accept/decline choices
    2. Target selection choices
    3. Index/choice selection
    """
    from lorcana_bot.pending_effects import get_current_pending_effect, get_valid_targets_for_requirement
    from lorcana_bot.cards import EffectDef

    candidates = []
    pe = get_current_pending_effect(state, actor)
    if pe is None:
        return candidates

    # Determine effect metadata
    effect_kind = _get_effect_kind(pe)
    effect_polarity = _classify_effect_polarity(pe, actor)
    projected_benefit, projected_harm = _estimate_effect_impact(pe, engine, actor)

    # Check if this is optional (accept/decline)
    if pe.optional and pe.accepted is None:
        # Accept option
        candidates.append(AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_EFFECT,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.RESOLVE_EFFECT,
                actor,
                pending_effect_id=pe.id,
                accept=True,
            ),
            source_instance_id=pe.source_id,
            source_card_id=pe.source_card_id,
            pending_effect_id=pe.id,
            resolve_optional=True,
            label=f"Accept optional effect",
            metadata={
                "pending_effect_id": pe.id,
                "accept": True,
                "optional": True,
                "effect_kind": effect_kind,
                "effect_polarity": effect_polarity,
                "projected_benefit": projected_benefit,
                "projected_harm": projected_harm,
                "ability_name": _get_ability_name(pe),
                "origin": pe.origin,
            },
            effect_kind=effect_kind,
            effect_polarity=effect_polarity,
            projected_benefit=projected_benefit,
            projected_harm=projected_harm,
            origin=pe.origin,
        ))
        # Decline option
        candidates.append(AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_EFFECT,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.RESOLVE_EFFECT,
                actor,
                pending_effect_id=pe.id,
                accept=False,
            ),
            source_instance_id=pe.source_id,
            source_card_id=pe.source_card_id,
            pending_effect_id=pe.id,
            resolve_optional=False,  # explicit decline
            label=f"Decline optional effect",
            metadata={
                "pending_effect_id": pe.id,
                "accept": False,
                "optional": True,
                "effect_kind": effect_kind,
                "effect_polarity": effect_polarity,
                "projected_benefit": projected_benefit,
                "projected_harm": projected_harm,
                "ability_name": _get_ability_name(pe),
                "origin": pe.origin,
            },
            effect_kind=effect_kind,
            effect_polarity=effect_polarity,
            projected_benefit=projected_benefit,
            projected_harm=projected_harm,
            origin=pe.origin,
        ))
    elif pe.requires_target_input and pe.current_requirement:
        # Target selection required
        requirement = pe.current_requirement
        valid_targets = get_valid_targets_for_requirement(state, requirement, actor, engine)
        for target in valid_targets:
            cdef = engine.card_def(state, target) if target in state.cards else None
            candidates.append(AutomatedActionCandidate(
                family=AutomatedActionFamily.RESOLVE_EFFECT,
                actor=actor,
                stable_key=make_stable_key(
                    AutomatedActionFamily.RESOLVE_EFFECT,
                    actor,
                    pending_effect_id=pe.id,
                    target=target,
                ),
                source_instance_id=pe.source_id,
                source_card_id=pe.source_card_id,
                target_instance_id=target,
                target_card_id=cdef.id if cdef else None,
                pending_effect_id=pe.id,
                targets=(target,),
                label=f"Select {cdef.full_name if cdef else 'target'} for effect",
                metadata={
                    "pending_effect_id": pe.id,
                    "target": target,
                    "effect_kind": effect_kind,
                    "effect_polarity": effect_polarity,
                    "target_requirement_kind": requirement.kind,
                    "ability_name": _get_ability_name(pe),
                    "origin": pe.origin,
                },
                effect_kind=effect_kind,
                effect_polarity=effect_polarity,
                target_requirement_kind=requirement.kind,
                origin=pe.origin,
            ))
    elif pe.requires_choice_input:
        # Choice index selection required
        for choice_idx in range(len(pe.choice_options)):
            candidates.append(AutomatedActionCandidate(
                family=AutomatedActionFamily.RESOLVE_EFFECT,
                actor=actor,
                stable_key=make_stable_key(
                    AutomatedActionFamily.RESOLVE_EFFECT,
                    actor,
                    pending_effect_id=pe.id,
                    choice_index=choice_idx,
                ),
                source_instance_id=pe.source_id,
                source_card_id=pe.source_card_id,
                pending_effect_id=pe.id,
                choice_index=choice_idx,
                label=f"Choose option {choice_idx + 1}",
                metadata={
                    "pending_effect_id": pe.id,
                    "choice_index": choice_idx,
                    "choice_options_count": len(pe.choice_options),
                    "effect_kind": effect_kind,
                    "effect_polarity": effect_polarity,
                    "ability_name": _get_ability_name(pe),
                    "origin": pe.origin,
                },
                effect_kind=effect_kind,
                effect_polarity=effect_polarity,
                origin=pe.origin,
            ))
    else:
        # No input required, just resolve
        candidates.append(AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_EFFECT,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.RESOLVE_EFFECT,
                actor,
                pending_effect_id=pe.id,
            ),
            source_instance_id=pe.source_id,
            source_card_id=pe.source_card_id,
            pending_effect_id=pe.id,
            label=f"Resolve effect",
            metadata={
                "pending_effect_id": pe.id,
                "effect_kind": effect_kind,
                "effect_polarity": effect_polarity,
                "ability_name": _get_ability_name(pe),
                "origin": pe.origin,
            },
            effect_kind=effect_kind,
            effect_polarity=effect_polarity,
            origin=pe.origin,
        ))

    return candidates


def _get_effect_kind(pe: Any) -> str | None:
    """Extract the effect kind from a pending effect."""
    if not pe.effects:
        return None
    if pe.current_effect_index < len(pe.effects):
        effect = pe.effects[pe.current_effect_index]
        if hasattr(effect, 'kind'):
            return effect.kind
        if isinstance(effect, dict):
            return effect.get('kind')
    return None


def _classify_effect_polarity(pe: Any, actor: int) -> str:
    """Classify effect polarity for the given actor.

    Mirrors Lorcanito's classifyTargetedStepPolarity and classifyEffectPolarity.
    """
    effect = None
    if pe.effects and pe.current_effect_index < len(pe.effects):
        effect = pe.effects[pe.current_effect_index]

    if effect is None:
        return "neutral"

    effect_target = None
    if hasattr(effect, 'target'):
        effect_target = effect.target
    elif isinstance(effect, dict):
        effect_target = effect.get('target')

    # Determine polarity based on effect type and target
    effect_kind = _get_effect_kind(pe)

    # DRAW, GAIN_LORE, PLAY_CARD are generally beneficial
    beneficial_effects = {"draw", "gain_lore", "play_card", "put_in_play", "gain_ink"}
    # DEAL_DAMAGE to opponent is beneficial, to self is harmful
    # HEAL is generally beneficial

    if effect_kind in beneficial_effects:
        if effect_target in {"YOU", "CONTROLLER", None} or effect_target == str(actor):
            return "beneficial"
        if effect_target in {"OPPONENT", "EACH_OPPONENT"}:
            return "beneficial"
        return "mixed"

    if effect_kind == "deal_damage":
        if effect_target in {"OPPONENT", "EACH_OPPONENT"}:
            return "beneficial"
        if effect_target in {"YOU", "CONTROLLER", None} or effect_target == str(actor):
            return "harmful"
        return "mixed"

    if effect_kind == "banish":
        return "neutral"  # Depends heavily on what's being banished

    return "neutral"


def _estimate_effect_impact(pe: Any, engine: GameEngine | None, actor: int) -> tuple[float, float]:
    """Estimate projected benefit and harm for an effect.

    Mirrors Lorcanito's estimateEffectBenefit with simple heuristics.
    """
    benefit = 0.0
    harm = 0.0

    effect_kind = _get_effect_kind(pe)

    # Simple benefit estimates based on effect type
    if effect_kind == "draw":
        benefit += 3.0  # Cards have value
    elif effect_kind == "gain_lore":
        benefit += 4.0  # Lore wins games
    elif effect_kind == "play_card":
        benefit += 5.0  # Getting a card into play is valuable
    elif effect_kind == "gain_ink":
        benefit += 2.0  # Ink is resource
    elif effect_kind == "deal_damage":
        harm += 2.0  # Damage is harm to opponent
    elif effect_kind == "banish":
        harm += 3.0  # Banishing is harmful

    return benefit, harm


def _get_ability_name(pe: Any) -> str | None:
    """Get ability name from pending effect."""
    if pe.origin_id:
        return pe.origin_id
    if pe.raw and isinstance(pe.raw, dict):
        return pe.raw.get("ability_name")
    return None


def _candidate_from_action(state: GameState, engine: GameEngine, action: Action) -> AutomatedActionCandidate | None:
    actor = action.actor
    if action.kind == ACTION_KEEP_HAND:
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.ALTER_HAND,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.ALTER_HAND, actor, mode="keep"),
            choice_index=0,
            label="Keep opening hand",
        )
    if action.kind == ACTION_MULLIGAN:
        targets = tuple(int(cid) for cid in sorted(action.choice or ()))
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.ALTER_HAND,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.ALTER_HAND, actor, mode="mulligan", targets=targets),
            targets=targets,
            choice_index=1,
            label=f"Mulligan {len(targets)} cards",
        )
    if action.kind == ACTION_INK_CARD:
        cdef = engine.card_def(state, action.card)
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.PUT_CARD_INTO_INKWELL,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.PUT_CARD_INTO_INKWELL, actor, card=action.card, card_id=cdef.id),
            card_instance_id=action.card,
            source_card_id=cdef.id,
            label=f"Ink {cdef.full_name}",
        )
    if action.kind == ACTION_PLAY_CARD:
        cdef = engine.card_def(state, action.card)
        tdef = engine.card_def(state, action.target) if action.target is not None else None
        metadata: dict[str, Any] = {}
        if cdef.card_type == CARD_ACTION and cdef.effects and action.target is None and any(getattr(e, "target", None) for e in cdef.effects):
            metadata["untargeted_action"] = True
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.PLAY_CARD,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.PLAY_CARD, actor, card=action.card, card_id=cdef.id, target=action.target),
            card_instance_id=action.card,
            source_card_id=cdef.id,
            target_instance_id=action.target,
            target_card_id=tdef.id if tdef else None,
            payment_mode="standard",
            label=f"Play {cdef.full_name}",
            metadata=metadata,
        )
    # B10: Alternative play modes - SING_SONG and PLAY_SHIFTED
    if action.kind == "SING_SONG":
        song_def = engine.card_def(state, action.card)
        singer_def = engine.card_def(state, action.source) if action.source else None
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.SING_SONG,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.SING_SONG, actor,
                song=action.card, song_id=song_def.id,
                singer=action.source, singer_id=singer_def.id if singer_def else None,
            ),
            card_instance_id=action.card,
            source_card_id=song_def.id,
            source_instance_id=action.source,
            singer_instance_ids=(action.source,) if action.source else (),
            payment_mode="sing",
            label=f"Sing {song_def.full_name} with {singer_def.full_name if singer_def else 'singer'}",
            metadata={
                "song_id": song_def.id,
                "singer_id": singer_def.id if singer_def else None,
                "payment_mode": "sing",
            },
        )
    if action.kind == "PLAY_SHIFTED":
        shift_def = engine.card_def(state, action.card)
        target_def = engine.card_def(state, action.target) if action.target else None
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.PLAY_SHIFTED,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.PLAY_SHIFTED, actor,
                card=action.card, card_id=shift_def.id,
                target=action.target, target_id=target_def.id if target_def else None,
            ),
            card_instance_id=action.card,
            source_card_id=shift_def.id,
            target_instance_id=action.target,
            target_card_id=target_def.id if target_def else None,
            shift_target_instance_id=action.target,
            payment_mode="shift",
            label=f"Shift {shift_def.full_name} onto {target_def.full_name if target_def else 'target'}",
            metadata={
                "shift_target_id": action.target,
                "shift_target_name": target_def.full_name if target_def else None,
                "payment_mode": "shift",
            },
        )
    if action.kind == ACTION_QUEST:
        cdef = engine.card_def(state, action.source)
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.QUEST,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.QUEST, actor, source=action.source, card_id=cdef.id),
            source_instance_id=action.source,
            source_card_id=cdef.id,
            label=f"Quest with {cdef.full_name}",
        )
    if action.kind == ACTION_CHALLENGE:
        sdef = engine.card_def(state, action.source)
        tdef = engine.card_def(state, action.target)
        metadata = _challenge_preview(state, engine, action.source, action.target)
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.CHALLENGE,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.CHALLENGE, actor, source=action.source, source_id=sdef.id, target=action.target, target_id=tdef.id),
            source_instance_id=action.source,
            source_card_id=sdef.id,
            target_instance_id=action.target,
            target_card_id=tdef.id,
            label=f"Challenge {tdef.full_name} with {sdef.full_name}",
            metadata=metadata,
        )
    if action.kind == ACTION_MOVE_TO_LOCATION:
        sdef = engine.card_def(state, action.source)
        tdef = engine.card_def(state, action.target)
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION, actor, source=action.source, target=action.target),
            source_instance_id=action.source,
            source_card_id=sdef.id,
            target_instance_id=action.target,
            target_card_id=tdef.id,
            label=f"Move {sdef.full_name} to {tdef.full_name}",
        )
    if action.kind == ACTION_END_TURN:
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.PASS_TURN,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.PASS_TURN, actor),
            label="Pass turn",
        )
    if action.kind == ACTION_CONCEDE:
        return AutomatedActionCandidate(
            family=AutomatedActionFamily.CONCEDE,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.CONCEDE, actor),
            label="Concede",
        )
    if action.kind == ACTION_RESOLVE_PENDING_EFFECT:
        choice = action.choice or {}
        pending_effect_id = choice.get("pending_effect_id")
        accept = choice.get("accept") if "accept" in choice else None
        choice_index = choice.get("choice_index")
        named_card = choice.get("named_card")
        destination = choice.get("destination")
        destinations_input = choice.get("destinations")
        structured_destinations = tuple(
            {
                "zone": str(destination_item.get("zone")),
                "cards": tuple(destination_item.get("cards", ())),
            }
            for destination_item in destinations_input
            if isinstance(destination_item, dict) and destination_item.get("zone")
        ) if isinstance(destinations_input, (list, tuple)) else ()
        stable_destinations = tuple(
            f"{destination['zone']}:{','.join(str(card_id) for card_id in destination['cards'])}"
            for destination in structured_destinations
        )
        amount = choice.get("amount")
        slotted_targets = _normalize_slotted_targets_for_candidate(choice.get("slotted_targets"))
        flat_slotted_targets: tuple[int, ...] = ()
        if slotted_targets:
            from lorcana_bot.targeting import flatten_slotted_targets
            flat_slotted_targets = flatten_slotted_targets(slotted_targets)
        targets = tuple(choice.get("targets", ())) or flat_slotted_targets
        discard_card_ids = tuple(choice.get("discard_card_ids", ()))
        enter_play_exerted = choice.get("enter_play_exerted")

        source_card_id = None
        if action.source is not None and action.source in state.cards:
            source_card_id = state.cards[action.source].card_id

        metadata = {
            "pending_effect_id": pending_effect_id,
            "accept": accept,
            "choice_index": choice_index,
            "selected_card_id": choice.get("selected_card_id"),
            "top_cards": tuple(choice.get("top_cards", ())),
            "bottom_cards": tuple(choice.get("bottom_cards", ())),
            "named_card": named_card,
            "destination": destination,
            "destinations": structured_destinations,
            "amount": amount,
            "targets": targets,
            "discard_card_ids": discard_card_ids,
            "enter_play_exerted": enter_play_exerted,
            "slotted_targets": slotted_targets,
        }
        metadata = {key: value for key, value in metadata.items() if value is not None and value != ()}

        label = "Resolve pending effect"
        if named_card is not None:
            label = f"Name {named_card}"
        elif structured_destinations:
            label = "Choose scry destinations"
        elif destination is not None:
            label = f"Choose {destination}"
        elif choice.get("selected_card_id") is not None:
            label = f"Select card {choice['selected_card_id']}"
        elif "top_cards" in choice or "bottom_cards" in choice:
            label = "Choose scry ordering"
        elif discard_card_ids:
            label = f"Discard {len(discard_card_ids)} cards"
        elif amount is not None:
            label = f"Choose amount {amount}"

        return AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_EFFECT,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.RESOLVE_EFFECT,
                actor,
                pending_effect_id=pending_effect_id,
                accept=accept,
                choice_index=choice_index,
                target=action.target,
                selected_card_id=choice.get("selected_card_id"),
                top_cards=tuple(choice.get("top_cards", ())),
                bottom_cards=tuple(choice.get("bottom_cards", ())),
                named_card=named_card,
                destination=destination,
                destinations=stable_destinations,
                amount=amount,
                targets=targets,
                discard_card_ids=discard_card_ids,
                enter_play_exerted=enter_play_exerted,
                slotted_targets=slotted_targets,
            ),
            source_instance_id=action.source,
            source_card_id=source_card_id,
            target_instance_id=action.target,
            pending_effect_id=str(pending_effect_id) if pending_effect_id is not None else None,
            choice_index=choice_index,
            resolve_optional=accept,
            named_card=named_card,
            destinations={str(destination): ()} if destination is not None else {},
            label=label,
            metadata=metadata,
            # B9: Capture new pending choice fields
            amount=amount,
            targets=targets,
            discard_card_ids=discard_card_ids,
            enter_play_exerted=enter_play_exerted,
            slotted_targets=slotted_targets,
        )
    if action.kind == ACTION_RESOLVE_BAG:
        bag_id = action.choice.get("bag_id") if action.choice else None
        accept = action.choice.get("accept", True) if action.choice else True

        # Get trigger info from bag entry
        source_card_id = None
        ability_id = None
        ability_name = None
        event_type = None
        optional = False
        effect_kinds: list[str] = []

        if bag_id and hasattr(state, "bag"):
            for entry in state.bag:
                if entry.id == bag_id:
                    source_card_id = entry.source_card_id
                    ability_id = entry.ability_id
                    ability_name = entry.ability_name
                    event_type = entry.event_type
                    optional = getattr(entry, "optional", False)
                    effect_kinds = [str(getattr(e, "kind", "unknown")) for e in getattr(entry, "effects", [])]
                    break

        is_optional = optional and not accept

        return AutomatedActionCandidate(
            family=AutomatedActionFamily.RESOLVE_BAG,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.RESOLVE_BAG, actor, bag_id=bag_id, accept=accept),
            source_instance_id=action.source if action.source else None,
            source_card_id=source_card_id,
            bag_index=0,  # B2: Will be updated with actual index
            resolve_optional=accept if optional else None,
            ability_id=ability_id,
            label=f"Resolve trigger: {ability_name or bag_id}",
            metadata={
                "bag_id": bag_id,
                "trigger_id": ability_id,
                "ability_name": ability_name,
                "event": event_type,
                "optional": optional,
                "accept": accept,
                "effect_kinds": effect_kinds,
            },
        )
    if action.kind == ACTION_USE_ABILITY:
        from lorcana_bot.abilities import get_activated_abilities_for_card

        source_card_id = None
        ability_id = action.choice.get("ability_id") if action.choice else None
        ability_index = action.choice.get("ability_index") if action.choice else None

        if action.source:
            source_card_id = state.cards[action.source].card_id if action.source in state.cards else None

        # Get ability name from card
        ability_name = None
        if action.source:
            card_def = engine.card_def(state, action.source)
            abilities = get_activated_abilities_for_card(state, action.source, card_def)
            for a in abilities:
                if a.ability_index == ability_index or a.ability_id == ability_id:
                    ability_name = a.name
                    break

        return AutomatedActionCandidate(
            family=AutomatedActionFamily.ACTIVATE_ABILITY,
            actor=actor,
            stable_key=make_stable_key(
                AutomatedActionFamily.ACTIVATE_ABILITY,
                actor,
                source=action.source,
                ability_id=ability_id,
                ability_index=ability_index,
            ),
            source_instance_id=action.source,
            source_card_id=source_card_id,
            ability_id=ability_id,
            ability_index=ability_index,
            label=f"Use ability: {ability_name or ability_id or 'activated'}",
            metadata={
                "ability_id": ability_id,
                "ability_index": ability_index,
                "ability_name": ability_name,
            },
        )
    return None


def _normalize_slotted_targets_for_candidate(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    from lorcana_bot.targeting import normalize_slotted_target_input
    return normalize_slotted_target_input(value)


def _mulligan_structural_candidates(state: GameState, engine: GameEngine, actor: int, legal: list[Action]) -> list[AutomatedActionCandidate]:
    if not any(action.kind == ACTION_MULLIGAN for action in legal):
        return []
    ps = state.players[actor]
    selected = []
    seen_expensive: set[str] = set()
    for cid in sorted(ps.hand):
        cdef = engine.card_def(state, cid)
        if not cdef.inkable or cdef.cost >= 5 or (cdef.cost >= 4 and cdef.id in seen_expensive):
            selected.append(cid)
        if cdef.cost >= 4:
            seen_expensive.add(cdef.id)
    if not selected or len(selected) >= len(ps.hand):
        return []
    selected_tuple = tuple(selected)
    return [
        AutomatedActionCandidate(
            family=AutomatedActionFamily.ALTER_HAND,
            actor=actor,
            stable_key=make_stable_key(AutomatedActionFamily.ALTER_HAND, actor, mode="structural", targets=selected_tuple),
            targets=selected_tuple,
            choice_index=1,
            label=f"Structural mulligan {len(selected_tuple)} cards",
            metadata={"mulligan_mode": "structural"},
        )
    ]


def _record_activated_ability_skips(state: GameState, engine: GameEngine, actor: int, result: CandidateEnumerationResult) -> None:
    from lorcana_bot.abilities import get_available_abilities_for_player, validate_ability_costs

    # Only report skipped abilities that can't be used this turn
    for ability in get_available_abilities_for_player(state, engine, actor):
        can_pay, _ = validate_ability_costs(state, engine, ability)
        if not can_pay:
            result.unsupported_skips.append(
                {
                    "family": AutomatedActionFamily.ACTIVATE_ABILITY,
                    "source_card": ability.source_card_id,
                    "ability_id": ability.ability_id,
                    "ability_index": ability.ability_index,
                    "unsupported_reason": "cannot pay ability costs",
                    "raw_ability_summary": str(ability.raw)[:240],
                }
            )


def _challenge_preview(state: GameState, engine: GameEngine, attacker: int, defender: int) -> dict[str, Any]:
    attacker_def = engine.card_def(state, attacker)
    defender_def = engine.card_def(state, defender)
    attacker_damage = state.cards[attacker].damage
    defender_damage = state.cards[defender].damage
    damage_to_defender = engine.damage_after_resist(defender_def, engine.effective_strength(state, attacker))
    damage_to_attacker = engine.damage_after_resist(attacker_def, engine.effective_strength(state, defender)) if defender_def.card_type == "character" else 0
    return {
        "attacker_strength": engine.effective_strength(state, attacker),
        "defender_strength": engine.effective_strength(state, defender),
        "attacker_willpower_remaining": engine.effective_willpower(state, attacker) - attacker_damage,
        "defender_willpower_remaining": engine.effective_willpower(state, defender) - defender_damage,
        "attacker_would_be_banished": attacker_damage + damage_to_attacker >= engine.effective_willpower(state, attacker),
        "defender_would_be_banished": defender_damage + damage_to_defender >= engine.effective_willpower(state, defender),
        "defender_lore": int(defender_def.lore or 0),
        "target_type": defender_def.card_type,
    }


def _source_card_id(state: GameState, source: int | None) -> str | None:
    if source is None or source not in state.cards:
        return None
    return state.cards[source].card_id


def _action_sort_key(action: Action) -> tuple:
    return (action.kind, action.actor, action.card or -1, action.source or -1, action.target or -1, str(action.choice))

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

    if getattr(state, "bag", None):
        for idx, trigger in enumerate(state.bag[: caps.max_candidates_per_family]):
            if getattr(trigger, "controller", None) == actor:
                result.unsupported_skips.append(
                    {
                        "family": AutomatedActionFamily.RESOLVE_BAG,
                        "source_card": _source_card_id(state, trigger.source),
                        "trigger_id": str(idx),
                        "unsupported_reason": "engine auto-resolves bag and has no resolver action yet",
                    }
                )

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
    return None


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
    for cid in sorted(state.players[actor].play):
        card = engine.card_def(state, cid)
        abilities = tuple(getattr(card, "activated_abilities", ()))
        raw_candidates = abilities or tuple(a for a in getattr(card, "unsupported_abilities", ()) if "activate" in str(a).casefold() or "exert" in str(a).casefold())
        for idx, ability in enumerate(raw_candidates):
            result.unsupported_skips.append(
                {
                    "family": AutomatedActionFamily.ACTIVATE_ABILITY,
                    "source_card": card.id,
                    "ability_index": idx,
                    "unsupported_reason": "activated ability execution is reserved for Milestone B",
                    "raw_ability_summary": str(ability)[:240],
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

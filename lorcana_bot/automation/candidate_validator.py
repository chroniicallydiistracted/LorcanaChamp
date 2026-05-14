from __future__ import annotations

from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState

from .candidates import AutomatedActionCandidate, AutomatedActionFamily, CandidateValidationResult
from .move_adapter import CandidateAdapterError, candidate_to_action


def validate_candidate(state: GameState, engine: GameEngine, candidate: AutomatedActionCandidate) -> CandidateValidationResult:
    if candidate.actor != state.active_player and candidate.family not in {AutomatedActionFamily.ALTER_HAND, AutomatedActionFamily.CONCEDE}:
        return CandidateValidationResult(False, "candidate actor is not active actor", "not_actor")
    if candidate.source_instance_id is not None and candidate.source_instance_id not in state.cards:
        return CandidateValidationResult(False, "source instance is missing", "source_missing")
    if candidate.target_instance_id is not None and candidate.target_instance_id not in state.cards:
        return CandidateValidationResult(False, "target instance is missing", "target_missing")
    if candidate.card_instance_id is not None and candidate.card_instance_id not in state.cards:
        return CandidateValidationResult(False, "card instance is missing", "source_missing")
    if candidate.family in {
        AutomatedActionFamily.CHOOSE_WHO_GOES_FIRST,
        AutomatedActionFamily.RESOLVE_BAG,
        AutomatedActionFamily.RESOLVE_EFFECT,
    }:
        return CandidateValidationResult(False, "candidate family is not executable by current engine", "unsupported_candidate_family")
    if candidate.family == AutomatedActionFamily.ACTIVATE_ABILITY:
        return CandidateValidationResult(False, "activated ability execution is not supported in Milestone A", "unsupported_cost")
    try:
        action = candidate_to_action(candidate)
    except CandidateAdapterError as exc:
        return CandidateValidationResult(False, str(exc), "adapter_error")
    try:
        legal_actions = engine.legal_actions(state, candidate.actor)
    except Exception as exc:
        return CandidateValidationResult(False, str(exc), "adapter_error")
    if action not in legal_actions:
        return CandidateValidationResult(False, f"action is not in engine legal actions: {action.compact()}", "illegal_action")
    return CandidateValidationResult(True)

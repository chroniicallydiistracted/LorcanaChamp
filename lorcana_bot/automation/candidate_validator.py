from __future__ import annotations

from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState

from .candidates import AutomatedActionCandidate, AutomatedActionFamily, CandidateValidationResult
from .move_adapter import CandidateAdapterError, candidate_to_action


def validate_candidate(state: GameState, engine: GameEngine, candidate: AutomatedActionCandidate) -> CandidateValidationResult:
    """Validate a candidate by checking engine legality.

    The engine's legal_actions() is the source of truth - it already handles
    pending effects, bag resolution, and actor priority correctly.

    This validator simply checks that the candidate maps to a legal action.
    """
    # Resolution families can act even when not active player (engine handles this)
    resolution_families = {
        AutomatedActionFamily.RESOLVE_BAG,
        AutomatedActionFamily.RESOLVE_EFFECT,
    }

    # Check instance existence for all candidates
    if candidate.source_instance_id is not None and candidate.source_instance_id not in state.cards:
        return CandidateValidationResult(False, "source instance is missing", "source_missing")
    if candidate.target_instance_id is not None and candidate.target_instance_id not in state.cards:
        return CandidateValidationResult(False, "target instance is missing", "target_missing")
    if candidate.card_instance_id is not None and candidate.card_instance_id not in state.cards:
        return CandidateValidationResult(False, "card instance is missing", "source_missing")

    # Map candidate to action
    try:
        action = candidate_to_action(candidate)
    except CandidateAdapterError as exc:
        return CandidateValidationResult(False, str(exc), "adapter_error")

    # Check engine legality - this is the source of truth
    try:
        legal_actions = engine.legal_actions(state, candidate.actor)
    except Exception as exc:
        return CandidateValidationResult(False, str(exc), "adapter_error")

    if action not in legal_actions:
        return CandidateValidationResult(False, f"action is not in engine legal actions: {action.compact()}", "illegal_action")

    return CandidateValidationResult(True)

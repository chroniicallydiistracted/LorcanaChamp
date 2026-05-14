from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_bot.constants import ACTION_CONCEDE, ACTION_END_TURN
from lorcana_bot.engine import GameEngine, IllegalActionError
from lorcana_bot.state import GameState

from .actor_resolution import ActorResolution, resolve_current_actor
from .candidate_enumerator import enumerate_automated_action_candidates
from .candidates import AutomatedActionCandidate, AutomatedActionCandidateSummary
from .caps import AutomationSearchCaps
from .decision_trace import AutomatedDecisionTrace, build_trace
from .deck_profile import build_deck_profile, public_profile_for_policy
from .move_adapter import candidate_to_action
from .strategy import AutomatedActionStrategy, StrategyContext


@dataclass
class AutomatedActionPlan:
    actor: int | None
    actor_resolution: ActorResolution
    candidates: list[AutomatedActionCandidate]
    summaries: list[AutomatedActionCandidateSummary]
    validation_rejections: list[dict[str, Any]]
    unsupported_skips: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]


def create_automated_action_plan(
    state: GameState,
    engine: GameEngine,
    strategy: AutomatedActionStrategy,
    caps: AutomationSearchCaps = AutomationSearchCaps(),
) -> AutomatedActionPlan:
    actor_resolution = resolve_current_actor(state, engine)
    actor = actor_resolution.actor
    if actor is None:
        return AutomatedActionPlan(None, actor_resolution, [], [], [], [], [{"reason": "blocked_no_actor"}])
    enum = enumerate_automated_action_candidates(state, engine, actor, caps)
    context = _strategy_context(state, engine, actor, strategy)
    summaries = strategy.summarize_candidates(context, tuple(enum.candidates))
    if len(summaries) != len(enum.candidates):
        raise ValueError(f"strategy {strategy.name} returned {len(summaries)} summaries for {len(enum.candidates)} candidates")
    input_keys = {candidate.stable_key for candidate in enum.candidates}
    if {summary.stable_key for summary in summaries} != input_keys:
        raise ValueError(f"strategy {strategy.name} did not summarize exactly the validated candidate set")
    original_order = {candidate.stable_key: idx for idx, candidate in enumerate(enum.candidates)}
    summaries = sorted(summaries, key=lambda s: (s.family_order, -s.score, original_order[s.stable_key], s.stable_key))
    return AutomatedActionPlan(actor, actor_resolution, enum.candidates, summaries, enum.validation_rejections, enum.unsupported_skips, enum.diagnostics)


def take_automated_action(
    state: GameState,
    engine: GameEngine,
    strategy: AutomatedActionStrategy,
    caps: AutomationSearchCaps = AutomationSearchCaps(),
) -> tuple[GameState, AutomatedDecisionTrace]:
    plan = create_automated_action_plan(state, engine, strategy, caps)
    execution_attempts: list[dict[str, Any]] = []
    selected_summary: AutomatedActionCandidateSummary | None = None
    selected_action = None
    fallback_taken = None
    if plan.actor is None:
        trace = build_trace(
            state=state,
            engine=engine,
            actor_resolution=plan.actor_resolution,
            strategy_name=strategy.name,
            information_policy=getattr(strategy, "information_policy", "fair"),
            summaries=plan.summaries,
            validation_rejections=plan.validation_rejections,
            unsupported_skips=plan.unsupported_skips,
            execution_attempts=execution_attempts,
            selected_summary=None,
            selected_action=None,
            fallback_taken=None,
            result="blocked",
        )
        return state, trace

    failures = 0
    for summary in plan.summaries:
        try:
            action = candidate_to_action(summary.candidate)
            next_state = engine.apply_action(state, action, validate=True)
            execution_attempts.append({"stable_key": summary.stable_key, "action_kind": action.kind, "success": True})
            selected_summary = summary
            selected_action = action
            trace = build_trace(
                state=state,
                engine=engine,
                actor_resolution=plan.actor_resolution,
                strategy_name=strategy.name,
                information_policy=getattr(strategy, "information_policy", "fair"),
                summaries=plan.summaries,
                validation_rejections=plan.validation_rejections,
                unsupported_skips=plan.unsupported_skips,
                execution_attempts=execution_attempts,
                selected_summary=selected_summary,
                selected_action=selected_action,
                fallback_taken=fallback_taken,
                result="success",
            )
            return next_state, trace
        except Exception as exc:
            failures += 1
            execution_attempts.append(
                {
                    "stable_key": summary.stable_key,
                    "action_kind": getattr(locals().get("action", None), "kind", None),
                    "success": False,
                    "error_code": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            if failures >= caps.max_execution_failures:
                break

    for legal in engine.legal_actions(state, plan.actor):
        if legal.kind == ACTION_END_TURN:
            next_state = engine.apply_action(state, legal, validate=True)
            fallback_taken = "pass_turn"
            execution_attempts.append({"stable_key": "fallback:passTurn", "action_kind": legal.kind, "success": True})
            trace = build_trace(
                state=state,
                engine=engine,
                actor_resolution=plan.actor_resolution,
                strategy_name=strategy.name,
                information_policy=getattr(strategy, "information_policy", "fair"),
                summaries=plan.summaries,
                validation_rejections=plan.validation_rejections,
                unsupported_skips=plan.unsupported_skips,
                execution_attempts=execution_attempts,
                selected_summary=None,
                selected_action=legal,
                fallback_taken=fallback_taken,
                result="fallback",
            )
            return next_state, trace

    trace = build_trace(
        state=state,
        engine=engine,
        actor_resolution=plan.actor_resolution,
        strategy_name=strategy.name,
        information_policy=getattr(strategy, "information_policy", "fair"),
        summaries=plan.summaries,
        validation_rejections=plan.validation_rejections,
        unsupported_skips=plan.unsupported_skips,
        execution_attempts=execution_attempts,
        selected_summary=None,
        selected_action=None,
        fallback_taken=None,
        result="blocked",
    )
    return state, trace


def _strategy_context(state: GameState, engine: GameEngine, actor: int, strategy: AutomatedActionStrategy) -> StrategyContext:
    information_policy = getattr(strategy, "information_policy", "fair")
    actor_decklist = [state.cards[cid].card_id for zone in (state.players[actor].deck, state.players[actor].hand, state.players[actor].play, state.players[actor].discard, state.players[actor].inkwell) for cid in zone]
    opponent = state.opponent(actor)
    opponent_decklist = [state.cards[cid].card_id for zone in (state.players[opponent].deck, state.players[opponent].hand, state.players[opponent].play, state.players[opponent].discard, state.players[opponent].inkwell) for cid in zone]
    actor_profile = build_deck_profile(actor_decklist, engine.db) if actor_decklist else None
    opponent_profile = build_deck_profile(opponent_decklist, engine.db) if information_policy == "oracle" and opponent_decklist else None
    return StrategyContext(
        state=state,
        engine=engine,
        actor=actor,
        information_policy=information_policy,
        actor_observation=engine.observe(state, actor),
        actor_deck_profile=public_profile_for_policy(actor_profile, information_policy=information_policy, is_actor=True),
        opponent_deck_profile=public_profile_for_policy(opponent_profile, information_policy=information_policy, is_actor=False),
        turn_number=state.turn_number,
        phase=state.phase,
    )

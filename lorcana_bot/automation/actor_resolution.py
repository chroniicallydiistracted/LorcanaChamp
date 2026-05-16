from __future__ import annotations

from dataclasses import dataclass

from lorcana_bot.constants import PHASE_MULLIGAN
from lorcana_bot.engine import GameEngine
from lorcana_bot.pending_effects import is_pending_effect_resolvable
from lorcana_bot.state import GameState


@dataclass(frozen=True)
class ActorResolution:
    actor: int | None
    reason: str
    pending_object_type: str | None = None
    pending_object_id: str | None = None


def resolve_current_actor(state: GameState, engine: GameEngine) -> ActorResolution:
    """Resolve the current actor for automation decisions.
    
    Priority (mirrors GameRunner.play()):
    1. Pending effect chooser
    2. Bag resolver  
    3. Active player
    
    This ordering ensures resolution happens before normal gameplay.
    """
    # 1. Check for pending effects - the chooser acts even when not active player
    pending_effects = getattr(state, "pending_effects", None)
    if pending_effects:
        for pe in pending_effects:
            if getattr(pe, "accepted", None) is None and (
                is_pending_effect_resolvable(pe) or not getattr(pe, "is_complete", False)
            ):
                chooser_id = getattr(pe, "chooser_id", None)
                if chooser_id is not None:
                    return ActorResolution(
                        actor=chooser_id,
                        reason="pending_effect_chooser",
                        pending_object_type="effect",
                        pending_object_id=str(getattr(pe, "id", 0)),
                    )

    if getattr(state, "bag", None):
        trigger = state.bag[0]
        return ActorResolution(
            actor=getattr(trigger, "controller", None),
            reason="pending_bag_resolver",
            pending_object_type="bag",
            pending_object_id=str(getattr(trigger, "source", 0)),
        )

    if state.phase == PHASE_MULLIGAN:
        for offset in (0, 1):
            player = state.active_player if offset == 0 else state.opponent(state.active_player)
            if not state.players[player].has_kept_opening_hand:
                return ActorResolution(actor=player, reason="mulligan_player", pending_object_type="mulligan")
        return ActorResolution(actor=None, reason="mulligan_phase_no_unresolved_player")

    choose_first = getattr(state, "choose_first_player_prompt", None)
    if choose_first:
        actor = getattr(choose_first, "actor", None)
        if actor is not None:
            return ActorResolution(actor=actor, reason="choose_who_goes_first", pending_object_type="choose_first")

    if state.winner is not None:
        return ActorResolution(actor=None, reason="game_over")
    if state.active_player in {0, 1}:
        return ActorResolution(actor=state.active_player, reason="active_priority_player")
    return ActorResolution(actor=None, reason="unresolved_actor")

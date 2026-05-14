from __future__ import annotations

from dataclasses import dataclass

from lorcana_bot.constants import PHASE_MULLIGAN
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import GameState


@dataclass(frozen=True)
class ActorResolution:
    actor: int | None
    reason: str
    pending_object_type: str | None = None
    pending_object_id: str | None = None


def resolve_current_actor(state: GameState, engine: GameEngine) -> ActorResolution:
    pending_effects = getattr(state, "pending_effects", None)
    if pending_effects:
        pending = pending_effects[0]
        actor = getattr(pending, "actor", None) or getattr(pending, "controller", None)
        if actor is not None:
            return ActorResolution(actor=actor, reason="pending_effect_chooser", pending_object_type="effect", pending_object_id=str(getattr(pending, "id", 0)))

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

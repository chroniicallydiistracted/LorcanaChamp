from __future__ import annotations

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
    ACTION_SING_SONG,
)

from .candidates import AutomatedActionCandidate, AutomatedActionFamily


class CandidateAdapterError(ValueError):
    pass


def candidate_to_action(candidate: AutomatedActionCandidate) -> Action:
    family = candidate.family
    actor = candidate.actor
    if family == AutomatedActionFamily.ALTER_HAND:
        if candidate.choice_index == 0:
            return Action(ACTION_KEEP_HAND, actor=actor)
        return Action(ACTION_MULLIGAN, actor=actor, choice=tuple(candidate.targets))
    if family == AutomatedActionFamily.PUT_CARD_INTO_INKWELL:
        return Action(ACTION_INK_CARD, actor=actor, card=_require(candidate.card_instance_id, "card_instance_id"))
    if family == AutomatedActionFamily.PLAY_CARD:
        return Action(ACTION_PLAY_CARD, actor=actor, card=_require(candidate.card_instance_id, "card_instance_id"), target=candidate.target_instance_id)
    if family == AutomatedActionFamily.QUEST:
        return Action(ACTION_QUEST, actor=actor, source=_require(candidate.source_instance_id, "source_instance_id"))
    if family == AutomatedActionFamily.CHALLENGE:
        return Action(
            ACTION_CHALLENGE,
            actor=actor,
            source=_require(candidate.source_instance_id, "source_instance_id"),
            target=_require(candidate.target_instance_id, "target_instance_id"),
        )
    if family == AutomatedActionFamily.MOVE_CHARACTER_TO_LOCATION:
        return Action(
            ACTION_MOVE_TO_LOCATION,
            actor=actor,
            source=_require(candidate.source_instance_id, "source_instance_id"),
            target=_require(candidate.target_instance_id, "target_instance_id"),
        )
    if family == AutomatedActionFamily.PASS_TURN:
        return Action(ACTION_END_TURN, actor=actor)
    if family == AutomatedActionFamily.CONCEDE:
        return Action(ACTION_CONCEDE, actor=actor)
    if family == AutomatedActionFamily.ACTIVATE_ABILITY:
        ability_id = candidate.ability_id or (candidate.metadata.get("ability_id") if candidate.metadata else None)
        ability_index = candidate.ability_index or (candidate.metadata.get("ability_index") if candidate.metadata else None)
        return Action(
            ACTION_USE_ABILITY,
            actor=actor,
            source=candidate.source_instance_id,
            target=candidate.target_instance_id,
            choice={"ability_id": ability_id, "ability_index": ability_index}
        )
    if family == AutomatedActionFamily.SING_SONG:
        choice = {}
        if candidate.payment_mode == "singTogether":
            choice = {"mode": "singTogether", "singer_ids": tuple(candidate.singer_instance_ids)}
        return Action(
            ACTION_SING_SONG,
            actor=actor,
            card=_require(candidate.card_instance_id, "card_instance_id"),
            source=_require(candidate.source_instance_id, "source_instance_id"),
            choice=choice,
        )
    if family == AutomatedActionFamily.RESOLVE_BAG:
        bag_id = candidate.metadata.get("bag_id") if candidate.metadata else None
        accept = candidate.metadata.get("accept") if candidate.metadata else True
        # For optional triggers, resolve_optional indicates accept (True) or decline (False)
        if candidate.resolve_optional is not None:
            accept = candidate.resolve_optional
        return Action(
            ACTION_RESOLVE_BAG,
            actor=actor,
            source=candidate.source_instance_id,
            choice={"bag_id": bag_id, "accept": accept}
        )
    if family == AutomatedActionFamily.RESOLVE_EFFECT:
        # B7/B9: Map resolveEffect candidates to ACTION_RESOLVE_PENDING_EFFECT
        # B9: Round-trip invariant - capture all pending choice fields
        pending_effect_id = candidate.pending_effect_id or (candidate.metadata.get("pending_effect_id") if candidate.metadata else None)
        choice: dict[str, Any] = {"pending_effect_id": pending_effect_id}

        # Handle optional accept/decline
        if candidate.resolve_optional is not None:
            choice["accept"] = candidate.resolve_optional

        # Handle target selection
        if candidate.target_instance_id is not None:
            choice["target"] = candidate.target_instance_id

        # B9: Handle targets tuple for multi_target pending requirements
        if candidate.targets:
            choice["targets"] = list(candidate.targets)

        # B10.7: Preserve slotted target input and expose flattened targets.
        slotted_targets = candidate.slotted_targets if isinstance(candidate.slotted_targets, dict) else {}
        if slotted_targets:
            choice["slotted_targets"] = slotted_targets
            if not candidate.targets:
                from lorcana_bot.targeting import flatten_slotted_targets
                choice["targets"] = list(flatten_slotted_targets(slotted_targets))

        # Handle choice index
        if candidate.choice_index is not None:
            choice["choice_index"] = candidate.choice_index

        if candidate.named_card is not None:
            choice["named_card"] = candidate.named_card

        # B9: Handle amount for amount pending requirements
        if candidate.amount is not None:
            choice["amount"] = candidate.amount

        # B9: Handle discard_card_ids for discard_choice pending requirements
        if candidate.discard_card_ids:
            choice["discard_card_ids"] = list(candidate.discard_card_ids)

        # B9: Handle enter_play_exerted for enter_play_exerted pending requirements
        if candidate.enter_play_exerted is not None:
            choice["enter_play_exerted"] = candidate.enter_play_exerted

        for key in ("selected_card_id", "top_cards", "bottom_cards", "destination", "destinations"):
            if candidate.metadata and key in candidate.metadata:
                choice[key] = candidate.metadata[key]

        return Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=actor,
            source=candidate.source_instance_id,
            target=candidate.target_instance_id,
            choice=choice
        )
    raise CandidateAdapterError(f"Unsupported candidate family {family}")


def _require(value: int | None, field: str) -> int:
    if value is None:
        raise CandidateAdapterError(f"Missing required {field}")
    return int(value)

from __future__ import annotations

import copy
import itertools
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

from .actions import Action
from .cards import CardDatabase, FormatRules, validate_deck
from .constants import (
    ACTION_CHALLENGE,
    ACTION_CONCEDE,
    ACTION_END_TURN,
    ACTION_INK_CARD,
    ACTION_KEEP_HAND,
    ACTION_MULLIGAN,
    ACTION_MOVE_TO_LOCATION,
    ACTION_PLAY_CARD,
    ACTION_QUEST,
    ACTION_RESOLVE_BAG,
    ACTION_RESOLVE_PENDING_EFFECT,
    ACTION_USE_ABILITY,
    CARD_ACTION,
    CARD_CHARACTER,
    CARD_LOCATION,
    EVENT_CARD_DISCARDED,
    EVENT_CARD_LEFT_DISCARD,
    EVENT_CARD_DRAWN,
    EVENT_CARD_EXERTED,
    EVENT_CARD_PLAYED,
    EVENT_CARD_SUNG,
    EVENT_CARD_READIED,
    EVENT_CARD_RETURNED_TO_HAND,
    EVENT_CHALLENGE_STARTED,
    EVENT_CHALLENGED,
    EVENT_CHALLENGED_AND_BANISHED,
    EVENT_CHARACTER_BANISHED,
    EVENT_BANISH_IN_CHALLENGE,
    EVENT_BE_CHOSEN,
    EVENT_CONCEDED,
    EVENT_DAMAGE_DEALT,
    EVENT_DAMAGE_REMOVED,
    EVENT_INKED,
    EVENT_KEPT_HAND,
    EVENT_LOCATION_LORE_GAINED,
    EVENT_LORE_GAINED,
    EVENT_LORE_LOST,
    EVENT_MOVED_TO_LOCATION,
    EVENT_MULLIGANED,
    EVENT_QUESTED,
    EVENT_SUPPORT,
    EVENT_TRIGGER_DECLINED,
    EVENT_TRIGGER_QUEUED,
    EVENT_TRIGGER_RESOLVED,
    EVENT_TRIGGER_SKIPPED,
    EVENT_TRIGGER_EVENT_BUFFERED,
    EVENT_TURN_END,
    EVENT_TURN_START,
    KEYWORD_BODYGUARD,
    KEYWORD_EVASIVE,
    KEYWORD_RECKLESS,
    KEYWORD_RESIST,
    KEYWORD_RUSH,
    KEYWORD_WARD,
    PHASE_GAME_OVER,
    PHASE_MAIN,
    PHASE_MULLIGAN,
    ZONE_DECK,
    ZONE_DISCARD,
    ZONE_HAND,
    ZONE_INKWELL,
    ZONE_LIMBO,
    ZONE_PLAY,
    ZONE_UNDER,
)
from .state import ActionLogEntry, BagEffectEntry, CardInstance, GameEvent, GameState, PlayerState
from .effect_types import EffectResolutionContext
from .effects import EffectResolver
from .pending_effects import (
    PendingEffect,
    has_pending_effects,
    get_current_pending_effect,
    get_pending_effect_by_id,
    get_valid_targets_for_requirement,
    get_valid_target_candidates_for_pending,
    resolve_pending_effect_target,
    resolve_pending_effect_choice,
    resolve_pending_effect_optional,
    resolve_scry_ordering,
    resolve_scry_destinations,
    resolve_search_selection,
    resolve_reveal_routing,
    resolve_named_card,
    resolve_destination_choice,
    resolve_amount_choice,
    resolve_target_selection,
    resolve_multi_target_selection,
    resolve_slotted_target_selection,
    resolve_player_target_selection,
    resolve_discard_choice,
    resolve_choice_index,
    resolve_optional_choice,
    resolve_enter_play_exerted_choice,
    advance_pending_effect,
    complete_pending_effect,
    get_next_pending_effect_chooser,
)
from .triggers import buffer_trigger_event, flush_triggered_events_to_bag, get_next_bag_resolver, has_pending_bag_items, remove_bag_effect, set_last_bag_resolver, record_bag_effect_resolution, can_resolve_bag_effect_by_restrictions
from .condition_evaluator import evaluate_condition, UnsupportedConditionError
from .abilities import (
    get_activated_abilities_for_card,
    get_available_abilities_for_player,
    can_use_ability_this_turn,
    use_ability,
    validate_ability_costs,
    ActivatedAbility,
    execute_ability_effects,
    validate_effects_supported,
)
from .static_effects import (
    effective_strength as static_effective_strength,
    effective_willpower as static_effective_willpower,
    keywords_for_instance as static_keywords_for_instance,
    static_cost_reductions,
    register_static_effects_for_card,
    deregister_static_effects_for_card,
    StaticEffectType,
    create_modify_stat_effect,
    create_keyword_grant_effect,
    create_cost_reduction_effect,
)
from .replacement_effects import (
    ReplacementEffectEntry,
    ReplacementEffectType,
    register_replacement_effects_for_card,
    register_replacement_effect,
    deregister_replacement_effects_from_card,
    cleanup_replacement_effects_on_turn_end,
    deal_damage as replacement_deal_damage,
    banish_card as replacement_banish_card,
    check_cannot_be_challenged,
    check_cannot_be_targeted,
)

# Diagnostic event types that should not recursively trigger buffering
_DIAGNOSTIC_EVENTS = frozenset({
    EVENT_TRIGGER_QUEUED,
    EVENT_TRIGGER_RESOLVED,
    EVENT_TRIGGER_DECLINED,
    EVENT_TRIGGER_SKIPPED,
    EVENT_TRIGGER_EVENT_BUFFERED,
})

_SUPPORTED_EFFECT_TARGET_KINDS = frozenset({
    "chosen_character",
    "chosen_card",
    "chosen_item",
    "chosen_location",
    "chosen_opposing_character",
    "chosen_damaged_character",
    "opposing_character",
    "self",
    "event_source",
    "event_target",
    "trigger_subject",
    "current_targets",
    "context_targets",
    "your_characters",
    "your_other_characters",
    "opposing_characters",
    "all_characters",
    "damaged_characters",
    "opposing_damaged_characters",
    "chosen_player",
    "you",
    "opponent",
    "each_player",
    "controller",
    "actor",
    "opposing_player",
    "target",
})


class IllegalActionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Observation:
    player: int
    active_player: int
    turn_number: int
    own_lore: int
    opponent_lore: int
    own_deck_count: int
    opponent_deck_count: int
    own_hand: tuple[int, ...]
    opponent_hand_count: int
    own_play: tuple[int, ...]
    opponent_play: tuple[int, ...]
    own_ink_count: int
    own_available_ink: int
    opponent_ink_count: int
    cards_public: dict[int, dict]


class BotProtocol(Protocol):
    def choose_action(self, observation: Observation, legal_actions: list[Action], engine: "GameEngine") -> int: ...


class GameEngine:
    """Rules engine for deterministic legal-action play.

    Implemented scope:
    - 2-player Core Constructed validation helper.
    - initial draw of 7; first player skips first turn draw.
    - inking once per turn.
    - playing characters, simple actions, and items/locations as permanents.
    - location lore at the start of a player's turn.
    - moving characters to friendly locations.
    - questing.
    - character challenges with Evasive, Rush, Bodyguard, Ward target protection, Resist, locations, and damage/banish.
    - basic action effects: draw, gain_lore, deal_damage.

    Not implemented yet:
    - full official card database, replacement effects, all keyword exceptions,
      shift/sing/bodyguard edge cases, multiplayer variants.
    """

    def __init__(self, db: CardDatabase, lore_to_win: int = 20):
        self.db = db
        self.lore_to_win = lore_to_win
        self.effect_resolver = EffectResolver(self)

    def setup_game(
        self,
        decklists: list[list[str]],
        *,
        seed: int | None = None,
        first_player: int = 0,
        validate: bool = False,
        format_rules: FormatRules | None = None,
        enable_mulligan: bool = False,
    ) -> GameState:
        if len(decklists) != 2:
            raise ValueError("This engine currently supports exactly 2 players")

        if validate:
            for idx, deck in enumerate(decklists):
                errors = validate_deck(deck, self.db, format_rules)
                if errors:
                    raise ValueError(f"Player {idx} invalid deck: " + "; ".join(errors))

        rng = random.Random(seed)
        players = [PlayerState(), PlayerState()]
        cards: dict[int, CardInstance] = {}
        next_id = 1

        for player, decklist in enumerate(decklists):
            ids: list[int] = []
            for card_name in decklist:
                card_def = self.db.get(card_name)
                instance = CardInstance(instance_id=next_id, card_id=card_def.id, owner=player, controller=player)
                cards[next_id] = instance
                ids.append(next_id)
                next_id += 1
            rng.shuffle(ids)
            players[player].deck = ids

        state = GameState(
            players=players,
            cards=cards,
            active_player=first_player,
            first_player=first_player,
            phase=PHASE_MULLIGAN if enable_mulligan else PHASE_MAIN,
            seed=seed,
            has_first_player_skipped_first_draw=True,
        )
        for player in (0, 1):
            self.draw_cards(state, player, 7)
            if not enable_mulligan:
                state.players[player].has_kept_opening_hand = True
        return state

    def copy_state(self, state: GameState) -> GameState:
        return copy.deepcopy(state)

    def card_def(self, state: GameState, instance_id: int):
        return self.db.get(state.cards[instance_id].card_id)

    def available_ink(self, state: GameState, player: int) -> int:
        return sum(1 for cid in state.players[player].inkwell if not state.cards[cid].exerted)

    def legal_actions(self, state: GameState, player: int | None = None) -> list[Action]:
        player = state.active_player if player is None else player
        if state.winner is not None:
            return []

        if state.phase == PHASE_MULLIGAN:
            return self._mulligan_actions(state, player) + [Action(ACTION_CONCEDE, actor=player)]

        if state.phase != PHASE_MAIN:
            return []

        # B3: Pending effect handling - chooser acts even when not active player
        if has_pending_effects(state):
            pe = get_current_pending_effect(state, player)
            if pe is not None:
                if player != pe.chooser_id:
                    return [Action(ACTION_CONCEDE, actor=player)]
                # Player is the current chooser - only RESOLVE_PENDING_EFFECT and CONCEDE are legal
                actions: list[Action] = []
                requirement = pe.current_requirement

                requirement_kind = (pe.raw or {}).get("requirement_kind")
                raw_requirement = (pe.raw or {}).get("requirement")

                if requirement_kind == "optional" and pe.accepted is None:
                    # Optional effect - can accept or decline
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": True}
                    ))
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "accept": False}
                    ))
                elif requirement_kind == "amount":
                    # Amount selection required
                    amount_options = (
                        (pe.raw or {}).get("amount_options")
                        or getattr(raw_requirement, "options", None)
                        or []
                    )
                    # Fallback: generate from min/max if provided
                    min_amount = (
                        (pe.raw or {}).get("min_amount")
                        if (pe.raw or {}).get("min_amount") is not None
                        else (pe.raw or {}).get("min", getattr(raw_requirement, "min_amount", getattr(raw_requirement, "min", 0)))
                    )
                    max_amount = (
                        (pe.raw or {}).get("max_amount")
                        if (pe.raw or {}).get("max_amount") is not None
                        else (pe.raw or {}).get("max", getattr(raw_requirement, "max_amount", getattr(raw_requirement, "max", len(amount_options))))
                    )
                    if not amount_options and max_amount > 0:
                        amount_options = list(range(min_amount, max_amount + 1))
                    for amount in amount_options:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={"pending_effect_id": pe.id, "amount": amount}
                        ))
                elif requirement_kind == "target":
                    # Single target selection - use targeting service for candidate resolution
                    candidates = get_valid_target_candidates_for_pending(state, pe, player, self)
                    card_candidates = [c for c in candidates if c.kind == "card"]
                    player_candidates = [c for c in candidates if c.kind == "player"]
                    if card_candidates:
                        for cand in card_candidates:
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                target=cand.id,
                                choice={"pending_effect_id": pe.id, "targets": (cand.id,)}
                            ))
                    if player_candidates:
                        for cand in player_candidates:
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                target=None,
                                choice={
                                    "pending_effect_id": pe.id,
                                    "target_kind": "player",
                                    "player_targets": (cand.id,),
                                    "player": cand.id,
                                }
                            ))
                elif requirement_kind == "multi_target":
                    # Multi-target selection - use targeting service, then enumerate combinations
                    service_candidates = get_valid_target_candidates_for_pending(state, pe, player, self)
                    card_cands = [c for c in service_candidates if c.kind == "card"]
                    candidate_ids = tuple(c.id for c in card_cands)
                    min_targets = (
                        (pe.raw or {}).get("min_targets")
                        if (pe.raw or {}).get("min_targets") is not None
                        else getattr(raw_requirement, "min_targets", getattr(requirement, "min_targets", 1))
                    ) or 1
                    max_targets = (
                        (pe.raw or {}).get("max_targets")
                        if (pe.raw or {}).get("max_targets") is not None
                        else getattr(raw_requirement, "max_targets", getattr(requirement, "max_targets", len(candidate_ids)))
                    )
                    if max_targets is None:
                        max_targets = len(candidate_ids)
                    # Generate all valid target combinations
                    from itertools import combinations
                    for r in range(min_targets, max_targets + 1):
                        for combo in combinations(candidate_ids, r):
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                target=combo[0] if combo else None,
                                choice={"pending_effect_id": pe.id, "targets": combo}
                            ))
                elif requirement_kind == "discard_choice":
                    # Discard choice - enumerate card combinations from hand candidates
                    card_candidates = (
                        (pe.raw or {}).get("card_candidate_ids")
                        or (pe.raw or {}).get("candidate_ids")
                        or getattr(raw_requirement, "card_candidate_ids", None)
                        or []
                    )
                    # Use raw_requirement if available, otherwise fall back to pe.raw
                    if raw_requirement is not None:
                        min_cards = getattr(raw_requirement, "min_cards", None)
                        max_cards = getattr(raw_requirement, "max_cards", None)
                    else:
                        min_cards = None
                        max_cards = None
                    if min_cards is None:
                        min_cards = (pe.raw or {}).get("min_discard", (pe.raw or {}).get("min_cards", 1))
                    if max_cards is None:
                        max_cards = (pe.raw or {}).get("max_discard", (pe.raw or {}).get("max_cards", None))
                    if max_cards is None:
                        max_cards = len(card_candidates)
                    # Filter to cards in chooser's hand
                    hand_cards = set(state.players[player].hand)
                    valid_cards = tuple(cid for cid in card_candidates if cid in hand_cards)
                    from itertools import combinations
                    for r in range(min_cards, max_cards + 1):
                        for combo in combinations(valid_cards, r):
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={"pending_effect_id": pe.id, "discard_card_ids": combo}
                            ))
                elif requirement_kind == "choice":
                    # Index-based choice selection
                    choice_options = (
                        (pe.raw or {}).get("options")
                        or getattr(raw_requirement, "options", None)
                        or list(pe.choice_options)
                    )
                    for idx, _ in enumerate(choice_options):
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={"pending_effect_id": pe.id, "choice_index": idx}
                        ))
                elif requirement_kind == "opponent_choice":
                    # Opponent makes a choice - only visible to pe.chooser_id
                    # Determine choice type from raw
                    choice_type = (pe.raw or {}).get("choice_type", "choice")
                    if choice_type == "target" or choice_type == "targets":
                        # Target-based opponent choice - use targeting service
                        candidates = get_valid_target_candidates_for_pending(state, pe, player, self)
                        card_candidates = [c for c in candidates if c.kind == "card"]
                        player_candidates = [c for c in candidates if c.kind == "player"]
                        if card_candidates:
                            for cand in card_candidates:
                                actions.append(Action(
                                    ACTION_RESOLVE_PENDING_EFFECT,
                                    actor=player,
                                    source=pe.source_id,
                                    target=cand.id,
                                    choice={"pending_effect_id": pe.id, "targets": (cand.id,)}
                                ))
                        if player_candidates:
                            for cand in player_candidates:
                                actions.append(Action(
                                    ACTION_RESOLVE_PENDING_EFFECT,
                                    actor=player,
                                    source=pe.source_id,
                                    target=None,
                                    choice={
                                        "pending_effect_id": pe.id,
                                        "target_kind": "player",
                                        "player_targets": (cand.id,),
                                        "player": cand.id,
                                    }
                                ))
                    elif choice_type == "amount":
                        amount_options = (
                            (pe.raw or {}).get("amount_options")
                            or getattr(raw_requirement, "options", None)
                            or []
                        )
                        for amount in amount_options:
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={"pending_effect_id": pe.id, "amount": amount}
                            ))
                    else:
                        # Default: choice index
                        choice_options = (
                            (pe.raw or {}).get("options")
                            or getattr(raw_requirement, "options", None)
                            or list(pe.choice_options)
                        )
                        for idx, _ in enumerate(choice_options):
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={"pending_effect_id": pe.id, "choice_index": idx}
                            ))
                elif requirement_kind == "enter_play_exerted":
                    # Enter play exerted choice - true/false
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "enter_play_exerted": True}
                    ))
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id, "enter_play_exerted": False}
                    ))
                elif requirement_kind == "scry_ordering":
                    candidate_ids = tuple(getattr(raw_requirement, "candidate_ids", ()))
                    destination_rules = tuple(getattr(raw_requirement, "destinations", ()) or ())
                    if destination_rules:
                        for destinations in self._scry_destination_choices(candidate_ids, destination_rules):
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={
                                    "pending_effect_id": pe.id,
                                    "destinations": destinations,
                                }
                            ))
                    else:
                        for ordered_cards in itertools.permutations(candidate_ids):
                            for top_count in range(len(candidate_ids) + 1):
                                actions.append(Action(
                                    ACTION_RESOLVE_PENDING_EFFECT,
                                    actor=player,
                                    source=pe.source_id,
                                    choice={
                                        "pending_effect_id": pe.id,
                                        "top_cards": ordered_cards[:top_count],
                                        "bottom_cards": ordered_cards[top_count:],
                                    }
                                ))
                elif requirement_kind == "search_selection":
                    candidate_ids = tuple(getattr(raw_requirement, "candidate_ids", ()) or pe.choice_options)
                    for selected_card_id in candidate_ids:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "selected_card_id": selected_card_id,
                            }
                        ))
                elif requirement_kind == "reveal_routing":
                    fixed_destination = getattr(raw_requirement, "destination", None)
                    destination_options = tuple(getattr(raw_requirement, "destination_options", ()) or pe.choice_options)
                    if fixed_destination:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "destination": fixed_destination,
                            }
                        ))
                    else:
                        for destination in destination_options:
                            actions.append(Action(
                                ACTION_RESOLVE_PENDING_EFFECT,
                                actor=player,
                                source=pe.source_id,
                                choice={
                                    "pending_effect_id": pe.id,
                                    "destination": destination,
                                }
                            ))
                elif requirement_kind == "named_card":
                    valid_names = tuple(getattr(raw_requirement, "valid_card_def_ids", ()) or pe.choice_options)
                    if not valid_names:
                        valid_names = tuple(card.id for card in sorted(self.db.all_cards(), key=lambda card: card.id))
                    for named_card in valid_names:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "named_card": named_card,
                            }
                        ))
                elif requirement_kind == "destination":
                    destination_options = tuple(
                        (pe.raw or {}).get("destination_options")
                        or getattr(raw_requirement, "destination_options", ())
                        or getattr(raw_requirement, "options", ())
                        or pe.choice_options
                    )
                    for destination in destination_options:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={
                                "pending_effect_id": pe.id,
                                "destination": destination,
                            }
                        ))
                elif pe.requires_target_input and requirement is not None:
                    # Target selection required
                    valid_targets = get_valid_targets_for_requirement(state, requirement, player, self)
                    for target in valid_targets:
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            target=target,
                            choice={"pending_effect_id": pe.id}
                        ))
                elif pe.requires_choice_input:
                    # Choice index selection required
                    for choice_idx in range(len(pe.choice_options)):
                        actions.append(Action(
                            ACTION_RESOLVE_PENDING_EFFECT,
                            actor=player,
                            source=pe.source_id,
                            choice={"pending_effect_id": pe.id, "choice_index": choice_idx}
                        ))
                else:
                    # No input required, just resolve
                    actions.append(Action(
                        ACTION_RESOLVE_PENDING_EFFECT,
                        actor=player,
                        source=pe.source_id,
                        choice={"pending_effect_id": pe.id}
                    ))

                actions.append(Action(ACTION_CONCEDE, actor=player))
                return actions
            else:
                # No pending effect for this player
                return [Action(ACTION_CONCEDE, actor=player)]

        # B2: Bag handling - bag resolver acts even when not active player
        if has_pending_bag_items(state):
            resolver = get_next_bag_resolver(state)
            if player != resolver:
                return [Action(ACTION_CONCEDE, actor=player)]
            # Player is the current resolver - only RESOLVE_BAG and CONCEDE are legal
            resolver_items = [
                entry for entry in state.bag
                if entry.controller_id == player or entry.chooser_id == player
            ]
            actions: list[Action] = []
            for entry in resolver_items:
                is_optional = entry.optional
                input_actions = self._bag_resolution_input_actions(state, player, entry)
                if input_actions:
                    actions.extend(input_actions)
                else:
                    actions.append(Action(
                        ACTION_RESOLVE_BAG,
                        actor=player,
                        source=entry.source_id,
                        choice={"bag_id": entry.id, "accept": True}
                    ))
                # Decline only for optional triggers
                if is_optional:
                    actions.append(Action(
                        ACTION_RESOLVE_BAG,
                        actor=player,
                        source=entry.source_id,
                        choice={"bag_id": entry.id, "accept": False}
                    ))
            actions.append(Action(ACTION_CONCEDE, actor=player))
            return actions

        if player != state.active_player:
            return []

        actions = []
        ps = state.players[player]

        extra_ink_key = f"additional_inkwell:{player}"
        extra_inks = int(state.turn_metadata.get(extra_ink_key, 0) or 0)
        if not state.turn_player_has_inked or extra_inks > 0:
            for cid in ps.hand:
                if self.card_def(state, cid).inkable:
                    actions.append(Action(ACTION_INK_CARD, actor=player, card=cid))
            if self._can_ink_from_discard(state, player):
                for cid in ps.discard:
                    if self.card_def(state, cid).inkable:
                        actions.append(Action(ACTION_INK_CARD, actor=player, card=cid))

        for cid in ps.hand:
            card = self.card_def(state, cid)
            if self.play_cost(state, player, cid) <= self.available_ink(state, player):
                if card.card_type == CARD_ACTION and self._effect_has_unsupported_target(card.effects):
                    continue
                if card.card_type == CARD_ACTION and (
                    any(self._effect_requires_target(e) for e in card.effects)
                    or self._effect_requires_slotted_targets(card.effects)
                ):
                    actions.extend(self._targeted_play_actions(state, player, cid))
                else:
                    actions.append(Action(ACTION_PLAY_CARD, actor=player, card=cid))

        # B10: Alternative play modes - Songs and Shift
        from .play_modes import (
            is_song_card, get_singer_info, can_sing_song,
            get_shift_info, get_shift_targets, can_play_as_shift,
            sing_together_groups,
        )

        # Generate SING_SONG actions for songs with singers
        for song_cid in ps.hand:
            song_card = self.card_def(state, song_cid)
            if song_card.card_type == CARD_ACTION and is_song_card(self, song_cid, state):
                # Find all singers who can sing this song
                for singer_cid in ps.play:
                    singer_info = get_singer_info(state, self, singer_cid)
                    if singer_info is not None and not singer_info.sing_together:
                        can_sing, _ = can_sing_song(state, self, singer_cid, song_cid)
                        if can_sing:
                            actions.append(Action(
                                "SING_SONG", actor=player, card=song_cid, source=singer_cid
                            ))
                for singer_group in sing_together_groups(state, self, player, song_cid):
                    actions.append(Action(
                        "SING_SONG",
                        actor=player,
                        card=song_cid,
                        source=singer_group[0],
                        choice={"mode": "singTogether", "singer_ids": singer_group},
                    ))

        # Generate PLAY_SHIFTED actions for shift characters
        for shift_cid in ps.hand:
            shift_card = self.card_def(state, shift_cid)
            if shift_card.card_type == CARD_CHARACTER:
                shift_cost = get_shift_info(state, self, shift_cid)
                if shift_cost is not None:
                    for target in get_shift_targets(state, self, shift_cid):
                        can_play, _ = can_play_as_shift(state, self, shift_cid, target.instance_id)
                        if can_play:
                            actions.append(Action(
                                "PLAY_SHIFTED", actor=player, card=shift_cid, target=target.instance_id
                            ))

        for cid in ps.play:
            if self.can_quest(state, cid):
                actions.append(Action(ACTION_QUEST, actor=player, source=cid))

        for source in ps.play:
            for target in self.challenge_targets(state, source):
                actions.append(Action(ACTION_CHALLENGE, actor=player, source=source, target=target))

        for source in ps.play:
            for location in self.location_move_targets(state, source):
                actions.append(Action(ACTION_MOVE_TO_LOCATION, actor=player, source=source, target=location))

        # B7: Activated abilities - generate USE_ABILITY actions
        from .abilities import validate_effects_supported, can_use_ability_this_turn
        for ability in get_available_abilities_for_player(state, self, player):
            # Check once-per-turn restriction
            if not can_use_ability_this_turn(state, ability):
                continue
            # Check costs are payable
            can_pay, _ = validate_ability_costs(state, self, ability)
            if not can_pay:
                continue
            # Check effects are supported (no pending prompts required)
            effects_supported, _ = validate_effects_supported(ability)
            if not effects_supported:
                continue
            slotted_actions = self._activated_ability_slotted_target_actions(state, ability, player)
            if slotted_actions is not None:
                actions.extend(slotted_actions)
                continue
            target_selections = self._activated_ability_target_selections(state, ability, player)
            if target_selections is None:
                continue
            if target_selections:
                for selected_targets in target_selections:
                    if selected_targets:
                        actions.append(Action(
                            ACTION_USE_ABILITY,
                            actor=player,
                            source=ability.source_instance_id,
                            target=selected_targets[0],
                            choice={
                                "ability_id": ability.ability_id,
                                "ability_index": ability.ability_index,
                                "targets": selected_targets,
                            },
                        ))
                    else:
                        actions.append(Action(
                            ACTION_USE_ABILITY,
                            actor=player,
                            source=ability.source_instance_id,
                            choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                        ))
            else:
                actions.append(Action(
                    ACTION_USE_ABILITY,
                    actor=player,
                    source=ability.source_instance_id,
                    choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
                ))

        actions.append(Action(ACTION_END_TURN, actor=player))
        actions.append(Action(ACTION_CONCEDE, actor=player))
        return actions

    def _activated_ability_target_selections(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> tuple[tuple[int, ...], ...] | None:
        descriptors = self._activated_ability_explicit_target_descriptors(ability)
        if not descriptors:
            return ((),)
        if len(descriptors) > 1:
            return None

        descriptor = descriptors[0]
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            enumerate_target_selections,
            resolve_candidate_targets,
        )

        context = TargetQueryContext(actor=player, source_id=ability.source_instance_id)
        candidates = apply_target_protections(
            state,
            self,
            resolve_candidate_targets(state, self, descriptor, context),
            descriptor,
            context,
        )
        availability = analyze_target_selection_availability(descriptor, candidates)
        if not availability.can_satisfy_required_selection:
            return None

        selections = enumerate_target_selections(candidates, descriptor, candidate_kind="card")
        return selections

    def _activated_ability_target_candidates(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> tuple[int, ...] | None:
        """Backward-compatible single-card candidate wrapper."""
        selections = self._activated_ability_target_selections(state, ability, player)
        if selections is None:
            return None
        return tuple(selection[0] for selection in selections if selection)

    def _activated_ability_slotted_target_actions(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> list[Action] | None:
        specs = self._move_to_location_slot_specs(ability.effects)
        if not specs:
            return None

        result: list[Action] = []
        for spec in specs:
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=player,
                source_id=ability.source_instance_id,
                spec=spec,
            ):
                subjects = tuple(slotted.get("subject", ()) or ())
                result.append(Action(
                    ACTION_USE_ABILITY,
                    actor=player,
                    source=ability.source_instance_id,
                    target=subjects[0] if subjects else None,
                    choice={
                        "ability_id": ability.ability_id,
                        "ability_index": ability.ability_index,
                        "slotted_targets": slotted,
                    },
                ))
        return result

    def _activated_ability_explicit_target_descriptors(self, ability: ActivatedAbility):
        from .targeting import normalize_target_descriptor, requires_explicit_target_selection
        descriptors = []
        for effect in ability.effects:
            target = getattr(effect, "target", None)
            if target is None:
                continue
            raw_target = getattr(target, "raw", None) or getattr(target, "alias", None) or getattr(target, "selector", None)
            descriptor = normalize_target_descriptor(raw_target)
            if descriptor is not None and requires_explicit_target_selection(descriptor.selector):
                descriptors.append(descriptor)
        return tuple(descriptors)

    def _mulligan_actions(self, state: GameState, player: int) -> list[Action]:
        ps = state.players[player]
        if ps.has_kept_opening_hand:
            return []
        actions = [Action(ACTION_KEEP_HAND, actor=player)]
        if ps.has_mulliganed:
            return actions
        hand = tuple(ps.hand)
        for count in range(1, len(hand) + 1):
            for choice in itertools.combinations(hand, count):
                actions.append(Action(ACTION_MULLIGAN, actor=player, choice=choice))
        return actions

    def _bag_resolution_input_actions(self, state: GameState, player: int, entry: BagEffectEntry) -> list[Action]:
        actions: list[Action] = []

        def target_actions(raw_target: Any, base_choice: dict[str, Any]) -> list[Action]:
            from .targeting import (
                TargetQueryContext,
                apply_target_protections,
                enumerate_target_selections,
                normalize_target_descriptor,
                resolve_candidate_targets,
            )

            desc = normalize_target_descriptor(raw_target)
            if desc is None:
                return []
            event_payload = {}
            if entry.event:
                event_payload.update(entry.event.event_snapshot or {})
                event_payload.update(entry.event.payload or {})
            chooser_actor = entry.chooser_id
            context = TargetQueryContext(actor=chooser_actor, source_id=entry.source_id, event_payload=event_payload)
            candidates = apply_target_protections(
                state,
                self,
                resolve_candidate_targets(state, self, desc, context),
                desc,
                context,
            )
            result: list[Action] = []
            for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
                choice = dict(base_choice)
                choice["targets"] = selected
                result.append(Action(
                    ACTION_RESOLVE_BAG,
                    actor=player,
                    source=entry.source_id,
                    target=selected[0] if selected else None,
                    choice=choice,
                ))
            return result

        def move_to_location_actions(effect: Any, base_choice: dict[str, Any]) -> list[Action]:
            raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
            if not isinstance(raw, dict):
                return []
            character = raw.get("character") or raw.get("subject")
            location = raw.get("location")
            if character is None or location is None:
                return []

            event_payload = {}
            if entry.event:
                event_payload.update(entry.event.event_snapshot or {})
                event_payload.update(entry.event.payload or {})

            spec = {
                "kind": "move-to-location",
                "slots": {
                    "subject": character,
                    "location": location,
                },
            }
            result: list[Action] = []
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=entry.chooser_id,
                source_id=entry.source_id,
                spec=spec,
                event_payload=event_payload,
            ):
                choice = dict(base_choice)
                choice["slotted_targets"] = slotted
                subjects = tuple(slotted.get("subject", ()) or ())
                result.append(Action(
                    ACTION_RESOLVE_BAG,
                    actor=player,
                    source=entry.source_id,
                    target=subjects[0] if subjects else None,
                    choice=choice,
                ))
            return result

        def move_damage_actions(effect: Any, base_choice: dict[str, Any]) -> list[Action]:
            raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
            if not isinstance(raw, dict):
                return []
            raw_amount = raw.get("amount")
            if not (isinstance(raw_amount, dict) and raw_amount.get("type") == "up-to"):
                return []
            maximum = min(int(raw_amount.get("value") or 0), state.cards[entry.source_id].damage)
            result: list[Action] = []
            for action in target_actions(raw.get("to"), base_choice):
                for amount in range(0, maximum + 1):
                    choice = dict(action.choice or {})
                    choice["amount"] = amount
                    result.append(Action(
                        ACTION_RESOLVE_BAG,
                        actor=action.actor,
                        source=action.source,
                        target=action.target,
                        choice=choice,
                    ))
            return result

        def put_into_inkwell_actions(effect: Any, base_choice: dict[str, Any]) -> list[Action]:
            raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
            if not isinstance(raw, dict):
                return []
            source = raw.get("source")
            if source == "hand":
                result = []
                for cid in state.players[player].hand:
                    choice = dict(base_choice)
                    choice["targets"] = (cid,)
                    result.append(Action(ACTION_RESOLVE_BAG, actor=player, source=entry.source_id, target=cid, choice=choice))
                return result
            if isinstance(source, dict):
                return target_actions(source, base_choice)
            return []

        for effect in entry.effects:
            raw = effect.raw.get("raw") if isinstance(getattr(effect, "raw", None), dict) and isinstance(effect.raw.get("raw"), dict) else getattr(effect, "raw", {}) or {}
            if effect.kind == "optional" and effect.effects:
                child = effect.effects[0]
                if getattr(child, "kind", None) == "move_to_location":
                    actions.extend(move_to_location_actions(child, {"bag_id": entry.id, "accept": True}))
                    continue
                if getattr(child, "kind", None) == "move_damage":
                    actions.extend(move_damage_actions(child, {"bag_id": entry.id, "accept": True}))
                    continue
                if getattr(child, "kind", None) == "put_into_inkwell":
                    actions.extend(put_into_inkwell_actions(child, {"bag_id": entry.id, "accept": True}))
                    continue
                if getattr(child, "kind", None) == "return_from_discard":
                    actions.extend(self._return_from_discard_bag_actions(state, player, entry, child, {"bag_id": entry.id, "accept": True}))
                    continue
                if getattr(child, "kind", None) == "pay_cost":
                    actions.extend(self._pay_cost_bag_actions(state, player, entry, child, {"bag_id": entry.id, "accept": True}))
                    continue
                if getattr(child, "kind", None) == "sequence":
                    sequence_actions = self._select_target_choice_bag_actions(state, player, entry, child, {"bag_id": entry.id, "accept": True})
                    if sequence_actions:
                        actions.extend(sequence_actions)
                        continue
                child_target = child.target
                child_raw = child.raw.get("raw") if isinstance(child.raw.get("raw"), dict) else child.raw
                raw_target = child_raw.get("target") if isinstance(child_raw, dict) and child_raw.get("target") is not None else child_target
                actions.extend(target_actions(raw_target, {"bag_id": entry.id, "accept": True}))
            elif effect.kind == "choice" and effect.effects:
                for idx, branch in enumerate(effect.effects):
                    branch_raw = branch.raw.get("raw") if isinstance(branch.raw.get("raw"), dict) else branch.raw
                    raw_target = branch_raw.get("target") if isinstance(branch_raw, dict) and branch_raw.get("target") is not None else branch.target
                    from .targeting import normalize_target_descriptor, requires_explicit_target_selection
                    desc = normalize_target_descriptor(raw_target)
                    base = {"bag_id": entry.id, "accept": True, "choice_index": idx}
                    if desc is not None and requires_explicit_target_selection(desc.selector):
                        actions.extend(target_actions(raw_target, base))
                    else:
                        actions.append(Action(ACTION_RESOLVE_BAG, actor=player, source=entry.source_id, choice=base))
            elif isinstance(raw.get("amount"), dict) and raw["amount"].get("type") == "lore-value-of":
                actions.extend(target_actions(raw["amount"].get("target"), {"bag_id": entry.id, "accept": True}))
            elif effect.kind == "move_to_location":
                actions.extend(move_to_location_actions(effect, {"bag_id": entry.id, "accept": True}))

        return actions

    def _return_from_discard_bag_actions(
        self,
        state: GameState,
        player: int,
        entry: BagEffectEntry,
        effect: Any,
        base_choice: dict[str, Any],
    ) -> list[Action]:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if not isinstance(raw, dict) or raw.get("target") not in {"CONTROLLER", "controller"}:
            return []
        card_type = raw.get("cardType")
        result: list[Action] = []
        for cid in state.players[entry.controller_id].discard:
            if card_type and self.card_def(state, cid).card_type != card_type:
                continue
            choice = dict(base_choice)
            choice["targets"] = (cid,)
            result.append(Action(ACTION_RESOLVE_BAG, actor=player, source=entry.source_id, target=cid, choice=choice))
        return result

    def _pay_cost_bag_actions(
        self,
        state: GameState,
        player: int,
        entry: BagEffectEntry,
        effect: Any,
        base_choice: dict[str, Any],
    ) -> list[Action]:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if not isinstance(raw, dict):
            return []
        cost = raw.get("cost")
        child = raw.get("effect")
        if not (isinstance(cost, dict) and set(cost) == {"ink"} and isinstance(child, dict)):
            return []
        if self.available_ink(state, entry.controller_id) < int(cost.get("ink") or 0):
            return []
        target = child.get("target")
        return self._bag_target_actions_from_raw(state, player, entry, target, base_choice)

    def _select_target_choice_bag_actions(
        self,
        state: GameState,
        player: int,
        entry: BagEffectEntry,
        effect: Any,
        base_choice: dict[str, Any],
    ) -> list[Action]:
        children = tuple(getattr(effect, "effects", ()) or ())
        if len(children) != 2 or getattr(children[0], "kind", None) != "select_target" or getattr(children[1], "kind", None) != "choice":
            return []
        choice_count = len(getattr(children[1], "effects", ()) or ())
        result: list[Action] = []
        for action in self._bag_target_actions_from_raw(state, player, entry, getattr(children[0], "target", None), base_choice):
            for idx in range(choice_count):
                choice = dict(action.choice or {})
                choice["choice_index"] = idx
                result.append(Action(ACTION_RESOLVE_BAG, actor=action.actor, source=action.source, target=action.target, choice=choice))
        return result

    def _bag_target_actions_from_raw(
        self,
        state: GameState,
        player: int,
        entry: BagEffectEntry,
        raw_target: Any,
        base_choice: dict[str, Any],
    ) -> list[Action]:
        from .targeting import (
            TargetQueryContext,
            apply_target_protections,
            enumerate_target_selections,
            normalize_target_descriptor,
            resolve_candidate_targets,
        )

        desc = normalize_target_descriptor(raw_target)
        if desc is None:
            return []
        context = TargetQueryContext(actor=entry.chooser_id, source_id=entry.source_id, event_payload={})
        candidates = apply_target_protections(state, self, resolve_candidate_targets(state, self, desc, context), desc, context)
        result = []
        for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
            choice = dict(base_choice)
            choice["targets"] = selected
            result.append(Action(
                ACTION_RESOLVE_BAG,
                actor=player,
                source=entry.source_id,
                target=selected[0] if selected else None,
                choice=choice,
            ))
        return result

    def can_quest(self, state: GameState, source: int) -> bool:
        inst = state.cards[source]
        if inst.zone != ZONE_PLAY or inst.controller != state.active_player:
            return False
        card = self.card_def(state, source)
        if card.card_type != CARD_CHARACTER:
            return False
        if inst.exerted or inst.drying:
            return False
        if source in set(state.turn_metadata.get("cant_quest_until_turn_end", ()) or ()):
            return False
        if self.has_keyword(state, source, KEYWORD_RECKLESS):
            return False
        # B7.1: Check static quest restrictions
        from .static_effects import can_quest as static_can_quest
        if not static_can_quest(state, source):
            return False
        return True

    def challenge_targets(self, state: GameState, source: int) -> list[int]:
        inst = state.cards[source]
        player = inst.controller
        if inst.zone != ZONE_PLAY or player != state.active_player:
            return []
        source_def = self.card_def(state, source)
        if source_def.card_type != CARD_CHARACTER:
            return []
        if inst.exerted:
            return []
        if inst.drying and not self.has_keyword(state, source, KEYWORD_RUSH):
            return []
        # B7.1: Check static challenge restriction - if source cannot challenge, return empty
        from .static_effects import can_challenge as static_can_challenge
        if not static_can_challenge(state, source):
            return []

        opponent = state.opponent(player)
        character_candidates: list[int] = []
        bodyguards: list[int] = []
        location_candidates: list[int] = []
        for target in state.players[opponent].play:
            target_inst = state.cards[target]
            target_def = self.card_def(state, target)
            if target_def.card_type == CARD_CHARACTER:
                if not target_inst.exerted:
                    continue
                if self.has_keyword(state, target, KEYWORD_EVASIVE) and not self.has_keyword(state, source, KEYWORD_EVASIVE):
                    continue
                # B8: Check cannot-be-challenged restriction
                if check_cannot_be_challenged(state, target, source):
                    continue
                if self.has_keyword(state, target, KEYWORD_BODYGUARD):
                    bodyguards.append(target)
                character_candidates.append(target)
            elif target_def.card_type == CARD_LOCATION:
                location_candidates.append(target)

        # Bodyguard only redirects challenge options when an opposing bodyguard
        # character is itself a legal challenge target.
        if bodyguards:
            return bodyguards
        return character_candidates + location_candidates

    def location_move_targets(self, state: GameState, source: int) -> list[int]:
        inst = state.cards[source]
        player = inst.controller
        if inst.zone != ZONE_PLAY or player != state.active_player:
            return []
        source_def = self.card_def(state, source)
        if source_def.card_type != CARD_CHARACTER:
            return []

        available = self.available_ink(state, player)
        targets: list[int] = []
        for target in state.players[player].play:
            target_def = self.card_def(state, target)
            if target_def.card_type != CARD_LOCATION:
                continue
            if inst.location_instance_id == target:
                continue
            if int(target_def.move_cost or 0) <= available:
                targets.append(target)
        return targets

    def resist_value(self, card) -> int:
        values: list[int] = []
        for ability in getattr(card, "abilities", ()):
            if isinstance(ability, dict) and str(ability.get("keyword", "")).strip().lower() == "resist":
                number = ability.get("keywordValueNumber")
                if isinstance(number, int):
                    values.append(number)
                elif isinstance(number, str) and number.lstrip("+").isdigit():
                    values.append(int(number.lstrip("+")))
        for keyword in getattr(card, "keywords", ()):
            key = str(keyword).upper()
            if key == KEYWORD_RESIST:
                values.append(1)
            elif key.startswith(f"{KEYWORD_RESIST}:"):
                suffix = key.split(":", 1)[1]
                if suffix.isdigit():
                    values.append(int(suffix))
        return max(values, default=0)

    def _damage_after_resist(self, target_card, amount: int) -> int:
        return max(0, amount - self.resist_value(target_card))

    def damage_after_resist(self, target_card, amount: int) -> int:
        return self._damage_after_resist(target_card, amount)

    def keywords_for_instance(self, state: GameState, instance_id: int) -> tuple[str, ...]:
        """Get all keywords including static grants and printed keywords."""
        card = self.card_def(state, instance_id)
        keywords = set(card.keywords)
        keywords.update(state.cards[instance_id].temporary_keywords)
        # Add static keyword grants
        for effect in state.static_effect_registry.get_effects_for_instance(state, instance_id):
            if effect.effect_type == StaticEffectType.GRANT_KEYWORD and effect.keyword:
                keywords.add(effect.keyword)
        return tuple(sorted(keywords))

    def has_keyword(self, state: GameState, instance_id: int, keyword: str) -> bool:
        return keyword in self.keywords_for_instance(state, instance_id)

    def effective_strength(self, state: GameState, instance_id: int) -> int:
        """Calculate effective strength including static modifiers."""
        card = self.card_def(state, instance_id)
        base = int(card.strength or 0)
        temp_modifier = state.cards[instance_id].temporary_modifiers.get("strength", 0)
        # Get static modifiers from registry
        static_modifier = 0
        for effect in state.static_effect_registry.get_effects_for_instance(state, instance_id):
            if effect.effect_type == StaticEffectType.MODIFY_STRENGTH:
                static_modifier += effect.amount
        return max(0, base + static_modifier + temp_modifier)

    def effective_willpower(self, state: GameState, instance_id: int) -> int:
        """Calculate effective willpower including static modifiers."""
        card = self.card_def(state, instance_id)
        base = int(card.willpower or 0)
        temp_modifier = state.cards[instance_id].temporary_modifiers.get("willpower", 0)
        # Get static modifiers from registry
        static_modifier = 0
        for effect in state.static_effect_registry.get_effects_for_instance(state, instance_id):
            if effect.effect_type == StaticEffectType.MODIFY_WILLPOWER:
                static_modifier += effect.amount
        return max(0, base + static_modifier + temp_modifier)

    def effective_lore(self, state: GameState, instance_id: int) -> int:
        """Calculate effective lore including static and temporary modifiers."""
        card = self.card_def(state, instance_id)
        base = int(card.lore or 0)
        temp_modifier = state.cards[instance_id].temporary_modifiers.get("lore", 0)
        static_modifier = 0
        for effect in state.static_effect_registry.get_effects_for_instance(state, instance_id):
            if effect.effect_type == StaticEffectType.MODIFY_LORE:
                static_modifier += effect.amount
        return max(0, base + static_modifier + temp_modifier)

    def play_cost(self, state: GameState, player: int, instance_id: int) -> int:
        """Calculate play cost including static cost reductions."""
        card = self.card_def(state, instance_id)
        reductions = self._applicable_cost_reductions(state, player, card.card_type)
        hand_source_reduction = self._hand_source_cost_reduction(state, player, instance_id)
        if hand_source_reduction:
            reductions.append({"amount": hand_source_reduction, "card_type": card.card_type, "source_id": instance_id})
        # Add static cost reductions
        for effect in state.static_effect_registry.effects:
            source_inst = state.cards.get(effect.source_id)
            if source_inst is None or source_inst.controller != player:
                continue
            if source_inst.zone != ZONE_PLAY:
                continue
            if effect.effect_type == StaticEffectType.COST_REDUCTION:
                card_type = effect.cost_reduction_card_type
                if card_type is None or card_type == card.card_type:
                    reductions.append({
                        "amount": effect.cost_reduction_amount,
                        "card_type": card_type,
                        "source_id": effect.source_id,
                    })
        return max(0, int(card.cost) - sum(int(reduction.get("amount", 0)) for reduction in reductions))

    def _hand_source_cost_reduction(self, state: GameState, player: int, instance_id: int) -> int:
        inst = state.cards.get(instance_id)
        if inst is None or inst.zone != ZONE_HAND or inst.controller != player:
            return 0
        card = self.card_def(state, instance_id)
        total = 0
        for ability in getattr(card, "source_abilities", ()) or ():
            if getattr(ability, "kind", None) != "static" or "hand" not in tuple(getattr(ability, "source_zones", ()) or ()):
                continue
            for effect in getattr(ability, "effects", ()) or ():
                raw = getattr(effect, "raw", {}) or {}
                if getattr(effect, "kind", None) != "cost-reduction":
                    continue
                amount = raw.get("amount")
                if isinstance(amount, dict) and amount.get("type") == "filtered-count":
                    count = self._count_filtered_cost_reduction_sources(state, player, amount)
                    total += count * int(amount.get("multiplier", 1) or 1)
                elif isinstance(amount, dict) and amount.get("type") == "characters-in-play":
                    controller = player if amount.get("controller") in {None, "you"} else state.opponent(player)
                    total += sum(1 for cid in state.players[controller].play if self.card_def(state, cid).card_type == CARD_CHARACTER)
                elif amount is not None:
                    if isinstance(amount, str) and amount == "full":
                        total += int(card.cost)
                    else:
                        total += int(amount)
        return total

    def _count_filtered_cost_reduction_sources(self, state: GameState, player: int, amount: dict[str, Any]) -> int:
        zones = amount.get("zones") or ("play",)
        if isinstance(zones, str):
            zones = (zones,)
        card_type = amount.get("cardType") or amount.get("card_type")
        owner = amount.get("owner")
        filters = amount.get("filters") or amount.get("filter") or ()
        if isinstance(filters, dict):
            filters = (filters,)
        total = 0
        for cid, inst in state.cards.items():
            if inst.zone not in zones:
                continue
            if owner == "you" and inst.owner != player:
                continue
            if owner == "opponent" and inst.owner != state.opponent(player):
                continue
            cdef = self.card_def(state, cid)
            if card_type and cdef.card_type != card_type:
                continue
            matched = True
            for filter_def in filters:
                if filter_def.get("type") == "has-name":
                    expected = str(filter_def.get("name") or "")
                    if cdef.full_name != expected and cdef.name != expected:
                        matched = False
                        break
            if matched:
                total += 1
        return total


    def apply_action(self, state: GameState, action: Action, *, validate: bool = True) -> GameState:
        if (
            validate
            and action not in self.legal_actions(state, action.actor)
            and not self._is_legal_resolve_bag_input_action(state, action)
        ):
            raise IllegalActionError(f"Illegal action: {action.compact()}")
        next_state = self.copy_state(state)
        log_phase = state.phase
        log_turn_number = state.turn_number
        if action.kind == ACTION_RESOLVE_BAG:
            self._apply_resolve_bag(next_state, action)
        elif action.kind == ACTION_INK_CARD:
            self._apply_ink(next_state, action)
        elif action.kind == ACTION_PLAY_CARD:
            self._apply_play(next_state, action)
        elif action.kind == ACTION_QUEST:
            self._apply_quest(next_state, action)
        elif action.kind == ACTION_CHALLENGE:
            self._apply_challenge(next_state, action)
        elif action.kind == ACTION_MOVE_TO_LOCATION:
            self._apply_move_to_location(next_state, action)
        elif action.kind == ACTION_END_TURN:
            self._apply_end_turn(next_state, action)
        elif action.kind == ACTION_KEEP_HAND:
            self._apply_keep_hand(next_state, action)
        elif action.kind == ACTION_MULLIGAN:
            self._apply_mulligan(next_state, action)
        elif action.kind == ACTION_CONCEDE:
            self._apply_concede(next_state, action)
        elif action.kind == ACTION_RESOLVE_PENDING_EFFECT:
            self._apply_resolve_pending_effect(next_state, action)
        elif action.kind == ACTION_USE_ABILITY:
            self._apply_use_ability(next_state, action)
        # B10: Alternative play mode dispatch
        elif action.kind == "SING_SONG":
            self._apply_sing_song(next_state, action)
        elif action.kind == "PLAY_SHIFTED":
            self._apply_play_shifted(next_state, action)
        else:
            raise IllegalActionError(f"Unhandled action kind {action.kind}")

        next_state.action_log.append(ActionLogEntry(turn_number=log_turn_number, phase=log_phase, action=action))

        # B2: Resolution boundary - resolve banishes first, then flush triggers
        self.resolve_banishes(next_state)
        flush_triggered_events_to_bag(next_state, self)
        self.resolve_win_loss(next_state)
        if next_state.winner is not None:
            next_state.phase = PHASE_GAME_OVER
        return next_state

    def _is_legal_resolve_bag_input_action(self, state: GameState, action: Action) -> bool:
        if action.kind != ACTION_RESOLVE_BAG or not action.choice:
            return False
        bag_id = action.choice.get("bag_id")
        if bag_id is None:
            return False
        entry = next((item for item in state.bag if item.id == bag_id), None)
        if entry is None:
            return False
        resolver = get_next_bag_resolver(state)
        if resolver is not None and action.actor != resolver:
            return False
        if action.actor != entry.controller_id and action.actor != entry.chooser_id:
            return False
        if action.choice.get("accept") is False and not entry.optional:
            return False
        return True

    def observe(self, state: GameState, player: int) -> Observation:
        opponent = state.opponent(player)
        public: dict[int, dict] = {}
        for cid, inst in state.cards.items():
            if inst.zone in {ZONE_PLAY, ZONE_DISCARD} or (inst.zone == ZONE_INKWELL and inst.controller == player) or (inst.zone == ZONE_HAND and inst.controller == player):
                cdef = self.card_def(state, cid)
                public[cid] = {
                    "card_id": cdef.id,
                    "name": cdef.full_name,
                    "zone": inst.zone,
                    "controller": inst.controller,
                    "exerted": inst.exerted,
                    "drying": inst.drying,
                    "damage": inst.damage,
                    "just_played": inst.just_played,
                    "has_quested_this_turn": inst.has_quested_this_turn,
                    "added_to_ink_this_turn": inst.added_to_ink_this_turn,
                }
        return Observation(
            player=player,
            active_player=state.active_player,
            turn_number=state.turn_number,
            own_lore=state.players[player].lore,
            opponent_lore=state.players[opponent].lore,
            own_deck_count=len(state.players[player].deck),
            opponent_deck_count=len(state.players[opponent].deck),
            own_hand=tuple(state.players[player].hand),
            opponent_hand_count=len(state.players[opponent].hand),
            own_play=tuple(state.players[player].play),
            opponent_play=tuple(state.players[opponent].play),
            own_ink_count=len(state.players[player].inkwell),
            own_available_ink=self.available_ink(state, player),
            opponent_ink_count=len(state.players[opponent].inkwell),
            cards_public=public,
        )

    def draw_cards(self, state: GameState, player: int, count: int, *, private: bool = False) -> list[int]:
        """Draw cards from the deck to hand.

        Args:
            state: The game state
            player: The player drawing cards
            count: Number of cards to draw
            private: If True, card identities are hidden from opponents in logs
                    (used for effect-driven draws where opponents shouldn't see the card)

        Returns:
            List of drawn card instance IDs (for event tracking)
        """
        ps = state.players[player]
        drawn_ids: list[int] = []
        for _ in range(count):
            if not ps.deck:
                state.winner = state.opponent(player)
                state.loss_reason = f"player_{player}_could_not_draw"
                return drawn_ids
            cid = ps.deck.pop(0)
            inst = state.cards[cid]
            inst.zone = ZONE_HAND
            inst.controller = player
            inst.revealed = False
            ps.hand.append(cid)
            drawn_ids.append(cid)

        # B13: Record cards drawn for turn metadata
        if "cards_drawn_this_turn_by_player" not in state.turn_metadata:
            state.turn_metadata["cards_drawn_this_turn_by_player"] = {}
        player_draws = state.turn_metadata["cards_drawn_this_turn_by_player"]
        player_draws[player] = player_draws.get(player, 0) + count

        # Emit CARD_DRAWN event with appropriate privacy level
        # In private mode, we don't leak the card identities to opponent
        if private:
            # Only emit safe metadata - count only, no card IDs
            self.emit_event(
                state,
                EVENT_CARD_DRAWN,
                actor=player,
                payload={
                    "count": count,
                    "private": True,
                },
            )
        else:
            # Full metadata - this is a manual/turn-start draw where reveal is expected
            self.emit_event(
                state,
                EVENT_CARD_DRAWN,
                actor=player,
                payload={
                    "count": count,
                    "card_ids": drawn_ids,
                    "private": False,
                },
            )

        return drawn_ids

    def emit_event(
        self,
        state: GameState,
        event_type: str,
        *,
        actor: int | None = None,
        source: int | None = None,
        target: int | None = None,
        payload: dict[str, Any] | None = None,
        queue_triggers: bool = True,
    ) -> GameEvent:
        """Central event emission method that also buffers triggers.

        This is the single entry point for all game events that should
        potentially trigger triggered abilities.
        """
        event = GameEvent(
            event_type=event_type,
            actor=actor,
            source=source,
            target=target,
            payload=payload or {},
            turn=state.turn_number,
            ply=len(state.action_log),
            controller=actor,
            source_card_id=state.cards[source].card_id if source and source in state.cards else None,
            target_card_id=state.cards[target].card_id if target and target in state.cards else None,
        )

        # Append to event log
        state.event_log.append(event)

        # Buffer for trigger matching if not a diagnostic event
        if queue_triggers and event_type not in _DIAGNOSTIC_EVENTS:
            buffer_trigger_event(state, event)

        return event

    def _move_card_eventful(
        self,
        state: GameState,
        card_id: int,
        destination: str,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        controller: int | None = None,
        event_type: str | None = None,
        payload: dict[str, Any] | None = None,
        queue_triggers: bool = True,
        index: int | None = None,
        include_stack: bool = True,
    ) -> tuple[str, str]:
        """Move one card through the engine event boundary."""
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        if destination not in {ZONE_DECK, ZONE_HAND, ZONE_PLAY, ZONE_DISCARD, ZONE_INKWELL, ZONE_LIMBO, ZONE_UNDER}:
            raise IllegalActionError(f"Unknown destination zone {destination}")

        inst = state.cards[card_id]
        from_zone = inst.zone
        owner = inst.owner
        from_controller = inst.controller
        resolved_actor = actor if actor is not None else from_controller
        stacked_card_ids = [card_id]
        if include_stack and from_zone == ZONE_PLAY and destination != ZONE_PLAY and inst.cards_under:
            stacked_card_ids.extend(cid for cid in inst.cards_under if cid in state.cards)

        if from_zone == ZONE_PLAY and destination != ZONE_PLAY:
            for moved_id in stacked_card_ids:
                deregister_static_effects_for_card(state, moved_id)
                deregister_replacement_effects_from_card(state, moved_id)

        leaving_location_ids: set[int] = set()
        if from_zone == ZONE_PLAY and destination != ZONE_PLAY:
            for moved_id in stacked_card_ids:
                try:
                    if self.card_def(state, moved_id).card_type == CARD_LOCATION:
                        leaving_location_ids.add(moved_id)
                except KeyError:
                    continue
        if leaving_location_ids:
            for other in state.cards.values():
                if other.location_instance_id in leaving_location_ids:
                    other.location_instance_id = None

        state.move_card(card_id, destination, controller=controller, index=index)
        for stacked_id in stacked_card_ids[1:]:
            stacked_controller = controller if controller is not None else state.cards[stacked_id].controller
            state.move_card(stacked_id, destination, controller=stacked_controller)
        if len(stacked_card_ids) > 1:
            for stacked_id in stacked_card_ids:
                stacked = state.cards[stacked_id]
                stacked.cards_under.clear()
                stacked.stack_parent_id = None
                stacked.played_via_shift = False
                stacked.played_cost_type = None
        to_controller = state.cards[card_id].controller

        if event_type is not None:
            event_payload = {
                "player_id": resolved_actor,
                "card_id": card_id,
                "subject_card_id": card_id,
                "owner_id": owner,
                "from_controller": from_controller,
                "controller_id": to_controller,
                "from_zone": from_zone,
                "to_zone": destination,
                "moved_card_ids": list(stacked_card_ids),
            }
            if source_id is not None:
                event_payload["source_card_id"] = source_id
                event_payload["trigger_source_card_id"] = source_id
            if payload:
                event_payload.update(payload)
            self.emit_event(
                state,
                event_type,
                actor=resolved_actor,
                source=source_id if source_id is not None else card_id,
                target=card_id if source_id is not None else None,
                payload=event_payload,
                queue_triggers=queue_triggers,
            )

        if from_zone == ZONE_DISCARD and destination != ZONE_DISCARD:
            self.emit_event(
                state,
                EVENT_CARD_LEFT_DISCARD,
                actor=resolved_actor,
                source=source_id if source_id is not None else card_id,
                target=card_id if source_id is not None else None,
                payload={
                    "player_id": resolved_actor,
                    "card_id": card_id,
                    "subject_card_id": card_id,
                    "source_card_id": source_id,
                    "trigger_source_card_id": source_id if source_id is not None else card_id,
                    "owner_id": owner,
                    "from_controller": from_controller,
                    "controller_id": to_controller,
                    "from_zone": from_zone,
                    "to_zone": destination,
                },
                queue_triggers=queue_triggers,
            )

        return from_zone, destination

    def _discard_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        reason: str | None = None,
        queue_triggers: bool = True,
    ) -> None:
        """Discard one card and emit CARD_DISCARDED."""
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        if state.cards[card_id].zone != ZONE_HAND:
            raise IllegalActionError("Discard target must be in hand")
        payload = {"reason": reason} if reason else None
        self._move_card_eventful(
            state,
            card_id,
            ZONE_DISCARD,
            actor=actor,
            source_id=source_id,
            event_type=EVENT_CARD_DISCARDED,
            payload=payload,
            queue_triggers=queue_triggers,
        )

    def _return_to_hand_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        queue_triggers: bool = True,
    ) -> None:
        """Return one card to its owner's hand and emit CARD_RETURNED_TO_HAND."""
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        owner = state.cards[card_id].owner
        self._move_card_eventful(
            state,
            card_id,
            ZONE_HAND,
            actor=actor if actor is not None else owner,
            source_id=source_id,
            controller=owner,
            event_type=EVENT_CARD_RETURNED_TO_HAND,
            payload={"owner_id": owner},
            queue_triggers=queue_triggers,
        )

    def _banish_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        reason: str | None = None,
        happened_in_challenge: bool = False,
        queue_triggers: bool = True,
    ) -> None:
        """Banish one card through replacement handling and emit CHARACTER_BANISHED.

        This is the authoritative banish helper. It:
        1. Evaluates replacement effects (via banish_card)
        2. Deregisters static/replacement effects if leaving play
        3. Performs the actual card move
        4. Emits the banish event
        """
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        inst = state.cards[card_id]
        controller = inst.controller
        from_zone = inst.zone
        card_type = self.card_def(state, card_id).card_type
        resolved_actor = actor if actor is not None else controller

        # Evaluate replacement effects - this does NOT move the card
        banish_event = replacement_banish_card(
            state,
            target_id=card_id,
            source_id=source_id,
            default_destination=ZONE_DISCARD,
        )

        # Perform the actual move through the engine-owned zone boundary.
        self._move_card_eventful(
            state,
            card_id,
            banish_event.actual_destination,
            actor=resolved_actor,
            controller=controller,
            queue_triggers=False,
        )

        challenge_context = {}
        if happened_in_challenge and isinstance(state.turn_metadata.get("active_challenge"), dict):
            challenge_context = dict(state.turn_metadata["active_challenge"])

        attacker_id = challenge_context.get("attacker_id")
        defender_id = challenge_context.get("defender_id")
        is_challenged_defender = happened_in_challenge and defender_id == card_id

        banish_payload = {
            "player_id": resolved_actor,
            "card_id": card_id,
            "subject_card_id": card_id,
            "source_card_id": source_id,
            "trigger_source_card_id": source_id if source_id is not None else card_id,
            "owner_id": inst.owner,
            "controller_id": controller,
            "from_zone": from_zone,
            "to_zone": banish_event.actual_destination,
            "happened_in_challenge": happened_in_challenge,
            "banished_card_type": card_type,
            "reason": reason,
            "was_replaced": banish_event.was_replaced,
            "replacement_description": banish_event.replacement_description,
            **challenge_context,
        }

        if is_challenged_defender:
            self.emit_event(
                state,
                EVENT_CHALLENGED_AND_BANISHED,
                actor=resolved_actor,
                source=card_id,
                target=card_id,
                payload={
                    **banish_payload,
                    "trigger_source_card_id": card_id,
                    "attacker_id": attacker_id,
                    "defender_id": defender_id,
                    "happened_in_challenge": True,
                },
                queue_triggers=queue_triggers,
            )

        self.emit_event(
            state,
            EVENT_CHARACTER_BANISHED,
            actor=resolved_actor,
            source=source_id if source_id is not None else card_id,
            target=card_id if source_id is not None else None,
            payload=banish_payload,
            queue_triggers=queue_triggers,
        )

        if happened_in_challenge:
            self.emit_event(
                state,
                EVENT_BANISH_IN_CHALLENGE,
                actor=resolved_actor,
                source=source_id if source_id is not None else card_id,
                target=card_id if source_id is not None else None,
                payload={
                    **banish_payload,
                    "happened_in_challenge": True,
                },
                queue_triggers=queue_triggers,
            )

        # B13: Record banish for turn metadata (only for character cards)
        if card_type == CARD_CHARACTER:
            if "banished_characters_this_turn" not in state.turn_metadata:
                state.turn_metadata["banished_characters_this_turn"] = []
            state.turn_metadata["banished_characters_this_turn"].append(card_id)

            if happened_in_challenge:
                if "banished_characters_in_challenge_by_owner_this_turn" not in state.turn_metadata:
                    state.turn_metadata["banished_characters_in_challenge_by_owner_this_turn"] = {}
                owner = inst.owner
                owner_banishes = state.turn_metadata["banished_characters_in_challenge_by_owner_this_turn"]
                if owner not in owner_banishes:
                    owner_banishes[owner] = []
                owner_banishes[owner].append(card_id)

    def _put_into_inkwell_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int,
        source_id: int | None = None,
        queue_triggers: bool = True,
        exerted: bool = False,
    ) -> None:
        """Put one card into its controller's inkwell and emit INKED."""
        self._move_card_eventful(
            state,
            card_id,
            ZONE_INKWELL,
            actor=actor,
            source_id=source_id,
            controller=actor,
            event_type=EVENT_INKED,
            payload={"card_def_id": state.cards[card_id].card_id},
            queue_triggers=queue_triggers,
        )
        state.cards[card_id].exerted = exerted
        state.cards[card_id].added_to_ink_this_turn = True

    def _ready_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        emit_event: bool = True,
        queue_triggers: bool = True,
    ) -> None:
        """Ready one card and optionally emit CARD_READIED.

        Set emit_event=False when readying is part of a compound action
        (end turn readying) where a single event covers all readyings.
        """
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        inst = state.cards[card_id]
        inst.exerted = False
        if not emit_event:
            return
        resolved_actor = actor if actor is not None else inst.controller
        self.emit_event(
            state,
            EVENT_CARD_READIED,
            actor=resolved_actor,
            source=source_id if source_id is not None else card_id,
            target=card_id if source_id is not None else None,
            payload={
                "player_id": resolved_actor,
                "card_id": card_id,
                "subject_card_id": card_id,
                "source_card_id": source_id,
                "trigger_source_card_id": source_id if source_id is not None else card_id,
                "owner_id": inst.owner,
                "controller_id": inst.controller,
            },
            queue_triggers=queue_triggers,
        )

    def _exert_eventful(
        self,
        state: GameState,
        card_id: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        reason: str | None = None,
        emit_event: bool = True,
        queue_triggers: bool = True,
    ) -> None:
        """Exert one card and optionally emit CARD_EXERTED.

        Set emit_event=False when exerting is part of a compound action
        (quest, challenge, sing) where the parent action emits the event.
        """
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        inst = state.cards[card_id]
        inst.exerted = True
        if not emit_event:
            return
        resolved_actor = actor if actor is not None else inst.controller
        self.emit_event(
            state,
            EVENT_CARD_EXERTED,
            actor=resolved_actor,
            source=source_id if source_id is not None else card_id,
            target=card_id if source_id is not None else None,
            payload={
                "player_id": resolved_actor,
                "card_id": card_id,
                "subject_card_id": card_id,
                "source_card_id": source_id,
                "trigger_source_card_id": source_id if source_id is not None else card_id,
                "owner_id": inst.owner,
                "controller_id": inst.controller,
                "reason": reason,
            },
            queue_triggers=queue_triggers,
        )

    def _gain_lore_eventful(
        self,
        state: GameState,
        player: int,
        amount: int,
        *,
        source_id: int | None = None,
        emit_event: bool = True,
        queue_triggers: bool = True,
    ) -> None:
        """Gain lore and emit a gain-lore trigger payload.

        Set emit_event=False when gaining lore is part of a compound action
        (quest, location lore) where the parent action emits a more specific event.
        """
        amount = int(amount)
        if amount <= 0:
            return
        state.players[player].lore += amount
        if not emit_event:
            return
        self.emit_event(
            state,
            EVENT_LORE_GAINED,
            actor=player,
            source=source_id,
            payload={
                "player_id": player,
                "source_card_id": source_id,
                "trigger_source_card_id": source_id,
                "lore": amount,
                "lore_gained": amount,
            },
            queue_triggers=queue_triggers,
        )

    def _lose_lore_eventful(
        self,
        state: GameState,
        player: int,
        amount: int,
        *,
        source_id: int | None = None,
        queue_triggers: bool = True,
    ) -> None:
        """Lose lore, floored at zero, and emit a lore-lost payload."""
        amount = int(amount)
        if amount <= 0:
            return
        before = state.players[player].lore
        lost = min(before, amount)
        state.players[player].lore = before - lost
        if lost <= 0:
            return
        self.emit_event(
            state,
            EVENT_LORE_LOST,
            actor=player,
            source=source_id,
            payload={
                "player_id": player,
                "source_card_id": source_id,
                "trigger_source_card_id": source_id,
                "lore": lost,
                "lore_lost": lost,
            },
            queue_triggers=queue_triggers,
        )

    def _remove_damage_eventful(
        self,
        state: GameState,
        card_id: int,
        amount: int,
        *,
        actor: int | None = None,
        source_id: int | None = None,
        queue_triggers: bool = True,
    ) -> int:
        """Remove damage from one card and emit a Lorcanito-aligned remove-damage event."""
        if card_id not in state.cards:
            raise IllegalActionError(f"Unknown card instance {card_id}")
        amount = int(amount)
        if amount <= 0:
            return 0
        inst = state.cards[card_id]
        removed = min(inst.damage, amount)
        if removed <= 0:
            return 0
        inst.damage -= removed
        resolved_actor = actor if actor is not None else inst.controller
        self.emit_event(
            state,
            EVENT_DAMAGE_REMOVED,
            actor=resolved_actor,
            source=source_id,
            target=card_id,
            payload={
                "player_id": resolved_actor,
                "card_id": card_id,
                "subject_card_id": card_id,
                "source_card_id": source_id,
                "trigger_source_card_id": source_id if source_id is not None else card_id,
                "damage_removed": removed,
                "healedAmount": removed,
                "triggerAmount": removed,
            },
            queue_triggers=queue_triggers,
        )
        return removed

    def _deal_damage_eventful(
        self,
        state: GameState,
        *,
        target_id: int,
        source_id: int | None,
        amount: int,
        actor: int | None = None,
        is_challenge: bool = False,
        apply_resist: bool = True,
    ):
        """Apply damage through replacement/prevention and emit DAMAGE_DEALT.

        `amount` is raw damage unless `apply_resist=False`. Challenge code already
        calculates challenge damage after resist, so it must pass apply_resist=False.
        Effect damage should usually pass apply_resist=True.
        """
        target_inst = state.cards.get(target_id)
        if target_inst is None:
            return replacement_deal_damage(
                state,
                target_id=target_id,
                source_id=source_id,
                amount=amount,
                is_challenge=is_challenge,
            )

        raw_amount = int(amount)
        final_input_amount = raw_amount
        if apply_resist:
            target_def = self.card_def(state, target_id)
            final_input_amount = self._damage_after_resist(target_def, raw_amount)
        static_prevented = self._static_prevented_damage_amount(
            state,
            target_id=target_id,
            amount=final_input_amount,
            is_challenge=is_challenge,
        )
        if static_prevented:
            final_input_amount = max(0, final_input_amount - static_prevented)

        damage_event = replacement_deal_damage(
            state,
            target_id=target_id,
            source_id=source_id,
            amount=final_input_amount,
            is_challenge=is_challenge,
        )

        # Lorcanito parity: if final damage is 0 or less after Resist,
        # replacement, or prevention, no damage was dealt. Do not emit
        # DAMAGE_DEALT and do not buffer a deal-damage trigger.
        if damage_event.current_amount <= 0:
            return damage_event

        source_controller = None
        if source_id is not None and source_id in state.cards:
            source_controller = state.cards[source_id].controller
        target_controller = target_inst.controller
        resolved_actor = actor if actor is not None else source_controller if source_controller is not None else target_controller

        prevented_amount = max(0, damage_event.original_amount - damage_event.current_amount)
        challenge_context = {}
        if is_challenge and isinstance(state.turn_metadata.get("active_challenge"), dict):
            challenge_context = dict(state.turn_metadata["active_challenge"])

        self.emit_event(
            state,
            EVENT_DAMAGE_DEALT,
            actor=resolved_actor,
            source=source_id,
            target=target_id,
            payload={
                "player_id": resolved_actor,
                "source_controller": source_controller,
                "target_controller": target_controller,
                "subject_card_id": target_id,
                "source_card_id": source_id,
                "target_card_id": target_id,
                "damage_dealt": damage_event.current_amount,
                "original_amount": damage_event.original_amount,
                "raw_amount": raw_amount,
                "prevented_amount": prevented_amount,
                "is_challenge": is_challenge,
                "was_replaced": damage_event.was_replaced,
                "replacement_description": damage_event.replacement_description,
                **challenge_context,
            },
        )
        return damage_event

    def _static_prevented_damage_amount(
        self,
        state: GameState,
        *,
        target_id: int,
        amount: int,
        is_challenge: bool,
    ) -> int:
        """Exact static prevention for Hercules - Mighty Leader source shapes."""
        if amount <= 0 or is_challenge:
            return 0
        target_inst = state.cards.get(target_id)
        if target_inst is None or target_inst.zone != ZONE_PLAY:
            return 0
        for source_id, source_inst in state.cards.items():
            if source_inst.zone != ZONE_PLAY or source_inst.stack_parent_id is not None:
                continue
            source_card = self.card_def(state, source_id)
            for ability in getattr(source_card, "source_abilities", ()) or ():
                if getattr(ability, "kind", None) != "static":
                    continue
                if getattr(ability, "condition", None) is not None and not source_inst.exerted:
                    continue
                for effect in getattr(ability, "effects", ()) or ():
                    if getattr(effect, "kind", None) != "restriction":
                        continue
                    raw = getattr(effect, "raw", {}) or {}
                    if raw.get("restriction") != "cant-be-dealt-damage":
                        continue
                    condition = raw.get("condition")
                    if not (
                        isinstance(condition, dict)
                        and condition.get("type") == "not"
                        and isinstance(condition.get("condition"), dict)
                        and condition["condition"].get("type") == "being-challenged"
                    ):
                        continue
                    if self._static_restriction_target_matches(state, source_id, target_id, effect):
                        return amount
        return 0

    def _static_restriction_target_matches(self, state: GameState, source_id: int, target_id: int, effect: Any) -> bool:
        raw_target = getattr(effect, "target", None)
        alias = getattr(raw_target, "alias", None)
        if alias == "SELF":
            return target_id == source_id
        raw = getattr(raw_target, "raw", None)
        if not isinstance(raw, dict):
            return False
        source_inst = state.cards[source_id]
        target_inst = state.cards[target_id]
        if raw.get("owner") == "you" and target_inst.controller != source_inst.controller:
            return False
        if raw.get("excludeSelf") and target_id == source_id:
            return False
        card_types = tuple(raw.get("cardTypes") or ())
        if card_types and self.card_def(state, target_id).card_type not in card_types:
            return False
        filters = raw.get("filter") or raw.get("filters") or ()
        if isinstance(filters, dict):
            filters = (filters,)
        for filter_def in filters:
            if not isinstance(filter_def, dict):
                return False
            if filter_def.get("type") == "has-classification":
                classification = filter_def.get("classification")
                if classification not in self.card_def(state, target_id).subtypes:
                    return False
        return True

    def resolve_bag(self, state: GameState) -> None:
        # B2: Bag must be resolved through ACTION_RESOLVE_BAG, not silently cleared
        raise RuntimeError("Bag must be resolved through ACTION_RESOLVE_BAG. Use legal_actions() to get RESOLVE_BAG actions.")

    def resolve_banishes(self, state: GameState) -> None:
        """Resolve banishes with rich Lorcanito-aligned payloads including challenge context.

        B8: Routes through _banish_eventful() to use replacement-aware banish handling.
        """
        banished: list[tuple[int, str]] = []  # (cid, card_type)
        for cid, inst in list(state.cards.items()):
            if inst.zone != ZONE_PLAY:
                continue
            cdef = self.card_def(state, cid)
            if cdef.card_type in {CARD_CHARACTER, CARD_LOCATION} and inst.damage >= self.effective_willpower(state, cid):
                banished.append((cid, cdef.card_type))

        for cid, card_type in banished:
            card = state.cards[cid]
            controller = card.controller
            # last_damage_source can be int or str (card name), cast to int for the API
            last_damage_source = card.last_damage_source
            source_for_banish: int | None = int(last_damage_source) if isinstance(last_damage_source, (int, str)) and last_damage_source else None
            happened_in_challenge = card.last_damage_was_challenge

            # B8: Route through _banish_eventful which handles:
            # 1. Deregistering static/replacement effects
            # 2. Evaluating replacement effects via banish_card
            # 3. Performing the card move
            # 4. Emitting the banish event with rich payload
            self._banish_eventful(
                state,
                cid,
                actor=controller,
                source_id=source_for_banish,
                reason="lethal_damage",
                happened_in_challenge=happened_in_challenge,
            )

    def resolve_win_loss(self, state: GameState) -> None:
        if state.winner is not None:
            return
        lore_winners = [idx for idx, ps in enumerate(state.players) if ps.lore >= self.lore_to_win]
        if lore_winners:
            # If simultaneous, active player priority is deterministic and testable.
            state.winner = state.active_player if state.active_player in lore_winners else lore_winners[0]
            state.loss_reason = "opponent_reached_lore_threshold"
            return
        for idx, ps in enumerate(state.players):
            if not ps.deck and state.active_player == idx:
                # Conservative approximation for the current MVP: active player loses
                # only at turn end if no deck remains after all effects.
                pass

    def _apply_ink(self, state: GameState, action: Action) -> None:
        """Apply ink action with rich event payload."""
        assert action.card is not None
        if state.cards[action.card].zone == ZONE_DISCARD and not self._can_ink_from_discard(state, action.actor):
            raise IllegalActionError("Cannot ink from discard")
        self._put_into_inkwell_eventful(state, action.card, actor=action.actor)
        extra_ink_key = f"additional_inkwell:{action.actor}"
        extra_inks = int(state.turn_metadata.get(extra_ink_key, 0) or 0)
        if state.turn_player_has_inked and extra_inks > 0:
            state.turn_metadata[extra_ink_key] = extra_inks - 1
        else:
            state.turn_player_has_inked = True
            state.players[action.actor].turn_flags.played_ink = True

    def _can_ink_from_discard(self, state: GameState, player: int) -> bool:
        for cid in state.players[player].play:
            card = self.card_def(state, cid)
            for ability in getattr(card, "source_abilities", ()) or ():
                if getattr(ability, "kind", None) != "static":
                    continue
                for effect in getattr(ability, "effects", ()) or ():
                    if getattr(effect, "kind", None) == "grant-discard-inkability":
                        return True
        return False

    def _register_lifecycle_effects_for_public_permanent(
        self,
        state: GameState,
        card_id: int,
    ) -> None:
        """Register static and replacement effects for a card entering public play.

        This helper centralizes lifecycle registration for permanents entering the
        play zone. It must be called after a card becomes a public permanent (in play
        with no stack_parent_id), and only for non-action permanents.

        The helper refuses:
        - Cards not in ZONE_PLAY
        - Cards with stack_parent_id (not publicly visible)
        - Action cards (actions go to discard, not play)

        Lorcanito parity: Lorcanito registers live continuous/replacement state
        only after a card becomes an active public permanent.
        """
        inst = state.cards.get(card_id)
        if inst is None or inst.zone != ZONE_PLAY or inst.stack_parent_id is not None:
            return

        card = self.card_def(state, card_id)
        if card.card_type == CARD_ACTION:
            return

        source_abilities = getattr(card, "source_abilities", None) or getattr(card, "abilities", ())
        register_static_effects_for_card(state, card_id, source_abilities)
        register_replacement_effects_for_card(state, card_id, source_abilities)

    def _apply_play(self, state: GameState, action: Action) -> None:
        """Apply play card action with rich event payload."""
        assert action.card is not None
        player = action.actor
        card = self.card_def(state, action.card)
        cost = self.play_cost(state, player, action.card)
        from_zone = state.cards[action.card].zone  # Store before move
        self._pay_ink(state, player, cost)
        self._consume_cost_reductions(state, player, card.card_type, card.cost - cost)

        if card.card_type == CARD_ACTION:
            self._move_card_eventful(state, action.card, ZONE_DISCARD, actor=player)
            # Extract player target from Action.choice for chosen_player actions
            player_target = None
            if action.choice and isinstance(action.choice, dict):
                player_target = action.choice.get("player")
            current_targets = ()
            if action.choice and isinstance(action.choice, dict) and action.choice.get("targets") is not None:
                current_targets = tuple(action.choice.get("targets") or ())
            elif action.target is not None:
                current_targets = (action.target,)
            slotted_targets = None
            if action.choice and isinstance(action.choice, dict):
                slotted_targets = action.choice.get("slotted_targets")
            self._resolve_effects(
                state,
                player,
                action.card,
                action.target,
                choice=player_target,
                current_targets=current_targets,
                slotted_targets=slotted_targets,
            )
            to_zone = ZONE_DISCARD
        else:
            self._move_card_eventful(state, action.card, ZONE_PLAY, actor=player)
            inst = state.cards[action.card]
            inst.exerted = False
            inst.damage = 0
            inst.drying = card.card_type == CARD_CHARACTER
            inst.just_played = True
            to_zone = ZONE_PLAY
            # Register static and replacement effects for public permanent entry
            self._register_lifecycle_effects_for_public_permanent(state, action.card)

        # Emit play event with rich Lorcanito-aligned payload
        self.emit_event(
            state,
            EVENT_CARD_PLAYED,
            actor=player,
            source=action.card,
            target=action.target,
            payload={
                "player_id": player,
                "subject_card_id": action.card,
                "card_type": card.card_type,
                "played_from": from_zone,
                "played_to": to_zone,
                "used_shift": False,
                "sung": False,
            },
        )

    def _apply_quest(self, state: GameState, action: Action) -> None:
        """Apply quest action with rich event payload."""
        assert action.source is not None
        source = action.source
        cdef = self.card_def(state, source)
        # B7.1: Calculate effective lore including static modifiers
        base_lore = int(cdef.lore or 0)
        from .static_effects import get_static_modifier
        lore_modifier = get_static_modifier(state, source, "lore")
        lore = base_lore + lore_modifier
        # Use eventful helpers - exert and gain lore without emitting their individual events
        self._exert_eventful(state, source, actor=action.actor, source_id=source, emit_event=False)
        state.cards[source].has_quested_this_turn = True
        self._gain_lore_eventful(state, action.actor, lore, source_id=source, emit_event=False)

        # Emit quest event with rich Lorcanito-aligned payload
        self.emit_event(
            state,
            EVENT_QUESTED,
            actor=action.actor,
            source=source,
            payload={
                "player_id": action.actor,
                "subject_card_id": source,
                "lore": lore,
            },
        )

    def _apply_challenge(self, state: GameState, action: Action) -> None:
        """Apply challenge action with rich event payload including attacker/defender details."""
        assert action.source is not None and action.target is not None
        source_def = self.card_def(state, action.source)
        target_def = self.card_def(state, action.target)
        source_inst = state.cards[action.source]
        target_inst = state.cards[action.target]
        # Use eventful exert - emit_event=False since challenge event covers it
        self._exert_eventful(state, action.source, actor=action.actor, source_id=action.source, emit_event=False)
        self._register_challenge_created_replacements(state, action.source, action.target)

        # Lorcanito-aligned challenge context for later damage/banish trigger snapshots.
        state.turn_metadata["active_challenge"] = {
            "attacker_id": action.source,
            "defender_id": action.target,
        }

        # Calculate base damage with resist (before replacement)
        attacker_base_damage = self._damage_after_resist(target_def, self.effective_strength(state, action.source))
        defender_base_damage = 0
        defender_damage_dealt = 0
        if target_def.card_type == CARD_CHARACTER:
            defender_base_damage = self._damage_after_resist(source_def, self.effective_strength(state, action.target))

        # Apply damage through the engine-owned damage helper so DAMAGE_DEALT
        # events are emitted and triggers are buffered. Challenge damage has
        # already had resist applied above, so apply_resist=False here.
        attacker_event = self._deal_damage_eventful(
            state,
            target_id=action.target,
            source_id=action.source,
            amount=attacker_base_damage,
            actor=action.actor,
            is_challenge=True,
            apply_resist=False,
        )
        attacker_damage_dealt = attacker_event.current_amount

        # Apply damage through the engine-owned damage helper for defender -> attacker.
        if target_def.card_type == CARD_CHARACTER:
            defender_event = self._deal_damage_eventful(
                state,
                target_id=action.source,
                source_id=action.target,
                amount=defender_base_damage,
                actor=target_inst.controller,
                is_challenge=True,
                apply_resist=False,
            )
            defender_damage_dealt = defender_event.current_amount

        target_inst.was_challenged_this_turn = True

        # B13: Record challenge for turn metadata
        if "challenges_by_player_this_turn" not in state.turn_metadata:
            state.turn_metadata["challenges_by_player_this_turn"] = {}
        player_challenges = state.turn_metadata["challenges_by_player_this_turn"]
        player_challenges[action.actor] = player_challenges.get(action.actor, 0) + 1

        self._resolve_temporary_challenge_lore_grants(state, action.source, action.actor)

        # Emit challenge event with rich Lorcanito-aligned payload
        self.emit_event(
            state,
            EVENT_CHALLENGE_STARTED,
            actor=action.actor,
            source=action.source,
            target=action.target,
            payload={
                "player_id": action.actor,
                "attacker_id": action.source,
                "defender_id": action.target,
                "defender_card_type": target_def.card_type,
                "attacker_damage_dealt": attacker_damage_dealt,
                "defender_damage_dealt": defender_damage_dealt,
            },
        )

    def _resolve_temporary_challenge_lore_grants(self, state: GameState, attacker_id: int, actor: int) -> None:
        grants = state.cards[attacker_id].temporary_granted_abilities
        remaining = []
        for grant in grants:
            if isinstance(grant, dict) and grant.get("type") == "gain-lore-when-challenging":
                self._gain_lore_eventful(state, actor, int(grant.get("amount") or 1), source_id=attacker_id)
                continue
            remaining.append(grant)
        state.cards[attacker_id].temporary_granted_abilities = remaining

    def _register_challenge_created_replacements(self, state: GameState, attacker_id: int, defender_id: int) -> None:
        """Register exact Rafiki-style prevention before challenge damage is dealt."""
        attacker_card = self.card_def(state, attacker_id)
        defender_card = self.card_def(state, defender_id)
        for ability in getattr(attacker_card, "source_abilities", ()) or ():
            if getattr(ability, "kind", None) != "triggered":
                continue
            for effect in getattr(ability, "effects", ()) or ():
                raw = getattr(effect, "raw", {}) or {}
                if getattr(effect, "kind", None) != "create-replacement-effect":
                    continue
                replacement = raw.get("replacement")
                if not isinstance(replacement, dict):
                    continue
                if replacement.get("type") != "prevent-damage" or replacement.get("targetRef") != "source":
                    continue
                ability_raw = getattr(ability, "raw", {}) or {}
                raw_trigger = ability_raw.get("trigger") if isinstance(ability_raw, dict) else None
                if not isinstance(raw_trigger, dict) or raw_trigger.get("event") != "challenge" or raw_trigger.get("on") != "SELF":
                    continue
                defender_filter = raw_trigger.get("defender")
                if isinstance(defender_filter, dict):
                    filters = defender_filter.get("filter") or defender_filter.get("filters") or ()
                    if isinstance(filters, dict):
                        filters = (filters,)
                    if any(
                        isinstance(filter_def, dict)
                        and filter_def.get("type") in {"has-classification", "classification"}
                        and filter_def.get("classification") not in defender_card.subtypes
                        for filter_def in filters
                    ):
                        continue
                register_replacement_effect(
                    state,
                    ReplacementEffectEntry(
                        source_id=attacker_id,
                        effect_type=ReplacementEffectType.PREVENT_DAMAGE,
                        target_mode="self",
                        amount=999,
                        replacement_effect="prevent_damage",
                        usage_key=f"challenge_created_prevent:{attacker_id}:{state.turn_number}",
                        event_kinds=tuple(replacement.get("eventKinds", ()) or ()),
                        consume_on_apply=bool(replacement.get("consumeOnApply")),
                        duration=str(raw.get("duration") or "this-turn"),
                    ),
                )

    def _apply_move_to_location(self, state: GameState, action: Action) -> None:
        assert action.source is not None and action.target is not None
        player = action.actor
        character = self.card_def(state, action.source)
        location = self.card_def(state, action.target)
        if character.card_type != CARD_CHARACTER or location.card_type != CARD_LOCATION:
            raise IllegalActionError("Move-to-location requires a character source and location target")
        self._pay_ink(state, player, int(location.move_cost or 0))
        state.cards[action.source].location_instance_id = action.target
        self.emit_event(state, EVENT_MOVED_TO_LOCATION, actor=player, source=action.source, target=action.target)

    def _effect_source_raw(self, effect: Any) -> dict[str, Any]:
        raw = getattr(effect, "raw", {}) or {}
        if isinstance(raw, dict) and isinstance(raw.get("raw"), dict):
            return raw["raw"]
        return raw if isinstance(raw, dict) else {}

    def _effect_kind_name(self, effect: Any) -> str:
        return str(getattr(effect, "kind", "") or "").replace("_", "-")

    def _effect_choice_actor(
        self,
        state: GameState,
        *,
        controller_id: int,
        raw: dict[str, Any],
        parent_chooser_id: int | None = None,
    ) -> int:
        chooser = raw.get("chooser")
        chosen_by = raw.get("chosenBy") or raw.get("chosen_by")

        if parent_chooser_id is not None and chooser is None and chosen_by is None:
            return parent_chooser_id

        normalized = str(chooser or chosen_by or "").replace("_", "-").lower()
        if normalized in {"opponent", "opponents"}:
            return state.opponent(controller_id)
        if normalized in {"controller", "you", "self"}:
            return controller_id
        return controller_id

    def _move_to_location_slot_specs(self, effects: tuple[Any, ...]) -> tuple[dict[str, Any], ...]:
        specs: list[dict[str, Any]] = []
        for effect in effects:
            if self._effect_kind_name(effect) == "move-to-location":
                raw = self._effect_source_raw(effect)
                character = raw.get("character") or raw.get("subject")
                location = raw.get("location")
                if character is not None and location is not None:
                    specs.append({
                        "kind": "move-to-location",
                        "slots": {
                            "subject": character,
                            "location": location,
                        },
                    })
            child_effects = tuple(getattr(effect, "effects", ()) or ())
            if child_effects:
                specs.extend(self._move_to_location_slot_specs(child_effects))
        return tuple(specs)

    def _effect_requires_slotted_targets(self, effects: tuple[Any, ...]) -> bool:
        return bool(self._move_to_location_slot_specs(effects))

    def _slot_target_selections(
        self,
        state: GameState,
        *,
        actor: int,
        source_id: int | None,
        raw_target: Any,
        event_payload: dict[str, Any] | None = None,
    ) -> tuple[tuple[int, ...], ...]:
        from .targeting import (
            TargetQueryContext,
            apply_target_protections,
            enumerate_target_selections,
            normalize_target_descriptor,
            resolve_candidate_targets,
        )

        descriptor = normalize_target_descriptor(raw_target)
        if descriptor is None:
            return ()

        context = TargetQueryContext(
            actor=actor,
            source_id=source_id,
            event_payload=dict(event_payload or {}),
        )
        candidates = apply_target_protections(
            state,
            self,
            resolve_candidate_targets(state, self, descriptor, context),
            descriptor,
            context,
        )
        return enumerate_target_selections(candidates, descriptor, candidate_kind="card")

    def _enumerate_move_to_location_slotted_targets(
        self,
        state: GameState,
        *,
        actor: int,
        source_id: int | None,
        spec: dict[str, Any],
        event_payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        slots = spec.get("slots", {})
        subject_options = self._slot_target_selections(
            state,
            actor=actor,
            source_id=source_id,
            raw_target=slots.get("subject"),
            event_payload=event_payload,
        )
        location_options = self._slot_target_selections(
            state,
            actor=actor,
            source_id=source_id,
            raw_target=slots.get("location"),
            event_payload=event_payload,
        )

        result: list[dict[str, Any]] = []
        for subjects in subject_options:
            if not subjects:
                continue
            for locations in location_options:
                if len(locations) != 1:
                    continue
                result.append({
                    "kind": "move-to-location",
                    "subject": tuple(subjects),
                    "location": tuple(locations),
                })
        return tuple(result)

    def _apply_end_turn(self, state: GameState, action: Action) -> None:
        player = action.actor
        if not state.players[player].deck:
            state.winner = state.opponent(player)
            state.loss_reason = f"player_{player}_ended_turn_with_empty_deck"
            return
        state.players[player].turn_flags.passed_turn = True
        self.emit_event(state, EVENT_TURN_END, actor=player)
        cleanup_replacement_effects_on_turn_end(state)
        state.turn_metadata.pop("cant_quest_until_turn_end", None)
        next_player = state.opponent(player)
        state.active_player = next_player
        state.turn_number += 1
        state.turn_player_has_inked = False
        state.players[next_player].turn_flags = type(state.players[next_player].turn_flags)()
        for cid in state.players[next_player].play:
            inst = state.cards[cid]
            inst.exerted = False
            inst.drying = False
            inst.just_played = False
            inst.added_to_ink_this_turn = False
            inst.has_quested_this_turn = False
            inst.used_abilities_this_turn.clear()
            inst.last_damage_source = None
            inst.last_damage_was_challenge = False
            inst.was_challenged_this_turn = False
            inst.temporary_keywords.clear()
            inst.temporary_modifiers.clear()
            inst.temporary_granted_abilities.clear()
        for cid in state.players[player].play:
            state.cards[cid].temporary_keywords.clear()
            state.cards[cid].temporary_modifiers.clear()
            state.cards[cid].temporary_granted_abilities.clear()
        state.players[player].cost_reductions.clear()
        state.players[next_player].cost_reductions.clear()
        for cid in state.players[next_player].inkwell:
            inst = state.cards[cid]
            inst.exerted = False
            inst.added_to_ink_this_turn = False

        # B13: Reset turn metadata when the active turn changes
        state.turn_metadata = {}

        self.emit_event(state, EVENT_TURN_START, actor=next_player)
        self._gain_lore_from_locations(state, next_player)
        self.draw_cards(state, next_player, 1)
        state.players[next_player].turn_flags.drew_for_turn = True

    def _gain_lore_from_locations(self, state: GameState, player: int) -> None:
        amount = 0
        count = 0
        for cid in state.players[player].play:
            cdef = self.card_def(state, cid)
            if cdef.card_type == CARD_LOCATION:
                amount += int(cdef.lore or 0)
                count += 1
        if amount > 0:
            self._gain_lore_eventful(state, player, amount, emit_event=False)
            self.emit_event(state, EVENT_LOCATION_LORE_GAINED, actor=player, payload={"lore": amount, "locations": count})

    def _apply_keep_hand(self, state: GameState, action: Action) -> None:
        state.players[action.actor].has_kept_opening_hand = True
        self.emit_event(state, EVENT_KEPT_HAND, actor=action.actor)
        self._advance_mulligan_or_start(state)

    def _apply_mulligan(self, state: GameState, action: Action) -> None:
        selected = tuple(action.choice or ())
        ps = state.players[action.actor]
        selected_set = set(selected)
        if not selected or len(selected_set) != len(selected):
            raise IllegalActionError("Mulligan requires a non-empty unique card choice")
        if any(cid not in ps.hand for cid in selected):
            raise IllegalActionError("Mulligan choices must be in the player's hand")

        for cid in selected:
            self._move_card_eventful(state, cid, ZONE_DECK, actor=action.actor, controller=action.actor, queue_triggers=False)
        self.draw_cards(state, action.actor, len(selected))
        self._shuffle_deck(state, action.actor, salt="mulligan")
        ps.has_mulliganed = True
        ps.has_kept_opening_hand = True
        ps.mulliganed_card_ids.extend(selected)
        self.emit_event(state, EVENT_MULLIGANED, actor=action.actor, payload={"cards": list(selected)})
        self._advance_mulligan_or_start(state)

    def _apply_concede(self, state: GameState, action: Action) -> None:
        state.winner = state.opponent(action.actor)
        state.loss_reason = f"player_{action.actor}_conceded"
        state.phase = PHASE_GAME_OVER
        self.emit_event(state, EVENT_CONCEDED, actor=action.actor)

    def _advance_mulligan_or_start(self, state: GameState) -> None:
        if all(player.has_kept_opening_hand for player in state.players):
            state.phase = PHASE_MAIN
            state.active_player = state.first_player
            self.emit_event(state, EVENT_TURN_START, actor=state.first_player)
            return

        next_player = state.opponent(state.active_player)
        if not state.players[next_player].has_kept_opening_hand:
            state.active_player = next_player

    def _shuffle_deck(self, state: GameState, player: int, *, salt: str) -> None:
        state.shuffle_counter += 1
        rng = random.Random(f"{state.seed}:{salt}:{player}:{state.shuffle_counter}")
        rng.shuffle(state.players[player].deck)

    def _apply_sing_song(self, state: GameState, action: Action) -> None:
        """Apply SING_SONG action - singer exerts and sings a song card.

        Action fields:
        - card: The song card instance ID from hand
        - source: The singer character instance ID in play
        """
        from .play_modes import execute_sing_song, execute_sing_together_song

        if action.card is None:
            raise IllegalActionError("SING_SONG requires a song card")
        if action.choice and action.choice.get("mode") == "singTogether":
            singer_ids = tuple(int(cid) for cid in action.choice.get("singer_ids", ()))
            execute_sing_together_song(state, self, singer_ids, action.card)
            return
        if action.source is None:
            raise IllegalActionError("SING_SONG requires a singer source")

        execute_sing_song(state, self, action.source, action.card)

    def _apply_play_shifted(self, state: GameState, action: Action) -> None:
        """Apply PLAY_SHIFTED action - play a shifted character on a target.

        Action fields:
        - card: The shifted character instance ID from hand
        - target: The target character instance ID in play
        """
        from .play_modes import execute_shift_play

        if action.card is None:
            raise IllegalActionError("PLAY_SHIFTED requires a shifted card")
        if action.target is None:
            raise IllegalActionError("PLAY_SHIFTED requires a target character")

        execute_shift_play(state, self, action.card, action.target)
        # Register static and replacement effects for the new public permanent (shifted card)
        self._register_lifecycle_effects_for_public_permanent(state, action.card)

    def _pay_ink(self, state: GameState, player: int, amount: int) -> None:
        ready_ink = [cid for cid in state.players[player].inkwell if not state.cards[cid].exerted]
        if len(ready_ink) < amount:
            raise IllegalActionError("Insufficient ink")
        for cid in ready_ink[:amount]:
            self._exert_eventful(state, cid, actor=player, source_id=cid, emit_event=False)

    def _effect_target_descriptors_for_card(
        self, state: GameState, source: int,
    ) -> tuple["TargetDescriptor", ...]:
        """Return explicit target-selection descriptors for an action card.

        Fixed targets such as "you", "opponent", "self", and collection targets
        such as "all_characters" are resolved by EffectResolver and do not need
        legal-action target choices. Unknown/unsupported target strings produce
        no descriptor (conservative: no broad fallback targets).
        """
        from .targeting import normalize_target_descriptor, requires_explicit_target_selection
        card = self.card_def(state, source)
        descriptors = []
        for raw_target in self._effect_target_kinds(card.effects):
            desc = normalize_target_descriptor(raw_target)
            if desc is None:
                continue
            if not requires_explicit_target_selection(desc.selector):
                continue
            descriptors.append(desc)
        return tuple(descriptors)

    def _targeted_play_actions(self, state: GameState, player: int, source: int) -> list[Action]:
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            enumerate_target_selections,
            resolve_candidate_targets,
        )

        actions: list[Action] = []
        query_context = TargetQueryContext(actor=player, source_id=source)
        for spec in self._move_to_location_slot_specs(self.card_def(state, source).effects):
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=player,
                source_id=source,
                spec=spec,
            ):
                subjects = tuple(slotted.get("subject", ()) or ())
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    target=subjects[0] if subjects else None,
                    choice={"slotted_targets": slotted},
                ))
        for desc in self._effect_target_descriptors_for_card(state, source):
            raw = resolve_candidate_targets(state, self, desc, query_context)
            candidates = apply_target_protections(state, self, raw, desc, query_context)
            availability = analyze_target_selection_availability(desc, candidates)
            if not availability.can_satisfy_required_selection:
                continue

            player_ids = tuple(c.id for c in candidates if c.kind == "player")
            for player_id in player_ids:
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    choice={"target_kind": "player", "player": player_id},
                ))

            for selected in enumerate_target_selections(candidates, desc, candidate_kind="card"):
                if not selected:
                    continue
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    target=selected[0],
                    choice={"targets": selected},
                ))
        return actions

    def _effect_target_candidates_for_card(
        self,
        state: GameState,
        player: int,
        source: int,
    ) -> tuple["TargetCandidate", ...]:
        """Resolve and protect target candidates for an action card.

        Returns TargetCandidate objects for all legal targets (both card and
        player).  Candidates are resolved through the targeting service and
        filtered through protection rules (Ward, cannot-be-targeted,
        ZONE_UNDER, stack_parent_id).
        """
        from .targeting import (
            TargetQueryContext,
            analyze_target_selection_availability,
            apply_target_protections,
            resolve_candidate_targets,
        )
        descriptors = self._effect_target_descriptors_for_card(state, source)
        context = TargetQueryContext(actor=player, source_id=source)
        all_candidates: list["TargetCandidate"] = []
        for desc in descriptors:
            raw = resolve_candidate_targets(state, self, desc, context)
            protected = apply_target_protections(state, self, raw, desc, context)
            availability = analyze_target_selection_availability(desc, protected)
            if not availability.requires_explicit_target_selection:
                continue
            if not availability.can_satisfy_required_selection:
                continue
            all_candidates.extend(protected)
        return tuple(all_candidates)

    def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]:
        """Backward-compatible card-only wrapper.

        Returns sorted card instance IDs from the targeting service.
        Excludes player candidates.
        """
        candidates = self._effect_target_candidates_for_card(state, player, source)
        return sorted(c.id for c in candidates if c.kind == "card")

    def _effect_requires_target(self, effect) -> bool:
        from .targeting import normalize_target_descriptor, requires_explicit_target_selection
        for kind in self._effect_target_kinds((effect,)):
            desc = normalize_target_descriptor(kind)
            if desc is not None and requires_explicit_target_selection(desc.selector):
                return True
        return False

    def _effect_has_unsupported_target(self, effects) -> bool:
        from .targeting import normalize_target_descriptor

        for target_kind in self._effect_target_kinds(effects):
            if isinstance(target_kind, str) and target_kind in _SUPPORTED_EFFECT_TARGET_KINDS:
                continue
            if normalize_target_descriptor(target_kind) is None:
                return True
        return False

    def _effect_target_kinds(self, effects) -> tuple[Any, ...]:
        targets: list[Any] = []
        for effect in effects:
            if isinstance(effect, dict):
                t = effect.get("target")
                if t:
                    targets.append(t)
                sub = effect.get("effects")
                if sub:
                    targets.extend(self._effect_target_kinds(sub))
            else:
                if getattr(effect, "kind", None) == "play_card":
                    raw = getattr(effect, "raw", {}) or {}
                    source_raw = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
                    if source_raw.get("from") == "discard" and source_raw.get("target") == "CHOSEN_CHARACTER":
                        targets.append({
                            "selector": "chosen",
                            "count": 1,
                            "owner": "you",
                            "zones": ["discard"],
                            "cardTypes": ["character"],
                        })
                        continue
                if effect.target:
                    targets.append(effect.target)
                if effect.effects:
                    targets.extend(self._effect_target_kinds(effect.effects))
        return tuple(targets)

    def _scry_destination_choices(
        self,
        candidate_ids: tuple[int, ...],
        destination_rules: tuple[dict[str, Any], ...],
    ) -> tuple[tuple[dict[str, Any], ...], ...]:
        """Enumerate legal structured scry destination choices for small pending sets."""
        if not candidate_ids:
            return (({"zone": "deck-bottom", "cards": ()},),)

        choices: list[tuple[dict[str, Any], ...]] = []

        def bounds(rule: dict[str, Any]) -> tuple[int, int]:
            minimum = max(0, int(rule.get("min", 0) or 0))
            maximum = int(rule.get("max", len(candidate_ids)) or len(candidate_ids))
            return minimum, max(minimum, min(maximum, len(candidate_ids)))

        def rec(index: int, remaining: tuple[int, ...], selected: list[dict[str, Any]]) -> None:
            if index >= len(destination_rules):
                if not remaining:
                    choices.append(tuple(dict(item) for item in selected))
                return

            rule = destination_rules[index]
            zone = str(rule.get("zone") or "")
            if not zone:
                rec(index + 1, remaining, selected)
                return

            if rule.get("remainder"):
                ordered_remainder = (
                    itertools.permutations(remaining)
                    if rule.get("ordering") == "player-choice" and len(remaining) > 1
                    else (remaining,)
                )
                for cards in ordered_remainder:
                    selected.append({"zone": zone, "cards": tuple(cards)})
                    rec(index + 1, (), selected)
                    selected.pop()
                return

            minimum, maximum = bounds(rule)
            for count in range(minimum, maximum + 1):
                if count > len(remaining):
                    continue
                for cards in itertools.permutations(remaining, count):
                    next_remaining = tuple(card_id for card_id in remaining if card_id not in cards)
                    selected.append({"zone": zone, "cards": tuple(cards)})
                    rec(index + 1, next_remaining, selected)
                    selected.pop()

        rec(0, candidate_ids, [])
        return tuple(choices)

    def _emit_be_chosen_events(
        self,
        state: GameState,
        *,
        actor: int,
        source: int,
        selected_targets: tuple[int, ...],
    ) -> None:
        """Emit Lorcanito-aligned be-chosen events for explicit selected targets."""
        if not selected_targets:
            return

        source_card = self.card_def(state, source)
        if source_card.card_type not in {CARD_ACTION, "item", CARD_CHARACTER}:
            return

        seen: set[int] = set()
        for target_id in selected_targets:
            if target_id in seen:
                continue
            seen.add(target_id)

            target_inst = state.cards.get(target_id)
            if target_inst is None:
                continue

            self.emit_event(
                state,
                EVENT_BE_CHOSEN,
                actor=target_inst.owner,
                source=source,
                target=target_id,
                payload={
                    "player_id": target_inst.owner,
                    "subject_card_id": target_id,
                    "trigger_source_card_id": source,
                    "source_card_id": source,
                    "source_card_type": source_card.card_type,
                    "controller_id": target_inst.controller,
                    "owner_id": target_inst.owner,
                },
            )

    def _resolve_effects(
        self,
        state: GameState,
        player: int,
        source: int,
        target: int | None,
        *,
        choice: Any = None,
        current_targets: tuple[int, ...] = (),
        slotted_targets: dict[str, Any] | None = None,
        destinations: tuple[dict[str, Any], ...] = (),
    ) -> None:
        card = self.card_def(state, source)
        selected_targets = current_targets or ((target,) if target is not None else ())
        self._emit_be_chosen_events(
            state,
            actor=player,
            source=source,
            selected_targets=tuple(int(target_id) for target_id in selected_targets),
        )
        self.effect_resolver.resolve_many(
            state,
            card.effects,
            EffectResolutionContext(
                actor=player,
                source=source,
                target=target,
                choice=choice,
                current_targets=current_targets,
                slotted_targets=slotted_targets,
                destinations=destinations,
            ),
        )

    def _resolve_explicit_effects(self, state: GameState, effects: tuple, context: EffectResolutionContext) -> None:
        """Resolve a specific set of effects (used for trigger effects from the bag)."""
        self.effect_resolver.resolve_many(state, effects, context)

    def _applicable_cost_reductions(self, state: GameState, player: int, card_type: str) -> list[dict]:
        reductions = []
        for reduction in state.players[player].cost_reductions:
            reduction_type = reduction.get("card_type")
            if reduction_type is None or reduction_type == card_type:
                reductions.append(reduction)
        return reductions

    def _consume_cost_reductions(self, state: GameState, player: int, card_type: str, amount_used: int) -> None:
        if amount_used <= 0:
            return
        remaining: list[dict] = []
        pending = amount_used
        for reduction in state.players[player].cost_reductions:
            reduction_type = reduction.get("card_type")
            if pending > 0 and (reduction_type is None or reduction_type == card_type):
                pending -= int(reduction.get("amount", 0))
                continue
            remaining.append(reduction)
        state.players[player].cost_reductions = remaining

    def _apply_resolve_bag(self, state: GameState, action: Action) -> None:
        """Apply RESOLVE_BAG action to resolve a trigger from the bag."""
        if not action.choice or "bag_id" not in action.choice:
            raise IllegalActionError("RESOLVE_BAG requires bag_id in choice")

        bag_id = action.choice["bag_id"]
        accept = action.choice.get("accept", True)

        # Find the bag entry
        entry: BagEffectEntry | None = None
        for idx, item in enumerate(state.bag):
            if item.id == bag_id:
                entry = item
                break

        if entry is None:
            raise IllegalActionError(f"Bag item {bag_id} not found")

        # Validate resolver
        next_resolver = get_next_bag_resolver(state)
        if next_resolver is not None and action.actor != next_resolver:
            raise IllegalActionError(f"Player {action.actor} is not the current bag resolver (expected {next_resolver})")

        # Validate controller/chooser
        if action.actor != entry.controller_id and action.actor != entry.chooser_id:
            raise IllegalActionError(f"Player {action.actor} cannot resolve this bag item (controller={entry.controller_id}, chooser={entry.chooser_id})")

        # Set last resolver
        set_last_bag_resolver(state, action.actor)

        # Handle decline
        if accept is False:
            if not (entry.optional or entry.auto_resolve is False):
                raise IllegalActionError("Non-optional bag item cannot be declined")
            remove_bag_effect(state, bag_id)
            self.emit_event(state, EVENT_TRIGGER_DECLINED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "ability_id": entry.ability_id}, queue_triggers=False)
            return

        self._merge_bag_resolution_input(entry, action.choice)

        # Check restrictions
        if not can_resolve_bag_effect_by_restrictions(state, entry):
            remove_bag_effect(state, bag_id)
            self.emit_event(state, EVENT_TRIGGER_SKIPPED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "reason": "restriction_not_satisfied"}, queue_triggers=False)
            return

        # Evaluate condition at resolution time
        if entry.condition:
            try:
                condition_met = evaluate_condition(entry.condition, state, entry.event, entry.source_id, self)
                if not condition_met:
                    remove_bag_effect(state, bag_id)
                    self.emit_event(state, EVENT_TRIGGER_SKIPPED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "reason": "condition_not_met"}, queue_triggers=False)
                    return
            except UnsupportedConditionError:
                # Condition cannot be evaluated - skip the trigger
                remove_bag_effect(state, bag_id)
                self.emit_event(state, EVENT_TRIGGER_SKIPPED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "reason": "unsupported_condition"}, queue_triggers=False)
                return

        # B2: Resolve effects as the trigger controller, not the chooser
        # Normalize event target from payload (handles defender_id from challenge events)
        event_payload = {}
        if entry.event:
            event_payload.update(entry.event.event_snapshot or {})
            event_payload.update(entry.event.payload or {})
        selected_targets = tuple(entry.resolution_input.get("targets", ()) or ())
        slotted_targets = entry.resolution_input.get("slotted_targets")
        destinations = tuple(
            dict(destination)
            for destination in entry.resolution_input.get("destinations", ()) or ()
            if isinstance(destination, dict)
        )
        event_target = (
            event_payload.get('event_target_id')
            or event_payload.get('target_id')
            or event_payload.get('defender_id')
            or event_payload.get('subject_card_id')
        )

        # Build current_targets tuple for collection-based targeting
        current_targets: tuple[int, ...] = selected_targets
        if not current_targets and event_target:
            current_targets = (event_target,)
        selected_target = selected_targets[0] if selected_targets else event_target

        context = EffectResolutionContext(
            actor=entry.controller_id,
            source=entry.source_id,
            target=selected_target,
            event=entry.event,
            event_payload=event_payload,
            choice=entry.resolution_input.get("choice_index") if "choice_index" in entry.resolution_input else entry.resolution_input.get("amount"),
            pending_trigger_id=entry.id,
            trigger_source=entry.source_id,
            trigger_subject=entry.event.subject_card_id if entry.event else None,
            current_targets=current_targets,
            slotted_targets=slotted_targets,
            destinations=destinations,
        )

        # Count pending effects BEFORE resolution to detect if effects create new pending
        pending_count_before = len(state.pending_effects)

        self._resolve_explicit_effects(state, entry.effects, context)

        # Check if any new pending effects were created from this bag item's resolution
        pending_count_after = len(state.pending_effects)
        created_pending = pending_count_after > pending_count_before

        if created_pending:
            # Mark all newly created pending effects with bag origin
            for pe in state.pending_effects[pending_count_before:]:
                pe.origin = "bag"
                pe.origin_id = bag_id
                pe.raw["origin"] = "bag"
                pe.raw["origin_id"] = bag_id
                # Store bag entry context in pending effect raw for completion handling
                pe.raw.setdefault("bag_id", bag_id)
                pe.raw.setdefault("resolution_input", {}).update(entry.resolution_input)
                pe.raw.setdefault("event", entry.event.event if entry.event else None)
                pe.raw.setdefault("event_payload", event_payload)
                pe.raw.setdefault("trigger_subject", entry.event.subject_card_id if entry.event else None)
                pe.raw.setdefault("ability_id", entry.ability_id)
                pe.raw.setdefault("source_id", entry.source_id)
                pe.raw.setdefault("controller_id", entry.controller_id)
            # Do NOT record resolution or remove bag entry yet - wait for pending to complete
            return

        # No pending effects created - complete resolution immediately
        # Record resolution
        record_bag_effect_resolution(state, entry)

        # Remove bag entry
        remove_bag_effect(state, bag_id)

        # Emit trigger resolved event
        self.emit_event(state, EVENT_TRIGGER_RESOLVED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "ability_id": entry.ability_id}, queue_triggers=False)

        # B2: Flush any newly emitted trigger events
        # This is handled by the resolution boundary in apply_action

    def _merge_bag_resolution_input(self, entry: BagEffectEntry, choice: dict[str, Any]) -> None:
        key_map = {
            "amount": "amount",
            "targets": "targets",
            "player_targets": "player_targets",
            "slotted_targets": "slotted_targets",
            "choice_index": "choice_index",
            "resolve_optional": "resolve_optional",
            "named_card": "named_card",
            "destinations": "destinations",
            "enter_play_exerted": "enter_play_exerted",
        }
        for choice_key, input_key in key_map.items():
            if choice_key in choice:
                entry.resolution_input[input_key] = choice[choice_key]

    def _apply_use_ability(self, state: GameState, action: Action) -> None:
        """Apply USE_ABILITY action to execute an activated ability.

        This method:
        1. Extracts the ability from the source card
        2. Validates and pays all costs atomically
        3. Resolves the ability effects
        4. Marks the ability as used this turn
        """
        from .abilities import get_activated_abilities_for_card, use_ability, AbilityCostError, AbilityExecutionError

        if action.source is None:
            raise IllegalActionError("USE_ABILITY requires a source card")

        source_id = action.source
        card_inst = state.cards.get(source_id)
        if card_inst is None:
            raise IllegalActionError(f"Source card {source_id} not found")

        if card_inst.zone != ZONE_PLAY:
            raise IllegalActionError("USE_ABILITY source must be in play")

        # Get the ability index from the choice
        ability_index = action.choice.get("ability_index") if action.choice else None
        ability_id = action.choice.get("ability_id") if action.choice else None

        # Find the ability on the card
        card_def = self.card_def(state, source_id)
        abilities = get_activated_abilities_for_card(state, source_id, card_def, self)

        ability = None
        if ability_index is not None:
            for a in abilities:
                if a.ability_index == ability_index:
                    ability = a
                    break
        elif ability_id is not None:
            for a in abilities:
                if a.ability_id == ability_id:
                    ability = a
                    break

        if ability is None:
            raise IllegalActionError(f"Ability not found on card {source_id}")

        if action.choice and isinstance(action.choice, dict) and action.choice.get("targets") is not None:
            selected_targets = tuple(int(target_id) for target_id in action.choice.get("targets") or ())
        elif action.target is not None:
            selected_targets = (action.target,)
        else:
            selected_targets = ()

        slotted_targets = None
        if action.choice and isinstance(action.choice, dict):
            slotted_targets = action.choice.get("slotted_targets")

        if self._activated_ability_requires_target(ability):
            valid_selections = self._activated_ability_target_selections(state, ability, action.actor)
            if valid_selections is None or selected_targets not in valid_selections:
                raise IllegalActionError("USE_ABILITY requires a valid selected target selection")

        if self._ability_requires_discard_cost_choice(ability):
            self._create_activated_discard_cost_pending(state, ability, action.actor, selected_targets)
            return

        # Execute the ability (validates costs, pays them, and resolves effects)
        result = use_ability(
            state,
            self,
            ability,
            selected_targets=selected_targets,
            slotted_targets=slotted_targets,
        )

        if not result.success:
            raise AbilityExecutionError(f"Ability execution failed: {result.error_message}")

        # Emit ability used event
        self.emit_event(
            state,
            "ABILITY_USED",
            actor=action.actor,
            source=source_id,
            payload={
                "ability_id": ability.ability_id,
                "ability_index": ability.ability_index,
                "costs_paid": list(result.costs_paid),
                "effects_resolved": result.effects_resolved,
            },
            queue_triggers=False,  # Ability costs don't trigger nested abilities
        )

    def _activated_ability_requires_target(self, ability: ActivatedAbility) -> bool:
        return bool(self._activated_ability_explicit_target_descriptors(ability))

    def _ability_requires_discard_cost_choice(self, ability: ActivatedAbility) -> bool:
        from lorcana_bot.card_logic.effect_utils import to_engine_cost_kind
        random_discard = bool((ability.raw or {}).get("random_discard"))
        return (
            not random_discard
            and any(to_engine_cost_kind(cost.kind) == "discard" for cost in ability.costs)
        )

    def _create_activated_discard_cost_pending(
        self,
        state: GameState,
        ability: ActivatedAbility,
        actor: int,
        selected_targets: tuple[int, ...],
    ) -> None:
        from lorcana_bot.card_logic.effect_utils import to_engine_cost_kind
        from lorcana_bot.pending_effects import create_discard_choice_pending_effect
        from lorcana_bot.costs import validate_cost_payable

        effects_supported, reason = validate_effects_supported(ability)
        if not effects_supported:
            raise IllegalActionError(reason)
        if not can_use_ability_this_turn(state, ability):
            raise IllegalActionError("Ability has already been used this turn")

        discard_amount = 0
        for cost in ability.costs:
            can_pay, cost_reason = validate_cost_payable(state, self, ability, cost)
            if not can_pay:
                raise IllegalActionError(f"Cannot pay cost {cost.kind}: {cost_reason}")
            if to_engine_cost_kind(cost.kind) == "discard":
                discard_amount += int(cost.amount or 1)
        if discard_amount <= 0:
            raise IllegalActionError("Discard cost pending requires discardCards amount")

        source_card = state.cards[ability.source_instance_id]
        candidate_ids = tuple(state.players[source_card.controller].hand)
        if len(candidate_ids) < discard_amount:
            raise IllegalActionError("Not enough cards to discard")

        create_discard_choice_pending_effect(
            state,
            controller_id=source_card.controller,
            chooser_id=source_card.controller,
            source_id=ability.source_instance_id,
            source_card_id=ability.source_card_id,
            target_player_id=source_card.controller,
            candidate_ids=candidate_ids,
            min_select=discard_amount,
            max_select=discard_amount,
            origin="activated_cost",
            origin_id=ability.unique_use_key,
            raw={
                "ability_id": ability.ability_id,
                "ability_index": ability.ability_index,
                "selected_targets": selected_targets,
                "reason": "ability_cost",
            },
        )

    def _apply_resolve_pending_effect(self, state: GameState, action: Action) -> None:
        """Apply RESOLVE_PENDING_EFFECT action to resolve a pending effect.

        This handles the target choice, choice index, and optional accept/decline
        for pending effects that require player input.
        """
        if not action.choice or "pending_effect_id" not in action.choice:
            raise IllegalActionError("RESOLVE_PENDING_EFFECT requires pending_effect_id in choice")

        pending_id = action.choice["pending_effect_id"]
        accept = action.choice.get("accept")
        choice_index = action.choice.get("choice_index")

        # Find the pending effect
        pe = None
        for item in state.pending_effects:
            if item.id == pending_id:
                pe = item
                break

        if pe is None:
            raise IllegalActionError(f"Pending effect {pending_id} not found")

        # Validate chooser
        if action.actor != pe.chooser_id:
            raise IllegalActionError(f"Player {action.actor} is not the current chooser (expected {pe.chooser_id})")

        # Handle optional accept/decline
        if pe.optional and pe.accepted is None and accept is not None:
            resolve_pending_effect_optional(state, pending_id, accept)
            if accept is False:
                # Decline - remove pending effect
                self._complete_bag_origin_pending_effect(state, pe, action.actor)

                complete_pending_effect(state, pending_id)
                return
            # Continue to resolve the effect
        elif pe.optional and pe.accepted is None and accept is None:
            # Optional effect requires explicit accept/decline
            raise IllegalActionError("Optional pending effect requires explicit accept/decline")

        raw = pe.raw or {}
        requirement_kind = raw.get("requirement_kind")

        if requirement_kind in {
            "scry_ordering",
            "search_selection",
            "reveal_routing",
            "named_card",
            "destination",
        }:
            try:
                if requirement_kind == "scry_ordering":
                    destinations = action.choice.get("destinations")
                    if destinations is not None:
                        resolve_scry_destinations(
                            state,
                            pending_id,
                            tuple(dict(destination) for destination in destinations),
                            engine=self,
                        )
                    else:
                        top_cards = tuple(action.choice.get("top_cards", ()))
                        bottom_cards = tuple(action.choice.get("bottom_cards", ()))
                        resolve_scry_ordering(state, pending_id, top_cards, bottom_cards, engine=self)

                elif requirement_kind == "search_selection":
                    selected_card_id = action.choice.get("selected_card_id")
                    if selected_card_id is None and choice_index is not None:
                        try:
                            selected_card_id = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid search choice index {choice_index}") from exc
                    if selected_card_id is None:
                        raise IllegalActionError("search_selection requires selected_card_id")
                    resolve_search_selection(state, pending_id, selected_card_id, engine=self)

                elif requirement_kind == "reveal_routing":
                    destination = action.choice.get("destination")
                    resolve_reveal_routing(state, pending_id, destination, engine=self)

                elif requirement_kind == "named_card":
                    named_card = action.choice.get("named_card")
                    if named_card is None and choice_index is not None:
                        try:
                            named_card = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid named-card choice index {choice_index}") from exc
                    if not named_card:
                        raise IllegalActionError("named_card requirement requires named_card")
                    resolve_named_card(state, pending_id, str(named_card), engine=self)

                elif requirement_kind == "destination":
                    destination = action.choice.get("destination")
                    if destination is None and choice_index is not None:
                        try:
                            destination = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid destination choice index {choice_index}") from exc
                    if not destination:
                        raise IllegalActionError("destination requirement requires destination")
                    resolve_destination_choice(state, pending_id, str(destination), engine=self)

            except ValueError as exc:
                raise IllegalActionError(str(exc)) from exc

            updated_pe = get_pending_effect_by_id(state, pending_id)
            if updated_pe:
                self._complete_bag_origin_pending_effect(state, updated_pe, action.actor)

            complete_pending_effect(state, pending_id)
            return

        # B9.3: General requirement_kind dispatch for Microfix 9 pending effects
        # These requirement kinds validate player input, persist to pe.raw["resolution_input"],
        # and pass selected values into effect resolution.
        if requirement_kind in {
            "amount",
            "target",
            "multi_target",
            "discard_choice",
            "choice",
            "optional",
            "opponent_choice",
            "enter_play_exerted",
        }:
            try:
                if requirement_kind == "amount":
                    amount = action.choice.get("amount")
                    if amount is None:
                        raise IllegalActionError("amount requirement requires amount in choice")
                    resolve_amount_choice(state, pending_id, int(amount), engine=self)

                elif requirement_kind == "target":
                    slotted_targets = action.choice.get("slotted_targets")
                    if slotted_targets is not None:
                        resolve_slotted_target_selection(state, pending_id, slotted_targets, engine=self)
                    else:
                        # Check if this is a player target
                        target_kind = action.choice.get("target_kind")
                        if target_kind == "player":
                            player_targets = action.choice.get("player_targets")
                            if player_targets is None:
                                raise IllegalActionError("target (player) requires player_targets in choice")
                            player_targets_tuple = tuple(player_targets) if player_targets else ()
                            resolve_player_target_selection(state, pending_id, player_targets_tuple, engine=self)
                        else:
                            targets = action.choice.get("targets")
                            if targets is None:
                                raise IllegalActionError("target requirement requires targets in choice")
                            targets_tuple = tuple(targets) if targets else ()
                            resolve_target_selection(state, pending_id, targets_tuple, engine=self)

                elif requirement_kind == "multi_target":
                    slotted_targets = action.choice.get("slotted_targets")
                    if slotted_targets is not None:
                        resolve_slotted_target_selection(state, pending_id, slotted_targets, engine=self)
                    else:
                        targets = action.choice.get("targets")
                        if targets is None:
                            raise IllegalActionError("multi_target requirement requires targets in choice")
                        targets_tuple = tuple(targets) if targets else ()
                        resolve_multi_target_selection(state, pending_id, targets_tuple, engine=self)

                elif requirement_kind == "discard_choice":
                    discard_card_ids = action.choice.get("discard_card_ids")
                    if discard_card_ids is None:
                        raise IllegalActionError("discard_choice requirement requires discard_card_ids in choice")
                    discard_tuple = tuple(discard_card_ids) if discard_card_ids else ()
                    resolve_discard_choice(state, pending_id, discard_tuple, engine=self)

                    if pe.origin == "activated_cost":
                        self._complete_activated_cost_pending_effect(state, pe, discard_tuple, action.actor)
                        complete_pending_effect(state, pending_id)
                        return

                    # After resolving the choice, apply the actual discards through _discard_eventful
                    # Get the target player and discard selected cards
                    target_player_id = pe.raw.get("target_player_id", pe.chooser_id)
                    for cid in discard_tuple:
                        self._discard_eventful(
                            state,
                            cid,
                            actor=target_player_id,
                            source_id=pe.source_id,
                            reason="effect",
                        )

                elif requirement_kind == "choice":
                    idx = choice_index if choice_index is not None else action.choice.get("choice_index")
                    if idx is None:
                        raise IllegalActionError("choice requirement requires choice_index")
                    resolve_choice_index(state, pending_id, int(idx), engine=self)

                elif requirement_kind == "optional":
                    # Optional accept/decline was already handled above; this is for
                    # requirement_kind="optional" with effect sequences
                    if accept is None:
                        raise IllegalActionError("optional requirement requires accept/decline")
                    resolve_optional_choice(state, pending_id, bool(accept), engine=self)

                elif requirement_kind == "opponent_choice":
                    # Opponent makes a choice - read choice_type from raw
                    choice_type = raw.get("choice_type", "choice")
                    if choice_type == "target" or choice_type == "targets":
                        slotted_targets = action.choice.get("slotted_targets")
                        if slotted_targets is not None:
                            resolve_slotted_target_selection(state, pending_id, slotted_targets, engine=self)
                        else:
                            # Check if this is a player target
                            target_kind = action.choice.get("target_kind")
                            if target_kind == "player":
                                player_targets = action.choice.get("player_targets")
                                if player_targets is None:
                                    raise IllegalActionError("opponent_choice (player target) requires player_targets in choice")
                                player_targets_tuple = tuple(player_targets) if player_targets else ()
                                resolve_player_target_selection(state, pending_id, player_targets_tuple, engine=self)
                            else:
                                targets = action.choice.get("targets")
                                if targets is None:
                                    raise IllegalActionError("opponent_choice (target) requires targets in choice")
                                targets_tuple = tuple(targets) if targets else ()
                                resolve_target_selection(state, pending_id, targets_tuple, engine=self)
                    elif choice_type == "amount":
                        amount = action.choice.get("amount")
                        if amount is None:
                            raise IllegalActionError("opponent_choice (amount) requires amount in choice")
                        resolve_amount_choice(state, pending_id, int(amount), engine=self)
                    else:
                        # Default: choice index
                        idx = choice_index if choice_index is not None else action.choice.get("choice_index")
                        if idx is None:
                            raise IllegalActionError("opponent_choice (choice) requires choice_index")
                        resolve_choice_index(state, pending_id, int(idx), engine=self)

                elif requirement_kind == "enter_play_exerted":
                    enter_exerted = action.choice.get("enter_play_exerted")
                    if enter_exerted is None:
                        raise IllegalActionError("enter_play_exerted requirement requires enter_play_exerted in choice")
                    resolve_enter_play_exerted_choice(state, pending_id, bool(enter_exerted), engine=self)

            except ValueError as exc:
                raise IllegalActionError(str(exc)) from exc

            # After resolving input, check if we should complete or continue to effect resolution
            # If this pending effect has no effects (pure input requirement), complete it
            # Otherwise, fall through to effect resolution
            if not pe.effects:
                updated_pe = get_pending_effect_by_id(state, pending_id) or pe
                self._complete_bag_origin_pending_effect(state, updated_pe, action.actor)
                complete_pending_effect(state, pending_id)
                return

        # Check if target input is required but not provided
        requirement = pe.current_requirement
        if pe.requires_target_input and requirement is not None:
            # Target selection required - validate that we have a target
            if not pe.selected_targets and not pe.selected_player_targets and action.target is None:
                raise IllegalActionError(f"Pending effect {pending_id} requires a target selection")
            # Validate the target is in the stored selections or action target
            if action.target is not None:
                resolve_pending_effect_target(state, pending_id, (action.target,))

        # Check if choice input is required but not provided
        if pe.requires_choice_input:
            if not pe.selected_choice and choice_index is None:
                raise IllegalActionError(f"Pending effect {pending_id} requires a choice selection")
            if choice_index is not None:
                resolve_pending_effect_choice(state, pending_id, choice_index)

        # Resolve the current effect
        current_effect = pe.current_effect
        if current_effect is not None:
            # Get card targets from stored selected_targets or action target.
            selected_targets = tuple(pe.selected_targets) if pe.selected_targets else ()
            selected_player_targets = (
                tuple(pe.selected_player_targets)
                or tuple((pe.raw or {}).get("selected_player_targets", ()) or ())
                or tuple((pe.raw or {}).get("resolution_input", {}).get("player_targets", ()) or ())
            )
            selected_target = selected_targets[0] if selected_targets else action.target
            if selected_player_targets and not selected_targets:
                selected_target = None

            # Player targets are passed through choice, matching player-target
            # action effects that consume EffectResolutionContext.choice.
            if selected_player_targets:
                selected_choice = selected_player_targets[0]
            else:
                selected_choice = pe.selected_choice if pe.selected_choice is not None else choice_index

            # Extract event context from raw
            raw = pe.raw or {}
            event = raw.get('event')
            event_payload = raw.get('event_payload', {})

            # Build context with target from pending effect and current_targets for multi-target effects
            # pending_trigger_id is set if origin is "bag", trigger_source/trigger_subject from event
            context = EffectResolutionContext(
                actor=pe.controller_id,
                source=pe.source_id,
                target=selected_target,
                event=event,
                event_payload=event_payload,
                choice=selected_choice,
                pending_trigger_id=pe.origin_id if pe.origin == "bag" else None,
                trigger_source=pe.source_id if pe.origin == "bag" else None,
                trigger_subject=raw.get("trigger_subject"),
                current_targets=selected_targets,
                context_targets=tuple(raw.get("context_targets", ()) or ()),
                slotted_targets=raw.get("slotted_targets") or raw.get("resolution_input", {}).get("slotted_targets"),
                destinations=tuple(
                    dict(destination)
                    for destination in (
                        raw.get("destinations")
                        or raw.get("resolution_input", {}).get("destinations")
                        or ()
                    )
                    if isinstance(destination, dict)
                ),
            )

            # Resolve the effect
            self.effect_resolver.resolve(state, current_effect, context)

        # Advance to next effect or complete
        advance_pending_effect(state, pending_id)

        # Check if complete
        updated_pe = get_pending_effect_by_id(state, pending_id)
        if updated_pe and updated_pe.is_complete:
            self._complete_bag_origin_pending_effect(state, updated_pe, action.actor)
            complete_pending_effect(state, pending_id)

    def _complete_activated_cost_pending_effect(
        self,
        state: GameState,
        pe: PendingEffect,
        discard_card_ids: tuple[int, ...],
        actor: int,
    ) -> None:
        from .abilities import get_activated_abilities_for_card
        from .costs import pay_cost, validate_cost_payable
        from lorcana_bot.card_logic.effect_utils import to_engine_cost_kind

        if pe.source_id is None or pe.source_id not in state.cards:
            raise IllegalActionError("Activated cost source is no longer in play")
        source_id = pe.source_id
        card_inst = state.cards[source_id]
        if card_inst.zone != ZONE_PLAY:
            raise IllegalActionError("Activated cost source is no longer in play")

        card_def = self.card_def(state, source_id)
        ability_index = pe.raw.get("ability_index")
        ability_id = pe.raw.get("ability_id")
        ability = None
        for candidate in get_activated_abilities_for_card(state, source_id, card_def, self):
            if ability_index is not None and candidate.ability_index == ability_index:
                ability = candidate
                break
            if ability_id is not None and candidate.ability_id == ability_id:
                ability = candidate
                break
        if ability is None:
            raise IllegalActionError("Activated ability for pending cost was not found")

        effects_supported, reason = validate_effects_supported(ability)
        if not effects_supported:
            raise IllegalActionError(reason)
        if not can_use_ability_this_turn(state, ability):
            raise IllegalActionError("Ability has already been used this turn")

        expected_discard = sum(
            int(cost.amount or 1)
            for cost in ability.costs
            if to_engine_cost_kind(cost.kind) == "discard"
        )
        if len(discard_card_ids) != expected_discard:
            raise IllegalActionError(f"Expected {expected_discard} discard cost cards")

        for cost in ability.costs:
            can_pay, cost_reason = validate_cost_payable(state, self, ability, cost)
            if not can_pay:
                raise IllegalActionError(f"Cannot pay cost {cost.kind}: {cost_reason}")

        target_player_id = int(pe.raw.get("target_player_id", actor))
        for cid in discard_card_ids:
            self._discard_eventful(
                state,
                cid,
                actor=target_player_id,
                source_id=source_id,
                reason="ability_cost",
            )

        paid_costs: list[str] = ["discardCards"] if discard_card_ids else []
        for cost in ability.costs:
            engine_kind = to_engine_cost_kind(cost.kind)
            if engine_kind in {"discard", "discard_chosen"}:
                continue
            pay_cost(state, self, ability, cost)
            paid_costs.append(cost.kind)

        card_inst.used_abilities_this_turn.append(ability.unique_use_key)
        selected_targets = tuple(pe.raw.get("selected_targets", ()) or ())
        execute_ability_effects(state, self, ability, selected_targets=selected_targets)
        self.emit_event(
            state,
            "ABILITY_USED",
            actor=actor,
            source=source_id,
            payload={
                "ability_id": ability.ability_id,
                "ability_index": ability.ability_index,
                "costs_paid": paid_costs,
                "effects_resolved": True,
            },
            queue_triggers=False,
        )

    def _complete_bag_origin_pending_effect(
        self,
        state: GameState,
        pe: PendingEffect,
        actor: int,
    ) -> bool:
        if pe.origin != "bag" or not pe.origin_id:
            return False

        bag_entry = next((entry for entry in state.bag if entry.id == pe.origin_id), None)
        if bag_entry is None:
            return False

        if pe.optional and pe.accepted is False:
            if not bag_entry.optional:
                raise IllegalActionError("Non-optional bag item cannot be declined")
            remove_bag_effect(state, bag_entry.id)
            self.emit_event(
                state,
                EVENT_TRIGGER_DECLINED,
                actor=actor,
                source=bag_entry.source_id,
                payload={"bag_id": bag_entry.id, "ability_id": bag_entry.ability_id},
                queue_triggers=False,
            )
            return True

        try:
            condition_met = (
                evaluate_condition(bag_entry.condition, state, bag_entry.event, bag_entry.source_id, self)
                if bag_entry.condition
                else True
            )
        except UnsupportedConditionError:
            remove_bag_effect(state, bag_entry.id)
            self.emit_event(
                state,
                EVENT_TRIGGER_SKIPPED,
                actor=actor,
                source=bag_entry.source_id,
                payload={"bag_id": bag_entry.id, "reason": "unsupported_condition_after_pending"},
                queue_triggers=False,
            )
            return True

        if not condition_met:
            remove_bag_effect(state, bag_entry.id)
            self.emit_event(
                state,
                EVENT_TRIGGER_SKIPPED,
                actor=actor,
                source=bag_entry.source_id,
                payload={"bag_id": bag_entry.id, "reason": "condition_not_met_after_pending"},
                queue_triggers=False,
            )
            return True

        bag_entry.resolution_input.update(pe.raw.get("resolution_input", {}) or {})
        record_bag_effect_resolution(state, bag_entry)
        remove_bag_effect(state, bag_entry.id)
        self.emit_event(
            state,
            EVENT_TRIGGER_RESOLVED,
            actor=actor,
            source=bag_entry.source_id,
            payload={"bag_id": bag_entry.id, "ability_id": bag_entry.ability_id},
            queue_triggers=False,
        )
        return True


@dataclass(slots=True)
class GameResult:
    winner: int | None
    turns: int
    final_lore: tuple[int, int]
    reason: str | None
    action_count: int


class GameRunner:
    def __init__(self, engine: GameEngine, max_actions: int = 1000):
        self.engine = engine
        self.max_actions = max_actions

    def play(
        self,
        state: GameState,
        bots: tuple[BotProtocol, BotProtocol],
        *,
        on_action: Callable[[dict[str, Any]], None] | None = None,
        strategy_names: tuple[str | None, str | None] | None = None,
    ) -> GameResult:
        actions_taken = 0
        while state.winner is None and actions_taken < self.max_actions:
            # B2: Actor priority: pending effects > bag resolver > active player
            if has_pending_effects(state):
                # Get the current pending effect's chooser (first pending effect)
                pe = state.pending_effects[0] if state.pending_effects else None
                if pe is None:
                    state.winner = state.opponent(state.active_player)
                    state.loss_reason = "pending_effect_had_no_chooser"
                    break
                player = pe.chooser_id
            elif has_pending_bag_items(state):
                player = get_next_bag_resolver(state)
                if player is None:
                    state.winner = state.opponent(state.active_player)
                    state.loss_reason = "bag_had_no_resolver"
                    break
            else:
                player = state.active_player

            legal = self.engine.legal_actions(state, player)
            if not legal:
                state.winner = state.opponent(player)
                state.loss_reason = f"player_{player}_had_no_legal_actions"
                break
            obs = self.engine.observe(state, player)
            setattr(self.engine, "_automation_live_state", state)
            idx = bots[player].choose_action(obs, legal, self.engine)
            if idx < 0 or idx >= len(legal):
                state.winner = state.opponent(player)
                state.loss_reason = f"player_{player}_bot_returned_illegal_index"
                break
            before_state = state
            event_start_index = len(before_state.event_log)
            action = legal[idx]
            state = self.engine.apply_action(state, action)
            if on_action is not None:
                on_action(
                    {
                        "ply": actions_taken,
                        "before": before_state,
                        "after": state,
                        "action": action,
                        "selected_candidate": {"index": idx, "action": action.compact()},
                        "strategy_name": strategy_names[player] if strategy_names else type(bots[player]).__name__,
                        "fallback_status": None,
                        "event_start_index": event_start_index,
                    }
                )
            actions_taken += 1

        if state.winner is None:
            if state.players[0].lore > state.players[1].lore:
                state.winner = 0
                state.loss_reason = "max_actions_lore_tiebreak"
            elif state.players[1].lore > state.players[0].lore:
                state.winner = 1
                state.loss_reason = "max_actions_lore_tiebreak"
            else:
                state.loss_reason = "max_actions_draw"

        return GameResult(
            winner=state.winner,
            turns=state.turn_number,
            final_lore=(state.players[0].lore, state.players[1].lore),
            reason=state.loss_reason,
            action_count=actions_taken,
        )

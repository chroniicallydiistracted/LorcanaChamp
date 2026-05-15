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
    EVENT_CARD_DRAWN,
    EVENT_CARD_EXERTED,
    EVENT_CARD_PLAYED,
    EVENT_CARD_READIED,
    EVENT_CARD_RETURNED_TO_HAND,
    EVENT_CHALLENGE_STARTED,
    EVENT_CHALLENGED,
    EVENT_CHARACTER_BANISHED,
    EVENT_CONCEDED,
    EVENT_DAMAGE_DEALT,
    EVENT_INKED,
    EVENT_KEPT_HAND,
    EVENT_LOCATION_LORE_GAINED,
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
    ZONE_PLAY,
)
from .state import ActionLogEntry, BagEffectEntry, CardInstance, GameEvent, GameState, PlayerState
from .effect_types import EffectResolutionContext
from .effects import EffectResolver
from .pending_effects import (
    has_pending_effects,
    get_current_pending_effect,
    get_pending_effect_by_id,
    get_valid_targets_for_requirement,
    resolve_pending_effect_target,
    resolve_pending_effect_choice,
    resolve_pending_effect_optional,
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
    register_replacement_effects_for_card,
    deregister_replacement_effects_from_card,
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
                
                if pe.optional and pe.accepted is None:
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
                # Accept is always available
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

        if not state.turn_player_has_inked:
            for cid in ps.hand:
                if self.card_def(state, cid).inkable:
                    actions.append(Action(ACTION_INK_CARD, actor=player, card=cid))

        for cid in ps.hand:
            card = self.card_def(state, cid)
            if self.play_cost(state, player, cid) <= self.available_ink(state, player):
                if card.card_type == CARD_ACTION and any(self._effect_requires_target(e) for e in card.effects):
                    targets = self._effect_targets_for_card(state, player, cid)
                    for target in targets:
                        actions.append(Action(ACTION_PLAY_CARD, actor=player, card=cid, target=target))
                else:
                    actions.append(Action(ACTION_PLAY_CARD, actor=player, card=cid))

        # B10: Alternative play modes - Songs and Shift
        from .play_modes import (
            is_song_card, get_singer_info, can_sing_song,
            get_shift_info, get_shift_targets, can_play_as_shift,
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
            # Use choice to encode the ability identifier
            actions.append(Action(
                ACTION_USE_ABILITY,
                actor=player,
                source=ability.source_instance_id,
                choice={"ability_id": ability.ability_id, "ability_index": ability.ability_index},
            ))

        actions.append(Action(ACTION_END_TURN, actor=player))
        actions.append(Action(ACTION_CONCEDE, actor=player))
        return actions

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

    def can_quest(self, state: GameState, source: int) -> bool:
        inst = state.cards[source]
        if inst.zone != ZONE_PLAY or inst.controller != state.active_player:
            return False
        card = self.card_def(state, source)
        if card.card_type != CARD_CHARACTER:
            return False
        if inst.exerted or inst.drying:
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

    def play_cost(self, state: GameState, player: int, instance_id: int) -> int:
        """Calculate play cost including static cost reductions."""
        card = self.card_def(state, instance_id)
        reductions = self._applicable_cost_reductions(state, player, card.card_type)
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


    def apply_action(self, state: GameState, action: Action, *, validate: bool = True) -> GameState:
        if validate and action not in self.legal_actions(state, action.actor):
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
            },
        )
        return damage_event

    def resolve_bag(self, state: GameState) -> None:
        # B2: Bag must be resolved through ACTION_RESOLVE_BAG, not silently cleared
        raise RuntimeError("Bag must be resolved through ACTION_RESOLVE_BAG. Use legal_actions() to get RESOLVE_BAG actions.")

    def resolve_banishes(self, state: GameState) -> None:
        """Resolve banishes with rich Lorcanito-aligned payloads including challenge context.
        
        B8: Uses banish_card() from replacement_effects to allow replacement effects
        to redirect the banish destination (e.g., return to hand instead of discard).
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
            from_zone = card.zone  # Store before move
            last_damage_source = card.last_damage_source
            happened_in_challenge = card.last_damage_was_challenge
            
            # B7.1: Deregister static effects before moving card from play
            deregister_static_effects_for_card(state, cid)
            # B8: Deregister replacement effects before moving card from play
            deregister_replacement_effects_from_card(state, cid)
            
            # B8: Use replacement-aware banish_card
            # last_damage_source can be int or str (card name), cast to int for the API
            source_for_banish: int | None = int(last_damage_source) if isinstance(last_damage_source, (int, str)) and last_damage_source else None
            banish_event = replacement_banish_card(
                state,
                target_id=cid,
                source_id=source_for_banish,
                default_destination=ZONE_DISCARD,
            )
            
            # Emit banish event with rich Lorcanito-aligned payload
            # Use actual_destination from replacement event
            self.emit_event(
                state,
                EVENT_CHARACTER_BANISHED,
                actor=controller,
                source=cid,
                payload={
                    "player_id": controller,
                    "subject_card_id": cid,
                    "from_zone": from_zone,
                    "to_zone": banish_event.actual_destination,
                    "happened_in_challenge": happened_in_challenge,
                    "last_damage_source": last_damage_source,
                    "banished_card_type": card_type,
                    "was_replaced": banish_event.was_replaced,
                    "replacement_description": banish_event.replacement_description,
                },
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
        card = state.cards[action.card]
        from_zone = card.zone  # Store before move
        state.move_card(action.card, ZONE_INKWELL)
        state.cards[action.card].exerted = False
        state.cards[action.card].added_to_ink_this_turn = True
        state.turn_player_has_inked = True
        state.players[action.actor].turn_flags.played_ink = True
        
        # Emit ink event with rich Lorcanito-aligned payload
        self.emit_event(
            state,
            EVENT_INKED,
            actor=action.actor,
            source=action.card,
            payload={
                "player_id": action.actor,
                "subject_card_id": action.card,
                "from_zone": from_zone,
                "to_zone": ZONE_INKWELL,
                "card_id": state.cards[action.card].card_id,
            },
        )

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
            state.move_card(action.card, ZONE_DISCARD)
            self._resolve_effects(state, player, action.card, action.target)
            to_zone = ZONE_DISCARD
        else:
            state.move_card(action.card, ZONE_PLAY)
            inst = state.cards[action.card]
            inst.exerted = False
            inst.damage = 0
            inst.drying = card.card_type == CARD_CHARACTER
            inst.just_played = True
            to_zone = ZONE_PLAY
            
        # B7.1: Register static effects for non-action permanents
        if card.card_type != CARD_ACTION:
            source_abilities = getattr(card, "source_abilities", None) or getattr(card, "abilities", ())
            register_static_effects_for_card(state, action.card, source_abilities)
            # B8: Register replacement effects for non-action cards entering play
            register_replacement_effects_for_card(state, action.card, source_abilities)
        
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
        state.cards[source].exerted = True
        state.cards[source].has_quested_this_turn = True
        state.players[action.actor].lore += lore
        
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
        source_inst.exerted = True

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

    def _apply_end_turn(self, state: GameState, action: Action) -> None:
        player = action.actor
        if not state.players[player].deck:
            state.winner = state.opponent(player)
            state.loss_reason = f"player_{player}_ended_turn_with_empty_deck"
            return
        state.players[player].turn_flags.passed_turn = True
        self.emit_event(state, EVENT_TURN_END, actor=player)
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
        for cid in state.players[player].play:
            state.cards[cid].temporary_keywords.clear()
            state.cards[cid].temporary_modifiers.clear()
        state.players[player].cost_reductions.clear()
        state.players[next_player].cost_reductions.clear()
        for cid in state.players[next_player].inkwell:
            inst = state.cards[cid]
            inst.exerted = False
            inst.added_to_ink_this_turn = False
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
            state.players[player].lore += amount
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
            state.move_card(cid, ZONE_DECK, controller=action.actor)
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
        from .play_modes import execute_sing_song
        
        if action.card is None:
            raise IllegalActionError("SING_SONG requires a song card")
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

    def _pay_ink(self, state: GameState, player: int, amount: int) -> None:
        ready_ink = [cid for cid in state.players[player].inkwell if not state.cards[cid].exerted]
        if len(ready_ink) < amount:
            raise IllegalActionError("Insufficient ink")
        for cid in ready_ink[:amount]:
            state.cards[cid].exerted = True

    def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]:
        card = self.card_def(state, source)
        targets: set[int] = set()
        for target_kind in self._effect_target_kinds(card.effects):
            if target_kind == "opposing_character":
                for cid in state.players[state.opponent(player)].play:
                    cdef = self.card_def(state, cid)
                    if cdef.card_type == CARD_CHARACTER and not self.has_keyword(state, cid, KEYWORD_WARD):
                        targets.add(cid)
            elif target_kind == "chosen_character":
                for who in (player, state.opponent(player)):
                    for cid in state.players[who].play:
                        cdef = self.card_def(state, cid)
                        if cdef.card_type != CARD_CHARACTER:
                            continue
                        if who != player and self.has_keyword(state, cid, KEYWORD_WARD):
                            continue
                        # B8: Check cannot-be-targeted restriction
                        if check_cannot_be_targeted(state, cid, source):
                            continue
                        targets.add(cid)
        return sorted(targets)

    def _effect_requires_target(self, effect) -> bool:
        return any(kind in {"opposing_character", "chosen_character"} for kind in self._effect_target_kinds((effect,)))

    def _effect_target_kinds(self, effects) -> set[str]:
        targets: set[str] = set()
        for effect in effects:
            if effect.target:
                targets.add(effect.target)
            if effect.effects:
                targets.update(self._effect_target_kinds(effect.effects))
        return targets

    def _resolve_effects(self, state: GameState, player: int, source: int, target: int | None) -> None:
        card = self.card_def(state, source)
        self.effect_resolver.resolve_many(state, card.effects, EffectResolutionContext(actor=player, source=source, target=target))

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
        event_payload = entry.event.payload if entry.event else {}
        event_target = (
            event_payload.get('event_target_id')
            or event_payload.get('target_id')
            or event_payload.get('defender_id')
            or event_payload.get('subject_card_id')
        )
        
        # Build current_targets tuple for collection-based targeting
        current_targets: tuple[int, ...] = ()
        if event_target:
            current_targets = (event_target,)
        
        context = EffectResolutionContext(
            actor=entry.controller_id,
            source=entry.source_id,
            target=event_target,
            event=entry.event,
            event_payload=event_payload,
            pending_trigger_id=entry.id,
            trigger_source=entry.source_id,
            trigger_subject=entry.event.subject_card_id if entry.event else None,
            current_targets=current_targets,
        )
        self._resolve_explicit_effects(state, entry.effects, context)
        
        # Record resolution
        record_bag_effect_resolution(state, entry)
        
        # Remove bag entry
        remove_bag_effect(state, bag_id)
        
        # Emit trigger resolved event
        self.emit_event(state, EVENT_TRIGGER_RESOLVED, actor=action.actor, source=entry.source_id, payload={"bag_id": bag_id, "ability_id": entry.ability_id}, queue_triggers=False)
        
        # B2: Flush any newly emitted trigger events
        # This is handled by the resolution boundary in apply_action

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
        abilities = get_activated_abilities_for_card(state, source_id, card_def)
        
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
        
        # Execute the ability (validates costs, pays them, and resolves effects)
        result = use_ability(state, self, ability)
        
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
                complete_pending_effect(state, pending_id)
                return
            # Continue to resolve the effect
        elif pe.optional and pe.accepted is None and accept is None:
            # Optional effect requires explicit accept/decline
            raise IllegalActionError("Optional pending effect requires explicit accept/decline")
        
        # Check if target input is required but not provided
        requirement = pe.current_requirement
        if pe.requires_target_input and requirement is not None:
            # Target selection required - validate that we have a target
            if not pe.selected_targets and action.target is None:
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
            # Get target from stored selected_targets or action target
            selected_target = pe.selected_targets[0] if pe.selected_targets else action.target
            # Get choice from stored selected_choice or action choice_index
            selected_choice = pe.selected_choice if pe.selected_choice is not None else choice_index
            
            # Extract event context from raw
            raw = pe.raw or {}
            event = raw.get('event')
            event_payload = raw.get('event_payload', {})
            
            # Build context with target from pending effect
            context = EffectResolutionContext(
                actor=pe.controller_id,
                source=pe.source_id,
                target=selected_target,
                event=event,
                event_payload=event_payload,
                choice=selected_choice,
            )
            
            # Resolve the effect
            self.effect_resolver.resolve(state, current_effect, context)
        
        # Advance to next effect or complete
        advance_pending_effect(state, pending_id)
        
        # Check if complete
        updated_pe = get_pending_effect_by_id(state, pending_id)
        if updated_pe and updated_pe.is_complete:
            complete_pending_effect(state, pending_id)


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

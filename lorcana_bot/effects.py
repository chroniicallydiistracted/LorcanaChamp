from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import EffectDef
from .constants import CARD_CHARACTER, ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_PLAY
from .effect_types import EffectResolutionContext, SUPPORTED_EFFECT_KINDS
from .state import GameState

if TYPE_CHECKING:
    from .engine import GameEngine


class EffectResolutionError(ValueError):
    pass


class EffectResolver:
    def __init__(self, engine: "GameEngine"):
        self.engine = engine

    def resolve_many(self, state: GameState, effects: tuple[EffectDef, ...], context: EffectResolutionContext) -> None:
        for effect in effects:
            self.resolve(state, effect, context)

    def resolve(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        if effect.kind not in SUPPORTED_EFFECT_KINDS:
            raise EffectResolutionError(f"Unsupported effect kind {effect.kind}")

        kind = effect.kind
        if kind == "sequence":
            self.resolve_many(state, effect.effects, context)
        elif kind == "optional":
            if self._optional_accepted(effect, context):
                self.resolve_many(state, effect.effects, context)
        elif kind == "choice":
            self._resolve_choice(state, effect, context)
        elif kind == "conditional":
            if self._condition_matches(state, effect, context):
                self.resolve_many(state, effect.effects, context)
        elif kind == "for_each":
            self._resolve_for_each(state, effect, context)
        elif kind == "draw":
            self.engine.draw_cards(state, self._target_player(state, effect, context), self._amount(effect))
        elif kind == "gain_lore":
            self.engine._gain_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(effect),
                source_id=context.source,
            )
        elif kind == "lose_lore":
            self.engine._lose_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(effect),
                source_id=context.source,
            )
        elif kind == "deal_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._deal_damage_eventful(
                    state,
                    target_id=target,
                    source_id=context.source,
                    amount=self._amount(effect),
                    actor=context.actor,
                    is_challenge=False,
                    apply_resist=True,
                )
        elif kind == "remove_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._remove_damage_eventful(
                    state,
                    target,
                    self._amount(effect),
                    actor=context.actor,
                    source_id=context.source,
                )
        elif kind == "banish":
            for target in self._target_cards(state, effect, context):
                self.engine._banish_eventful(
                    state,
                    target,
                    actor=context.actor,
                    source_id=context.source,
                    reason="effect",
                )
        elif kind == "discard":
            self._discard(state, effect, context)
        elif kind == "return_to_hand":
            for target in self._target_cards(state, effect, context):
                self.engine._return_to_hand_eventful(
                    state,
                    target,
                    actor=context.actor,
                    source_id=context.source,
                )
        elif kind == "ready":
            for target in self._target_cards(state, effect, context):
                self.engine._ready_eventful(
                    state,
                    target,
                    actor=context.actor,
                    source_id=context.source,
                )
        elif kind == "exert":
            for target in self._target_cards(state, effect, context):
                self.engine._exert_eventful(
                    state,
                    target,
                    actor=context.actor,
                    source_id=context.source,
                    reason="effect",
                )
        elif kind == "cost_reduction":
            state.players[context.actor].cost_reductions.append(
                {
                    "amount": self._amount(effect),
                    "card_type": effect.value if isinstance(effect.value, str) else None,
                    "duration": effect.duration or "this_turn",
                }
            )
        elif kind == "keyword_grant":
            keyword = self._keyword(effect)
            for target in self._target_cards(state, effect, context):
                if keyword not in state.cards[target].temporary_keywords:
                    state.cards[target].temporary_keywords.append(keyword)
        elif kind == "temporary_modifier":
            self._temporary_modifier(state, effect, context)
        # B4: Scry, search, reveal, and deck routing effects
        elif kind == "scry":
            self._resolve_scry(state, effect, context)
        elif kind == "look_at_top":
            self._resolve_look_at_top(state, effect, context)
        elif kind == "reveal_top_card":
            self._resolve_reveal_top_card(state, effect, context)
        elif kind == "reveal_hand":
            self._resolve_reveal_hand(state, effect, context)
        elif kind == "reveal_cards":
            self._resolve_reveal_cards(state, effect, context)
        elif kind == "search_deck":
            self._resolve_search_deck(state, effect, context)
        elif kind == "put_card_in_hand":
            self._resolve_put_card_in_hand(state, effect, context)
        elif kind == "put_card_on_top":
            self._resolve_put_card_on_top(state, effect, context)
        elif kind == "put_card_on_bottom":
            self._resolve_put_card_on_bottom(state, effect, context)
        elif kind == "put_card_in_discard":
            self._resolve_put_card_in_discard(state, effect, context)
        elif kind == "shuffle_deck":
            self._resolve_shuffle_deck(state, effect, context)
        elif kind == "name_a_card":
            self._resolve_name_a_card(state, effect, context)
        elif kind == "reveal_and_route":
            self._resolve_reveal_and_route(state, effect, context)

    def _resolve_choice(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        if not effect.effects:
            return
        index = 0
        if isinstance(context.choice, int):
            index = context.choice
        elif isinstance(effect.value, int):
            index = effect.value
        if index < 0 or index >= len(effect.effects):
            raise EffectResolutionError(f"Choice index {index} out of range for {len(effect.effects)} options")
        self.resolve(state, effect.effects[index], context)

    def _resolve_for_each(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        collection = str(effect.value or effect.target or "")
        targets = self._collection(state, collection, context)
        for target in targets:
            nested_context = EffectResolutionContext(
                actor=context.actor,
                source=context.source,
                target=target,
                choice=context.choice,
                optional_choices=context.optional_choices,
                # B2: Pass trigger context through for_each
                event=context.event,
                event_payload=context.event_payload,
                pending_trigger_id=context.pending_trigger_id,
                trigger_source=context.trigger_source,
                trigger_subject=context.trigger_subject,
                current_targets=context.current_targets,
            )
            self.resolve_many(state, effect.effects, nested_context)

    def _condition_matches(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> bool:
        condition = effect.condition or {}
        kind = condition.get("kind", "always")
        if kind == "always":
            return True
        if kind == "target_damaged":
            target = context.target
            return target is not None and state.cards[target].damage > 0
        if kind == "has_lore_at_least":
            player = context.actor if condition.get("player", "actor") == "actor" else state.opponent(context.actor)
            return state.players[player].lore >= int(condition.get("amount", 0))
        raise EffectResolutionError(f"Unsupported condition kind {kind}")

    def _optional_accepted(self, effect: EffectDef, context: EffectResolutionContext) -> bool:
        if not effect.optional:
            return True
        key = str(effect.value or effect.kind)
        return context.optional_choices.get(key, True)

    def _discard(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        targets = []
        if effect.target not in {"opponent", "opposing_player", "controller", "actor", "you"}:
            targets = self._target_cards(state, effect, context, require_target=False)
        if targets:
            for target in targets:
                if state.cards[target].zone != ZONE_HAND:
                    raise EffectResolutionError("Discard target must be in hand")
                self.engine._discard_eventful(
                    state,
                    target,
                    actor=state.cards[target].controller,
                    source_id=context.source,
                    reason="effect",
                )
            return

        player = self._target_player(state, effect, context)
        for _ in range(min(self._amount(effect), len(state.players[player].hand))):
            self.engine._discard_eventful(
                state,
                state.players[player].hand[0],
                actor=player,
                source_id=context.source,
                reason="effect",
            )

    def _temporary_modifier(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        if not isinstance(effect.value, dict):
            raise EffectResolutionError("temporary_modifier requires a dict value")
        for target in self._target_cards(state, effect, context):
            modifiers = state.cards[target].temporary_modifiers
            for key, value in effect.value.items():
                if key not in {"strength", "willpower", "lore"}:
                    raise EffectResolutionError(f"Unsupported temporary modifier {key}")
                modifiers[key] = modifiers.get(key, 0) + int(value)

    def _target_cards(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
        *,
        require_target: bool = True,
    ) -> list[int]:
        target = effect.target
        if target in {None, "chosen_character", "chosen_card", "chosen_item", "chosen_location", "target", "opposing_character"}:
            if context.target is None:
                if require_target:
                    raise EffectResolutionError(f"Effect {effect.kind} requires a target")
                return []
            return [context.target]
        if target == "self":
            if context.source is None:
                raise EffectResolutionError(f"Effect {effect.kind} requires a source")
            return [context.source]
        # Trigger-derived targets
        if target == "event_source":
            if context.trigger_source is None:
                if require_target:
                    raise EffectResolutionError(f"Effect {effect.kind} requires trigger_source")
                return []
            return [context.trigger_source]
        if target == "event_target":
            # B2: Normalized event target resolution priority
            # 1. context.target (already normalized from payload)
            if context.target is not None:
                return [context.target]
            # 2. context.current_targets[0]
            if context.current_targets:
                return [context.current_targets[0]]
            # 3. Fall through to event_payload (for legacy/testing)
            if context.event_payload:
                event_target_id = (
                    context.event_payload.get("event_target_id")
                    or context.event_payload.get("target_id")
                    or context.event_payload.get("defender_id")
                )
                if event_target_id:
                    return [event_target_id]
            if require_target:
                raise EffectResolutionError(f"Effect {effect.kind} requires event_target")
            return []
        if target == "trigger_subject":
            # B2: Normalized trigger subject resolution priority
            # 1. context.trigger_subject
            if context.trigger_subject is not None:
                return [context.trigger_subject]
            # 2. context.event_payload['subject_card_id']
            if context.event_payload and "subject_card_id" in context.event_payload:
                return [context.event_payload["subject_card_id"]]
            if require_target:
                raise EffectResolutionError(f"Effect {effect.kind} requires trigger_subject")
            return []
        if target in {"your_characters", "your_other_characters", "opposing_characters", "all_characters", "damaged_characters", "opposing_damaged_characters"}:
            return self._collection(state, target, context)
        raise EffectResolutionError(f"Unsupported card target {target!r} for {effect.kind}")

    def _collection(self, state: GameState, collection: str, context: EffectResolutionContext) -> list[int]:
        players: tuple[int, ...]
        # B2: Determine collection based on target type
        if collection in {"your_characters", "friendly_characters"}:
            players = (context.actor,)
        elif collection == "your_other_characters":
            players = (context.actor,)
        elif collection in {"opposing_characters", "opposing_damaged_characters"}:
            players = (state.opponent(context.actor),)
        elif collection in {"damaged_characters", "all_characters"}:
            players = (context.actor, state.opponent(context.actor))
        else:
            raise EffectResolutionError(f"Unsupported for_each collection {collection!r}")
        
        result: list[int] = []
        for player in players:
            for cid in state.players[player].play:
                if self.engine.card_def(state, cid).card_type != CARD_CHARACTER:
                    continue
                
                # Filter out source from your_other_characters
                if collection == "your_other_characters" and cid == context.source:
                    continue
                
                # Filter by damage state
                if collection == "damaged_characters" and state.cards[cid].damage == 0:
                    continue
                if collection == "opposing_damaged_characters" and state.cards[cid].damage == 0:
                    continue
                
                result.append(cid)
        return result

    def _target_player(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> int:
        if effect.target in {None, "controller", "actor", "you"}:
            return context.actor
        if effect.target in {"opponent", "opposing_player"}:
            return state.opponent(context.actor)
        if effect.target == "chosen_player":
            if context.choice not in {0, 1}:
                raise EffectResolutionError("chosen_player requires context.choice of 0 or 1")
            return int(context.choice)
        raise EffectResolutionError(f"Unsupported player target {effect.target!r} for {effect.kind}")

    def _amount(self, effect: EffectDef) -> int:
        return int(effect.amount or 0)

    def _keyword(self, effect: EffectDef) -> str:
        if not effect.keyword:
            raise EffectResolutionError("keyword_grant requires keyword")
        return effect.keyword.strip().upper().replace(" ", "_")

    # B4: Scry, search, reveal, and deck routing effect handlers
    # These effects typically require pending player input for ordering/routing

    def _resolve_scry(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle scry effect - look at top N cards and order them.
        
        Scry requires creating a pending effect that allows the player to:
        1. Look at the top N cards of their deck (private)
        2. Put any number on top in any order
        3. Put the rest on bottom in any order
        
        Uses create_scry_pending_effect which stores top N card IDs privately
        and does NOT move cards until resolve_scry_ordering is called.
        """
        from .pending_effects import create_scry_pending_effect
        
        amount = self._amount(effect)
        if amount <= 0:
            return
        
        # Create proper scry pending effect with requirement tracking
        create_scry_pending_effect(
            state=state,
            controller_id=context.actor,
            chooser_id=context.actor,
            source_id=context.source,
            source_card_id=self.engine.card_def(state, context.source).id if context.source else None,
            amount=amount,
            origin="scry",
        )

    def _resolve_look_at_top(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle look_at_top effect - reveal top N cards without moving them.
        
        This is informational only for the player who controls the effect.
        The cards are revealed but stay on top of the deck.
        """
        # Look at top cards - this is for triggering player info only
        # Cards stay on deck, just the player gets to see them
        amount = self._amount(effect)
        player_deck = state.players[context.actor].deck
        
        # Emit reveal event for the looked-at cards (private info)
        top_cards = player_deck[:min(amount, len(player_deck))]
        if top_cards:
            self.engine.emit_event(
                state,
                "LOOKED_AT_TOP_CARDS",
                actor=context.actor,
                source=context.source,
                payload={
                    "count": len(top_cards),
                    "card_ids": top_cards,  # Only revealed to the player
                    "private": True,
                },
                queue_triggers=False,
            )

    def _resolve_reveal_top_card(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle reveal_top_card effect - reveal the top card of a deck.
        
        The card identity becomes public and is routed according to effect.value.
        """
        amount = self._amount(effect)
        if amount <= 0:
            amount = 1
        
        player = self._target_player(state, effect, context)
        player_deck = state.players[player].deck
        
        if not player_deck:
            return
        
        # Reveal top card(s)
        revealed_cards = []
        for i in range(min(amount, len(player_deck))):
            cid = player_deck[i]
            inst = state.cards[cid]
            
            # Mark as revealed (public info)
            inst.revealed = True
            revealed_cards.append(cid)
            
            # Emit public reveal event
            self.engine.emit_event(
                state,
                "CARD_REVEALED",
                actor=player,
                source=cid,
                payload={
                    "card_id": cid,
                    "card_def_id": inst.card_id,
                    "from_zone": ZONE_DECK,
                    "player": player,
                },
            )
        
        # Route the revealed card(s) according to effect value
        if effect.value:
            destination = str(effect.value)
            for cid in revealed_cards:
                if destination == "hand":
                    self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)
                elif destination == "discard":
                    self.engine._move_card_eventful(state, cid, ZONE_DISCARD, actor=player, source_id=context.source)
                elif destination == "play":
                    # Only characters can go to play
                    cdef = self.engine.card_def(state, cid)
                    if cdef.card_type == "character":
                        self.engine._move_card_eventful(state, cid, ZONE_PLAY, actor=player, source_id=context.source)
                # put_on_top and put_on_bottom handled separately

    def _resolve_reveal_hand(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle reveal_hand effect - reveal all cards in hand.
        
        The card identities become public and are routed according to effect.value.
        """
        player = self._target_player(state, effect, context)
        hand = state.players[player].hand
        
        # Reveal all cards in hand
        for cid in hand:
            inst = state.cards[cid]
            inst.revealed = True
            
            # Emit public reveal event
            self.engine.emit_event(
                state,
                "HAND_REVEALED",
                actor=player,
                source=cid,
                payload={
                    "card_id": cid,
                    "card_def_id": inst.card_id,
                    "from_zone": ZONE_HAND,
                    "player": player,
                },
            )

    def _resolve_reveal_cards(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle reveal_cards effect - reveal specific cards.
        
        The card identities become public.
        """
        # Get cards to reveal from context.target or effect.target
        cards_to_reveal = self._target_cards(state, effect, context, require_target=False)
        
        for cid in cards_to_reveal:
            inst = state.cards[cid]
            inst.revealed = True
            
            # Emit public reveal event
            self.engine.emit_event(
                state,
                "CARDS_REVEALED",
                actor=context.actor,
                source=cid,
                payload={
                    "card_id": cid,
                    "card_def_id": inst.card_id,
                },
            )

    def _resolve_search_deck(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle search_deck effect - search deck for cards matching a filter.
        
        This requires pending player input to select which card to take.
        The filter is specified in effect.value as a card type, keyword, or name.
        
        Uses create_search_pending_effect which stores candidate card IDs privately
        and requires explicit selection before moving.
        """
        from .pending_effects import create_search_pending_effect
        
        player = self._target_player(state, effect, context)
        player_deck = state.players[player].deck
        
        if not player_deck:
            return
        
        # Parse filter from effect.value (card_type, keyword, or name)
        filter_desc = str(effect.value) if effect.value else None
        
        # For now, include all deck cards as candidates (full search)
        # In a real implementation, this would filter based on effect.value
        candidate_ids = tuple(player_deck)
        
        # Determine destination from effect or default
        destination = str(effect.value) if effect.value else "hand"
        
        # Create proper search pending effect with requirement tracking
        create_search_pending_effect(
            state=state,
            controller_id=context.actor,
            chooser_id=player,  # Player whose deck is being searched makes the choice
            source_id=context.source,
            source_card_id=self.engine.card_def(state, context.source).id if context.source else None,
            candidate_ids=candidate_ids,
            destination=destination,
            shuffle_after=True,  # Most search effects shuffle after
            filter_desc=filter_desc,
            max_select=1,
            origin="search_deck",
        )

    def _resolve_put_card_in_hand(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle put_card_in_hand effect - move selected card to hand.
        
        The card to move is determined by context.choice or the pending effect selection.
        """
        # The card to move should be specified in context.choice (card instance id)
        card_id = context.choice
        if card_id is None:
            # No specific card - this is an error unless it's from a pending effect
            return
        
        if card_id in state.cards:
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_HAND,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
                event_type="CARD_MOVED_TO_HAND",
                payload={"player": state.cards[card_id].owner},
            )

    def _resolve_put_card_on_top(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle put_card_on_top effect - move card to top of deck.
        
        The card to move is determined by context.choice or the pending effect selection.
        """
        # The card to move should be specified in context.choice
        card_id = context.choice
        if card_id is None:
            return
        
        if card_id in state.cards:
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
                index=0,
            )

    def _resolve_put_card_on_bottom(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle put_card_on_bottom effect - move card to bottom of deck.
        
        The card to move is determined by context.choice or the pending effect selection.
        """
        # The card to move should be specified in context.choice
        card_id = context.choice
        if card_id is None:
            return
        
        if card_id in state.cards:
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
            )

    def _resolve_put_card_in_discard(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle put_card_in_discard effect - move card to discard.
        
        The card to move is determined by context.choice or the pending effect selection.
        """
        # The card to move should be specified in context.choice
        card_id = context.choice
        if card_id is None:
            return
        
        if card_id in state.cards:
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DISCARD,
                actor=context.actor,
                source_id=context.source,
            )

    def _resolve_shuffle_deck(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle shuffle_deck effect - shuffle the deck.
        
        Uses deterministic shuffling based on game seed.
        """
        import random
        player = self._target_player(state, effect, context)
        state.shuffle_counter += 1
        rng = random.Random(f"{state.seed}:shuffle_effect:{player}:{state.shuffle_counter}")
        rng.shuffle(state.players[player].deck)

    def _resolve_name_a_card(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle name_a_card effect - name a specific card.
        
        This requires pending player input to choose the card name.
        The named card is then used for comparison or routing.
        """
        # Create a pending effect that requires player to name a card
        named_card_id = context.choice
        if named_card_id is None:
            from .pending_effects import create_named_card_pending_effect

            raw_valid_ids = effect.raw.get("valid_card_def_ids") or effect.raw.get("validCardDefIds") or ()
            valid_card_def_ids = tuple(str(card_id) for card_id in raw_valid_ids)
            create_named_card_pending_effect(
                state=state,
                controller_id=context.actor,
                chooser_id=context.actor,
                source_id=context.source,
                source_card_id=self.engine.card_def(state, context.source).id if context.source else None,
                valid_card_def_ids=valid_card_def_ids,
                origin="name_a_card",
            )

    def _resolve_reveal_and_route(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle reveal_and_route effect - reveal a card and move it to a destination.
        
        This combines reveal and routing in one effect.
        """
        # Get destination from effect.value
        destination = str(effect.value) if effect.value else "hand"
        
        player = self._target_player(state, effect, context)
        player_deck = state.players[player].deck
        
        if not player_deck:
            return
        
        # Reveal top card
        cid = player_deck[0]
        inst = state.cards[cid]
        inst.revealed = True
        
        # Emit public reveal event
        self.engine.emit_event(
            state,
            "CARD_REVEALED",
            actor=player,
            source=cid,
            payload={
                "card_id": cid,
                "card_def_id": inst.card_id,
                "from_zone": ZONE_DECK,
                "player": player,
            },
        )
        
        # Route to destination
        if destination == "hand":
            self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)
        elif destination == "discard":
            self.engine._move_card_eventful(state, cid, ZONE_DISCARD, actor=player, source_id=context.source)
        elif destination == "play":
            cdef = self.engine.card_def(state, cid)
            if cdef.card_type == "character":
                self.engine._move_card_eventful(state, cid, ZONE_PLAY, actor=player, source_id=context.source)

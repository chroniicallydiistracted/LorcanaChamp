from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .cards import EffectDef
from .constants import ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
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
            self.engine.draw_cards(
                state,
                self._target_player(state, effect, context),
                self._amount(effect, context),
                private=True,
            )
        elif kind == "gain_lore":
            self.engine._gain_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(effect, context),
                source_id=context.source,
            )
        elif kind == "lose_lore":
            self.engine._lose_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(effect, context),
                source_id=context.source,
            )
        elif kind == "deal_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._deal_damage_eventful(
                    state,
                    target_id=target,
                    source_id=context.source,
                    amount=self._amount(effect, context),
                    actor=context.actor,
                    is_challenge=False,
                    apply_resist=True,
                )
        elif kind == "remove_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._remove_damage_eventful(
                    state,
                    target,
                    self._amount(effect, context),
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
                    "amount": self._amount(effect, context),
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
        elif kind == "put_into_inkwell":
            self._resolve_put_into_inkwell(state, effect, context)

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
                current_targets=(target,),
                context_targets=context.context_targets,
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
        # Check for explicit discard choice requirements
        raw = effect.raw or {}
        is_chosen = raw.get("chosen", False)
        chosen_by = raw.get("chosen_by") or raw.get("chosenBy")

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
        amount = self._amount(effect, context)

        # Determine if explicit choice is required
        # Rule 1: If effect.raw["chosen"] is true, create pending discard_choice
        # Rule 2: If effect.raw["chosen_by"] or effect.raw["chosenBy"] is "opponent", chooser is opponent
        # Rule 3: If target player is not the resolving actor and explicit choice is required, create pending
        # Rule 4: If no explicit choice is required, preserve current deterministic discard behavior

        requires_explicit_choice = is_chosen or chosen_by is not None

        if requires_explicit_choice:
            # Build discard candidates from the target player's hand
            candidate_ids = tuple(state.players[player].hand)

            # Determine the chooser
            if chosen_by == "opponent":
                chooser_id = state.opponent(context.actor)
            else:
                # Default: controller chooses (for "chosen" without "chosen_by")
                chooser_id = context.actor

            # Determine min/max selection count
            max_discard = min(amount, len(candidate_ids))
            if max_discard == 0:
                return  # Nothing to discard

            # Import and create the pending effect
            from lorcana_bot.pending_effects import create_discard_choice_pending_effect

            source_card_id = None
            if context.source is not None and context.source in state.cards:
                source_card_id = state.cards[context.source].card_id

            create_discard_choice_pending_effect(
                state,
                controller_id=context.actor,
                chooser_id=chooser_id,
                source_id=context.source,
                source_card_id=source_card_id,
                target_player_id=player,
                candidate_ids=candidate_ids,
                min_select=1,
                max_select=max_discard,
                origin="discard_effect",
                raw=raw,  # Pass through raw metadata for effect tracking
            )
            return

        # No explicit choice required - preserve deterministic behavior
        for _ in range(min(amount, len(state.players[player].hand))):
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
        descriptor = self._normalize_effect_target(effect.target)
        if descriptor is None:
            if require_target:
                raise EffectResolutionError(f"Unsupported card target {effect.target!r} for {effect.kind}")
            return []

        if self._uses_selected_card_context(descriptor.selector):
            selected = self._selected_card_targets_from_context(context)
            if not selected:
                if require_target:
                    raise EffectResolutionError(f"Effect {effect.kind} requires a target")
                return []
            return self._resolve_selected_card_targets(state, descriptor, context, selected)

        targets = self._resolve_descriptor_card_targets(state, descriptor, context)
        if not targets and require_target:
            raise EffectResolutionError(f"Effect {effect.kind} found no valid targets for {descriptor.selector!r}")
        return targets

    def _collection(self, state: GameState, collection: str, context: EffectResolutionContext) -> list[int]:
        descriptor = self._normalize_effect_target(collection)
        if descriptor is None:
            raise EffectResolutionError(f"Unsupported for_each collection {collection!r}")
        targets = self._resolve_descriptor_card_targets(state, descriptor, context)
        if not targets:
            return []
        return targets

    def _target_player(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> int:
        descriptor = self._normalize_player_target(effect.target)
        if descriptor is None:
            raise EffectResolutionError(f"Unsupported player target {effect.target!r} for {effect.kind}")

        from .targeting import resolve_candidate_player_ids

        query_context = self._target_query_context(context)
        candidates = resolve_candidate_player_ids(state, descriptor, query_context)

        if descriptor.selector == "chosen_player":
            if not isinstance(context.choice, int):
                raise EffectResolutionError("chosen_player requires context.choice of a player id")
            if context.choice not in candidates:
                raise EffectResolutionError(f"chosen_player target {context.choice!r} is not valid")
            return int(context.choice)

        if len(candidates) != 1:
            raise EffectResolutionError(
                f"Player target {effect.target!r} resolved to {len(candidates)} players"
            )
        return candidates[0]

    def _normalize_effect_target(self, raw_target: Any):
        from .targeting import normalize_target_descriptor

        target = "target" if raw_target is None else raw_target
        descriptor = normalize_target_descriptor(target)
        if descriptor is not None:
            return descriptor
        return None

    def _normalize_player_target(self, raw_target: Any):
        from .targeting import normalize_target_descriptor

        if raw_target in {None, "controller", "actor"}:
            return normalize_target_descriptor("you")
        if raw_target == "opposing_player":
            return normalize_target_descriptor("opponent")
        return normalize_target_descriptor(raw_target)

    def _target_query_context(self, context: EffectResolutionContext):
        from .targeting import TargetQueryContext

        event_payload = dict(context.event_payload or {})
        if context.trigger_source is not None:
            event_payload.setdefault("source", context.trigger_source)
            event_payload.setdefault("source_id", context.trigger_source)
        elif context.source is not None:
            event_payload.setdefault("source", context.source)
            event_payload.setdefault("source_id", context.source)

        event_target = context.target
        if event_target is None and context.current_targets:
            event_target = context.current_targets[0]
        if event_target is not None:
            event_payload.setdefault("target", event_target)
            event_payload.setdefault("target_id", event_target)
            event_payload.setdefault("event_target_id", event_target)

        if context.trigger_subject is not None:
            event_payload.setdefault("subject", context.trigger_subject)
            event_payload.setdefault("trigger_subject", context.trigger_subject)
            event_payload.setdefault("subject_id", context.trigger_subject)
            event_payload.setdefault("subject_card_id", context.trigger_subject)

        return TargetQueryContext(
            actor=context.actor,
            source_id=context.source,
            event_payload=event_payload,
            current_targets=context.current_targets,
            context_targets=context.context_targets,
        )

    def _uses_selected_card_context(self, selector: str) -> bool:
        from .targeting import requires_explicit_target_selection

        return selector == "target" or requires_explicit_target_selection(selector)

    def _selected_card_targets_from_context(self, context: EffectResolutionContext) -> tuple[int, ...]:
        if context.current_targets:
            return context.current_targets
        if context.target is not None:
            return (context.target,)
        return ()

    def _resolve_selected_card_targets(
        self,
        state: GameState,
        descriptor,
        context: EffectResolutionContext,
        selected: tuple[int, ...],
    ) -> list[int]:
        from .targeting import resolve_candidate_card_ids

        query_context = self._target_query_context(context)
        constrained = replace(descriptor, selector="current_targets")
        constrained_context = replace(query_context, current_targets=selected)
        return list(resolve_candidate_card_ids(state, self.engine, constrained, constrained_context))

    def _resolve_descriptor_card_targets(self, state: GameState, descriptor, context: EffectResolutionContext) -> list[int]:
        from .targeting import resolve_candidate_card_ids

        return list(resolve_candidate_card_ids(state, self.engine, descriptor, self._target_query_context(context)))

    def _amount(self, effect: EffectDef, context: EffectResolutionContext) -> int:
        """Resolve effect amount from various supported shapes.

        Supported shapes:
        - integer: direct int amount on EffectDef (including 0)
        - numeric string: string that converts to int (from raw["amount"])
        - {"type": "static", "amount": N}: explicit static amount object
        - {"type": "event-snapshot", "key": "drawnCount"}: event snapshot lookup

        Raises:
            EffectResolutionError: for unsupported amount shapes (never returns 0)
        """
        raw_source = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else {}
        raw_amount = raw_source.get("amount") if "amount" in raw_source else effect.raw.get("amount")
        if raw_amount is not None:
            if isinstance(raw_amount, (int, float)):
                return int(raw_amount)
            if isinstance(raw_amount, str):
                if raw_amount.isdigit():
                    return int(raw_amount)
                raise EffectResolutionError(f"Unsupported amount shape: {raw_amount!r}")

        # Check for object-style amount in raw
        if isinstance(raw_amount, dict):
            amount_type = raw_amount.get("type")
            if amount_type == "static":
                static_amount = raw_amount.get("amount")
                if static_amount is not None:
                    return int(static_amount)
            elif amount_type == "event-snapshot":
                key = raw_amount.get("key")
                if key:
                    event_payload = context.event_payload or {}
                    event_snapshot = getattr(context.event, "event_snapshot", {}) or {}
                    value = event_payload.get(key)
                    if value is None:
                        value = event_snapshot.get(key)
                    if value is not None:
                        return int(value)
                    raise EffectResolutionError(f"Event snapshot amount key {key!r} was not present")

        # Check direct amount - only if raw["amount"] was not present
        if raw_amount is None and effect.amount is not None:
            return int(effect.amount)

        # Unsupported amount shape - raise instead of returning 0
        unsupported_shape = raw_amount if raw_amount is not None else effect.amount
        raise EffectResolutionError(
            f"Unsupported amount shape: {unsupported_shape!r}. "
            f"Supported shapes: integer, numeric string, {{'type': 'static', 'amount': N}}, "
            f"{{'type': 'event-snapshot', 'key': 'KEY_NAME'}}"
        )

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

        amount = self._amount(effect, context)
        if amount <= 0:
            return

        # Create proper scry pending effect with requirement tracking
        source_raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        raw_destinations = source_raw.get("destinations") if isinstance(source_raw, dict) else None
        destinations = tuple(dict(destination) for destination in raw_destinations if isinstance(destination, dict)) if isinstance(raw_destinations, list) else ()
        create_scry_pending_effect(
            state=state,
            controller_id=context.actor,
            chooser_id=context.actor,
            source_id=context.source,
            source_card_id=self.engine.card_def(state, context.source).id if context.source else None,
            amount=amount,
            destinations=destinations,
            origin="scry",
        )

    def _resolve_look_at_top(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Handle look_at_top effect - reveal top N cards without moving them.

        This is informational only for the player who controls the effect.
        The cards are revealed but stay on top of the deck.
        """
        # Look at top cards - this is for triggering player info only
        # Cards stay on deck, just the player gets to see them
        amount = self._amount(effect, context)
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
        amount = self._amount(effect, context)
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

        source_raw = self._source_raw(effect)
        filter_desc = self._search_filter_desc(source_raw)
        candidate_ids = tuple(
            cid for cid in player_deck
            if self._matches_search_filter(state, cid, source_raw)
        )
        if not candidate_ids:
            return

        # Determine destination from effect or default
        destination = self._search_destination(source_raw)

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

    def _source_raw(self, effect: EffectDef) -> dict[str, Any]:
        raw = effect.raw or {}
        nested = raw.get("raw") if isinstance(raw, dict) else None
        if isinstance(nested, dict):
            return nested
        return raw if isinstance(raw, dict) else {}

    def _matches_search_filter(self, state: GameState, card_id: int, source_raw: dict[str, Any]) -> bool:
        card_type = source_raw.get("cardType") or source_raw.get("card_type")
        card_name = source_raw.get("cardName") or source_raw.get("name")
        classification = source_raw.get("classification")
        max_cost = source_raw.get("maxCost")
        if card_type is None and card_name is None and classification is None and max_cost is None:
            return True

        card = self.engine.card_def(state, card_id)
        if card_type:
            if card_type == "song":
                if card.card_type != "action" or "song" not in {sub.lower() for sub in card.subtypes}:
                    return False
            elif card_type == "floodborn":
                if "floodborn" not in {sub.lower() for sub in card.subtypes}:
                    return False
            elif card.card_type != str(card_type):
                return False

        if card_name and card.full_name != card_name and card.name != card_name:
            return False

        if classification and str(classification).lower() not in {sub.lower() for sub in card.subtypes}:
            return False

        if max_cost is not None:
            try:
                if card.cost > int(max_cost):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def _search_filter_desc(self, source_raw: dict[str, Any]) -> str | None:
        for key in ("cardType", "cardName", "classification", "maxCost"):
            if key in source_raw:
                return f"{key}:{source_raw[key]}"
        return None

    def _search_destination(self, source_raw: dict[str, Any]) -> str:
        if source_raw.get("putOnTop") is True:
            return "deck-top"
        destination = source_raw.get("putInto") or source_raw.get("destination") or "hand"
        return str(destination)

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

    def _resolve_put_into_inkwell(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        source_raw = self._source_raw(effect)
        exerted = bool(source_raw.get("exerted", True))
        for target in self._target_cards(state, effect, context):
            owner = state.cards[target].owner
            self.engine._put_into_inkwell_eventful(
                state,
                target,
                actor=owner,
                source_id=context.source,
                queue_triggers=False,
                exerted=exerted,
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
        source_raw = self._source_raw(effect)
        destination = self._route_destination(source_raw, effect.value)

        player = self._target_player(state, effect, context)
        player_deck = state.players[player].deck

        if not player_deck:
            return

        cid = player_deck[0]
        inst = state.cards[cid]
        reveal_public = source_raw.get("visibility", "public") != "private" and source_raw.get("private") is not True
        if reveal_public:
            inst.revealed = True

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
        else:
            self.engine.emit_event(
                state,
                "PRIVATE_CARD_LOOKED_AT",
                actor=player,
                source=context.source,
                payload={"private": True, "count": 1, "from_zone": ZONE_DECK, "player": player},
                queue_triggers=False,
            )

        if destination == "hand":
            self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)
        elif destination == "discard":
            self.engine._move_card_eventful(state, cid, ZONE_DISCARD, actor=player, source_id=context.source)
        elif destination == "deck-top":
            self.engine._move_card_eventful(state, cid, ZONE_DECK, actor=player, source_id=context.source, index=0)
        elif destination == "deck-bottom":
            self.engine._move_card_eventful(state, cid, ZONE_DECK, actor=player, source_id=context.source)
        elif destination == "inkwell":
            self.engine._put_into_inkwell_eventful(
                state,
                cid,
                actor=player,
                source_id=context.source,
                queue_triggers=False,
                exerted=bool(source_raw.get("exerted", True)),
            )
        elif destination == "play":
            cdef = self.engine.card_def(state, cid)
            if cdef.card_type == "character":
                self.engine._move_card_eventful(state, cid, ZONE_PLAY, actor=player, source_id=context.source)

    def _route_destination(self, source_raw: dict[str, Any], value: Any) -> str:
        destination = (
            source_raw.get("destination")
            or source_raw.get("putInto")
            or source_raw.get("put_into")
            or source_raw.get("to")
            or value
            or "hand"
        )
        normalized = str(destination).replace("_", "-").lower()
        return {
            "top": "deck-top",
            "deck": "deck-top",
            "decktop": "deck-top",
            "deck-top": "deck-top",
            "top-of-deck": "deck-top",
            "bottom": "deck-bottom",
            "deckbottom": "deck-bottom",
            "deck-bottom": "deck-bottom",
            "bottom-of-deck": "deck-bottom",
            "discard-pile": "discard",
            "ink": "inkwell",
        }.get(normalized, normalized)

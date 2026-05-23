from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .cards import EffectDef
from .constants import EVENT_MOVED_TO_LOCATION, ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
from .effect_types import EffectResolutionContext, SUPPORTED_EFFECT_KINDS
from .state import GameState

if TYPE_CHECKING:
    from .engine import GameEngine


class EffectResolutionError(ValueError):
    pass


class EffectResolver:
    def __init__(self, engine: "GameEngine"):
        self.engine = engine

    # ------------------------------------------------------------------
    # Lorcanito-aligned context builders
    # ------------------------------------------------------------------

    def _ctx(
        self,
        context: EffectResolutionContext,
        **updates: Any,
    ) -> EffectResolutionContext:
        """Return an updated frozen EffectResolutionContext."""
        return replace(context, **updates)

    def _chooser(self, context: EffectResolutionContext) -> int:
        return context.chooser if context.chooser is not None else context.actor

    def _state_resolution_signature(self, state: GameState) -> tuple[Any, ...]:
        """Snapshot board-visible state used to detect whether a leaf effect performed.

        Do not include pending_effects or bag length here. Creating pending input
        is not the same as performing the underlying effect for if-you-do.
        """
        player_sig = tuple(
            (
                tuple(player.deck),
                tuple(player.hand),
                tuple(player.play),
                tuple(player.discard),
                tuple(player.inkwell),
                int(player.lore),
            )
            for player in state.players
        )
        card_sig = tuple(
            sorted(
                (
                    card_id,
                    inst.zone,
                    inst.owner,
                    inst.controller,
                    inst.exerted,
                    inst.damage,
                    inst.location_instance_id,
                    tuple(getattr(inst, "cards_under", ()) or ()),
                    tuple(getattr(inst, "temporary_keywords", ()) or ()),
                    tuple(sorted(getattr(inst, "temporary_modifiers", {}) or {})),
                    tuple(getattr(inst, "temporary_granted_abilities", ()) or ()),
                )
                for card_id, inst in state.cards.items()
            )
        )
        return (player_sig, card_sig)

    def _mark_result(
        self,
        context: EffectResolutionContext,
        *,
        performed: bool,
        target_count: int = 0,
    ) -> EffectResolutionContext:
        return self._ctx(
            context,
            last_effect_performed=bool(performed),
            last_effect_target_count=int(target_count or 0),
        )

    def _mark_from_state_change(
        self,
        before: tuple[Any, ...],
        state: GameState,
        context: EffectResolutionContext,
        *,
        target_count: int = 0,
    ) -> EffectResolutionContext:
        return self._mark_result(
            context,
            performed=before != self._state_resolution_signature(state),
            target_count=target_count,
        )

    def _with_current_targets(
        self,
        context: EffectResolutionContext,
        targets: tuple[int, ...],
        *,
        target: int | None = None,
        performed: bool | None = None,
    ) -> EffectResolutionContext:
        if performed is None:
            performed = bool(targets)
        return self._ctx(
            context,
            target=target if target is not None else (targets[0] if targets else context.target),
            current_targets=tuple(int(target_id) for target_id in targets),
            target_selection_resolved=bool(targets),
            last_effect_performed=bool(performed),
            last_effect_target_count=len(targets),
        )

    def _with_slotted_targets(
        self,
        context: EffectResolutionContext,
        slotted_targets: dict[str, Any] | None,
    ) -> EffectResolutionContext:
        if not slotted_targets:
            return context
        flat = self._flatten_slotted_target_ids(slotted_targets)
        return self._ctx(
            context,
            slotted_targets=slotted_targets,
            current_targets=flat,
            target=flat[0] if flat else context.target,
            target_selection_resolved=bool(flat),
            last_effect_performed=bool(flat),
            last_effect_target_count=len(flat),
        )

    def _promote_current_targets_to_context(
        self,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Promote currentTargets into contextTargets after a sequence step.

        Mirrors Lorcanito's promoteCurrentSelectionTargetsToContext().
        """
        if not context.current_targets:
            return context
        combined = tuple(dict.fromkeys((*context.context_targets, *context.current_targets)))
        return self._ctx(
            context,
            context_targets=combined,
            current_targets=(),
            target=None,
        )

    def _flatten_slotted_target_ids(self, slotted_targets: dict[str, Any] | None) -> tuple[int, ...]:
        if not slotted_targets:
            return ()
        from .targeting import flatten_slotted_targets, normalize_slotted_target_input
        normalized = normalize_slotted_target_input(slotted_targets)
        return tuple(flatten_slotted_targets(normalized))

    def _emit_be_chosen_for_context(
        self,
        state: GameState,
        context: EffectResolutionContext,
        source_id: int | None = None,
    ) -> None:
        selected = tuple(dict.fromkeys((
            *(context.current_targets or ()),
            *self._flatten_slotted_target_ids(context.slotted_targets),
        )))
        if not selected:
            return
        if source_id is None:
            source_id = context.source
        if source_id is None or source_id not in state.cards:
            return
        try:
            self.engine._emit_be_chosen_events(
                state,
                actor=context.actor,
                source=source_id,
                selected_targets=selected,
            )
        except AttributeError:
            return

    def resolve_many(
        self,
        state: GameState,
        effects: tuple[EffectDef, ...],
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Resolve a sequence of effects while carrying Lorcanito selection state.

        Each child may update current_targets, context_targets, chooser,
        named_card, destinations, or last_effect_performed. The updated context
        must be passed to the next effect.
        """
        current_context = context
        for effect in effects:
            current_context = self.resolve(state, effect, current_context)
            current_context = self._promote_current_targets_to_context(current_context)
        return current_context

    def resolve(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        if effect.kind not in SUPPORTED_EFFECT_KINDS:
            raise EffectResolutionError(f"Unsupported effect kind {effect.kind}")

        kind = effect.kind

        if kind == "sequence":
            return self.resolve_many(state, effect.effects, context)

        if kind == "optional":
            return self._resolve_optional(state, effect, context)

        if kind == "choice":
            return self._resolve_choice(state, effect, context)

        if kind == "conditional":
            return self._resolve_conditional(state, effect, context)

        if kind == "select_target":
            return self._resolve_select_target(state, effect, context)

        if self._effect_needs_external_chooser(effect, context):
            self._create_pending_choice_for_effect(state, effect, context)
            return self._mark_result(context, performed=False)

        before = self._state_resolution_signature(state)

        if context.slotted_targets:
            context = self._with_slotted_targets(context, context.slotted_targets)
            self._emit_be_chosen_for_context(state, context)

        if kind == "restriction":
            self._resolve_restriction(state, effect, context)
        elif kind == "conditional":
            if self._condition_matches(state, effect, context):
                self.resolve_many(state, effect.effects, context)
        elif kind == "for_each":
            self._resolve_for_each(state, effect, context)
        elif kind == "draw":
            for player in self._target_players(state, effect, context):
                self.engine.draw_cards(state, player, self._amount(state, effect, context), private=True)
        elif kind == "draw_until_hand_size":
            for player in self._target_players(state, effect, context):
                target_size = self._draw_until_hand_size(effect)
                needed = max(0, target_size - len(state.players[player].hand))
                if needed:
                    self.engine.draw_cards(state, player, needed, private=True)
        elif kind == "gain_lore":
            self.engine._gain_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(state, effect, context),
                source_id=context.source,
            )
        elif kind == "lose_lore":
            self.engine._lose_lore_eventful(
                state,
                self._target_player(state, effect, context),
                self._amount(state, effect, context),
                source_id=context.source,
            )
        elif kind == "deal_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._deal_damage_eventful(
                    state,
                    target_id=target,
                    source_id=context.source,
                    amount=self._amount(state, effect, context),
                    actor=context.actor,
                    is_challenge=False,
                    apply_resist=True,
                )
        elif kind == "move_damage":
            self._resolve_move_damage(state, effect, context)
        elif kind == "move_to_location":
            self._resolve_move_to_location(state, effect, context)
        elif kind == "remove_damage":
            for target in self._target_cards(state, effect, context):
                self.engine._remove_damage_eventful(
                    state,
                    target,
                    self._amount(state, effect, context),
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
        elif kind == "return_from_discard":
            self._resolve_return_from_discard(state, effect, context)
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
                    "amount": self._amount(state, effect, context),
                    "card_type": effect.value if isinstance(effect.value, str) else None,
                    "duration": effect.duration or "this_turn",
                }
            )
        elif kind == "additional_inkwell":
            allowance = int(effect.amount or 1)
            key = f"additional_inkwell:{context.actor}"
            state.turn_metadata[key] = int(state.turn_metadata.get(key, 0) or 0) + allowance
        elif kind == "pay_cost":
            self._resolve_pay_cost(state, effect, context)
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
        elif kind == "count":
            self._resolve_count(state, effect, context)
        elif kind == "reveal_hand":
            self._resolve_reveal_hand(state, effect, context)
        elif kind == "reveal_cards":
            self._resolve_reveal_cards(state, effect, context)
        elif kind == "search_deck":
            self._resolve_search_deck(state, effect, context)
        elif kind == "put_card_in_hand":
            self._resolve_put_card_in_hand(state, effect, context)
        elif kind == "put_card_on_top":
            return self._resolve_put_card_on_top(state, effect, context)
        elif kind == "put_card_on_bottom":
            return self._resolve_put_card_on_bottom(state, effect, context)
        elif kind == "put_card_in_discard":
            self._resolve_put_card_in_discard(state, effect, context)
        elif kind == "shuffle_deck":
            self._resolve_shuffle_deck(state, effect, context)
        elif kind == "shuffle_into_deck":
            self._resolve_shuffle_into_deck(state, effect, context)
        elif kind == "name_a_card":
            return self._resolve_name_a_card(state, effect, context)
        elif kind == "reveal_and_route":
            return self._resolve_reveal_and_route(state, effect, context)
        elif kind == "put_into_inkwell":
            self._resolve_put_into_inkwell(state, effect, context)
        elif kind == "play_card":
            self._resolve_play_card(state, effect, context)
        elif kind == "grant_ability":
            self._resolve_grant_ability(state, effect, context)
        elif kind == "grant_abilities_while_here":
            return
        elif kind == "grant_discard_inkability":
            return
        elif kind == "create_replacement_effect":
            self._resolve_create_replacement_effect(state, effect, context)
        elif kind == "return_random_from_inkwell":
            self._resolve_return_random_from_inkwell(state, effect, context)
        else:
            raise EffectResolutionError(f"Unsupported effect kind {kind}")

        return self._mark_from_state_change(
            before,
            state,
            context,
            target_count=len(context.current_targets or ()),
        )

    def _resolve_choice(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        raw = self._source_raw(effect)
        chooser_id = self._resolve_effect_chooser(state, raw, context)

        if context.choice_index is None and not isinstance(context.choice, int) and not isinstance(effect.value, int):
            self._create_choice_pending(state, effect, context, chooser_id)
            return self._mark_result(context, performed=False)

        if not effect.effects:
            return self._mark_result(context, performed=False)

        if isinstance(context.choice_index, int):
            index = context.choice_index
        elif isinstance(context.choice, int):
            index = context.choice
        else:
            index = int(effect.value or 0)

        if index < 0 or index >= len(effect.effects):
            raise EffectResolutionError(f"Choice index {index} out of range for {len(effect.effects)} options")

        branch_context = self._ctx(
            context,
            chooser=chooser_id,
            choice_index=index,
            choice=index,
        )
        return self.resolve(state, effect.effects[index], branch_context)

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

    def _resolve_effect_chooser(
        self,
        state: GameState,
        raw: dict[str, Any],
        context: EffectResolutionContext,
    ) -> int:
        """Resolve the player who should make the current prompt choice.

        Mirrors Lorcanito selection-context.ts.
        """
        chooser = raw.get("chooser")
        chosen_by = raw.get("chosenBy") or raw.get("chosen_by")
        normalized = str(chooser or chosen_by or "").replace("_", "-").casefold()

        if normalized in {"you", "controller", "self"}:
            return context.actor

        if normalized in {"opponent", "opponents"}:
            return state.opponent(context.actor)

        if normalized == "chosen-player":
            if isinstance(context.choice, int):
                return int(context.choice)
            if context.current_targets:
                selected = context.current_targets[0]
                if selected in range(len(state.players)):
                    return int(selected)
            return context.actor

        if normalized == "card-owner":
            selected = context.current_targets or context.context_targets
            for target_id in selected:
                if target_id in state.cards:
                    return state.cards[target_id].owner
            return context.actor

        if normalized == "target":
            if isinstance(context.choice, int):
                return int(context.choice)
            selected = context.current_targets or context.context_targets
            for target_id in selected:
                if target_id in state.cards:
                    return state.cards[target_id].owner
            return context.actor

        if context.chooser is not None:
            return context.chooser
        return context.actor

    def _effect_needs_external_chooser(
        self,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> bool:
        raw = self._source_raw(effect)
        target = raw.get("target") or effect.target
        if target is None:
            return False
        chosen_by = str(raw.get("chosenBy") or raw.get("chosen_by") or "").casefold()
        chooser = str(raw.get("chooser") or "").casefold()
        if chosen_by == "opponent" and not context.current_targets:
            return True
        if chooser in {"opponent", "opponents"} and not context.current_targets:
            return True
        return False

    def _create_pending_choice_for_effect(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> None:
        raw = self._source_raw(effect)
        chooser_id = self._resolve_effect_chooser(state, raw, context)
        target = raw.get("target") or effect.target

        if target is None:
            raise EffectResolutionError("External chooser effect requires a target")

        from .pending_effects import create_pending_effect

        source_card_id = self.engine.card_def(state, context.source).id if context.source in state.cards else None
        # Keep the full Lorcanito target object in raw["target"], but do not
        # put an unhashable dict into EffectDef.target. Pending target candidate
        # resolution already reads raw["target"] first.
        pending_target = "target" if isinstance(target, dict) else effect.target

        pending_effect = EffectDef(
            kind=effect.kind,
            amount=effect.amount,
            target=pending_target,
            value=effect.value,
            keyword=effect.keyword,
            effects=effect.effects,
            condition=effect.condition,
            optional=effect.optional,
            duration=effect.duration,
            raw=effect.raw,
        )

        create_pending_effect(
            state,
            controller_id=context.actor,
            chooser_id=chooser_id,
            source_id=context.source,
            source_card_id=source_card_id,
            effects=(pending_effect,),
            origin="opponent_choice" if chooser_id != context.actor else "choice",
            raw={
                "requirement_kind": "opponent_choice" if chooser_id != context.actor else "target",
                "choice_type": "target",
                "target": target,
                "target_actor": context.actor,
                "protection_actor": chooser_id,
                "chooser_id": chooser_id,
                "controller_id": context.actor,
                "selected_targets": context.current_targets,
                "current_targets": context.current_targets,
                "context_targets": context.context_targets,
                "slotted_targets": context.slotted_targets,
                "destinations": context.destinations,
                "named_card": context.named_card,
                "last_effect_performed": context.last_effect_performed,
                "last_effect_target_count": context.last_effect_target_count,
            },
        )

    def _create_choice_pending(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
        chooser_id: int,
    ) -> None:
        from .pending_effects import create_pending_effect

        raw = self._source_raw(effect)
        options = raw.get("options") or raw.get("choices") or list(range(len(effect.effects or ())))
        source_card_id = self.engine.card_def(state, context.source).id if context.source in state.cards else None

        create_pending_effect(
            state,
            controller_id=context.actor,
            chooser_id=chooser_id,
            source_id=context.source,
            source_card_id=source_card_id,
            effects=(effect,),
            origin="choice",
            raw={
                "requirement_kind": "choice" if chooser_id == context.actor else "opponent_choice",
                "choice_type": "choice",
                "options": tuple(options),
                "target_actor": context.actor,
                "protection_actor": chooser_id,
                "chooser_id": chooser_id,
                "controller_id": context.actor,
                "current_targets": context.current_targets,
                "context_targets": context.context_targets,
                "slotted_targets": context.slotted_targets,
                "destinations": context.destinations,
                "named_card": context.named_card,
                "last_effect_performed": context.last_effect_performed,
                "last_effect_target_count": context.last_effect_target_count,
            },
        )

    def _create_optional_pending(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
        chooser_id: int,
    ) -> None:
        from .pending_effects import create_pending_effect

        source_card_id = self.engine.card_def(state, context.source).id if context.source in state.cards else None

        create_pending_effect(
            state,
            controller_id=context.actor,
            chooser_id=chooser_id,
            source_id=context.source,
            source_card_id=source_card_id,
            effects=(effect,),
            optional=True,
            origin="optional",
            raw={
                "requirement_kind": "optional" if chooser_id == context.actor else "opponent_choice",
                "choice_type": "optional",
                "target_actor": context.actor,
                "protection_actor": chooser_id,
                "chooser_id": chooser_id,
                "controller_id": context.actor,
                "current_targets": context.current_targets,
                "context_targets": context.context_targets,
                "slotted_targets": context.slotted_targets,
                "destinations": context.destinations,
                "named_card": context.named_card,
                "last_effect_performed": context.last_effect_performed,
                "last_effect_target_count": context.last_effect_target_count,
            },
        )

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
    
    def _resolve_optional(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        raw = self._source_raw(effect)
        chooser_id = self._resolve_effect_chooser(state, raw, context)

        if context.resolve_optional is None and raw.get("resolveOptional") is None:
            self._create_optional_pending(state, effect, context, chooser_id)
            return self._mark_result(context, performed=False)

        accepted = (
            bool(context.resolve_optional)
            if context.resolve_optional is not None
            else bool(raw.get("resolveOptional"))
        )
        if not accepted:
            return self._mark_result(context, performed=False)

        child_effects = effect.effects
        if not child_effects:
            child = raw.get("effect")
            if isinstance(child, dict):
                from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
                mapped = map_raw_effect(child)
                if mapped is not None:
                    child_effects = (EffectDef(
                        kind=mapped.kind.replace("-", "_"),
                        amount=mapped.amount,
                        target=mapped.target,
                        value=mapped.value,
                        keyword=mapped.keyword,
                        effects=tuple(
                            EffectDef(
                                kind=nested.kind.replace("-", "_"),
                                amount=nested.amount,
                                target=nested.target,
                                raw=nested.raw,
                            )
                            for nested in mapped.effects
                        ),
                        condition=mapped.condition,
                        optional=mapped.optional,
                        duration=mapped.duration,
                        raw=mapped.raw,
                    ),)

        optional_context = self._ctx(
            context,
            chooser=chooser_id,
            resolve_optional=True,
        )
        return self.resolve_many(state, tuple(child_effects), optional_context)
    
    def _resolve_conditional(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        condition = effect.condition or {}
        kind = str(condition.get("type") or condition.get("kind") or "always")

        if kind == "if-you-do":
            condition_met = context.last_effect_performed is True
        else:
            condition_met = self._condition_matches(state, effect, context)

        raw = self._source_raw(effect)
        if condition_met:
            child_effects = effect.effects
            if not child_effects:
                branch = raw.get("then") or raw.get("ifTrue") or raw.get("effect")
                if isinstance(branch, dict):
                    from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
                    mapped = map_raw_effect(branch)
                    if mapped is not None:
                        child_effects = (EffectDef(
                            kind=mapped.kind.replace("-", "_"),
                            amount=mapped.amount,
                            target=mapped.target,
                            value=mapped.value,
                            keyword=mapped.keyword,
                            effects=tuple(
                                EffectDef(
                                    kind=nested.kind.replace("-", "_"),
                                    amount=nested.amount,
                                    target=nested.target,
                                    raw=nested.raw,
                                )
                                for nested in mapped.effects
                            ),
                            condition=mapped.condition,
                            optional=mapped.optional,
                            duration=mapped.duration,
                            raw=mapped.raw,
                        ),)
            return self.resolve_many(state, tuple(child_effects), context)

        else_branch = raw.get("else") or raw.get("ifFalse")
        if isinstance(else_branch, dict):
            from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
            mapped = map_raw_effect(else_branch)
            if mapped is not None:
                return self.resolve(state, EffectDef(
                    kind=mapped.kind.replace("-", "_"),
                    amount=mapped.amount,
                    target=mapped.target,
                    value=mapped.value,
                    keyword=mapped.keyword,
                    raw=mapped.raw,
                ), context)

        return self._mark_result(context, performed=False)
    
    def _resolve_select_target(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Resolve a Lorcanito select-target effect.

        select-target does not mutate the board, but it does establish
        currentTargets and lastEffectPerformed for later sequence steps.
        """
        targets = tuple(self._target_cards(state, effect, context, require_target=False))
        if not targets and context.current_targets:
            targets = context.current_targets
        return self._with_current_targets(
            context,
            tuple(int(target_id) for target_id in targets),
            performed=bool(targets),
        )

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

        players = self._target_players(state, effect, context)

        # Determine if explicit choice is required
        # Rule 1: If effect.raw["chosen"] is true, create pending discard_choice
        # Rule 2: If effect.raw["chosen_by"] or effect.raw["chosenBy"] is "opponent", chooser is opponent
        # Rule 3: If target player is not the resolving actor and explicit choice is required, create pending
        # Rule 4: If no explicit choice is required, preserve current deterministic discard behavior

        requires_explicit_choice = is_chosen or chosen_by is not None

        if requires_explicit_choice:
            if len(players) != 1:
                raise EffectResolutionError("Explicit discard choice requires one target player")
            player = players[0]
            amount = self._discard_amount_for_player(state, effect, context, player)
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
        for player in players:
            amount = self._discard_amount_for_player(state, effect, context, player)
            for _ in range(min(amount, len(state.players[player].hand))):
                self.engine._discard_eventful(
                    state,
                    state.players[player].hand[0],
                    actor=player,
                    source_id=context.source,
                    reason="effect",
                )

    def _discard_amount_for_player(self, state: GameState, effect: EffectDef, context: EffectResolutionContext, player: int) -> int:
        raw_source = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if isinstance(raw_source, dict) and raw_source.get("amount") == "all":
            return len(state.players[player].hand)
        return self._amount(state, effect, context)

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
        if effect.target == "card_owner":
            target_ids = context.current_targets or ((context.target,) if context.target is not None else ())
            if not target_ids:
                raise EffectResolutionError("CARD_OWNER target requires selected card context")
            return state.cards[int(target_ids[0])].owner
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

    def _target_players(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> tuple[int, ...]:
        descriptor = self._normalize_player_target(effect.target)
        if descriptor is not None and descriptor.selector == "each_player":
            from .targeting import resolve_candidate_player_ids
            return tuple(resolve_candidate_player_ids(state, descriptor, self._target_query_context(context)))
        return (self._target_player(state, effect, context),)

    def _normalize_effect_target(self, raw_target: Any):
        from .targeting import normalize_target_descriptor

        raw = getattr(raw_target, "raw", None)
        if isinstance(raw, dict):
            descriptor = normalize_target_descriptor(raw)
            if descriptor is not None:
                return descriptor

        if isinstance(raw_target, dict):
            descriptor = normalize_target_descriptor(raw_target)
            if descriptor is not None:
                return descriptor

        alias = getattr(raw_target, "alias", None)
        if isinstance(alias, str) and alias:
            descriptor = normalize_target_descriptor(alias)
            if descriptor is not None:
                return descriptor

        selector = getattr(raw_target, "selector", None)
        if isinstance(selector, str) and selector:
            descriptor = normalize_target_descriptor(selector)
            if descriptor is not None:
                return descriptor

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
            chooser=context.chooser,
            protection_actor=context.chooser,
        )

    def _uses_selected_card_context(self, selector: str) -> bool:
        from .targeting import requires_explicit_target_selection

        return (
            selector in {
                "target",
                "current_targets",
                "context_targets",
                "previous_target",
                "selected_first",
                "selected_all",
            }
            or requires_explicit_target_selection(selector)
        )

    def _selected_card_targets_from_context(self, context: EffectResolutionContext) -> tuple[int, ...]:
        if context.current_targets:
            return context.current_targets
        if context.context_targets:
            return context.context_targets
        if context.slotted_targets:
            flat = self._flatten_slotted_target_ids(context.slotted_targets)
            if flat:
                return flat
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

    def _amount(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> int:
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
                if raw_amount == "all":
                    player = self._target_player(state, effect, context)
                    return len(state.players[player].hand)
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
            elif amount_type == "cards-under-self":
                if context.source is None or context.source not in state.cards:
                    raise EffectResolutionError("cards-under-self amount requires source")
                return len(state.cards[context.source].cards_under)
            elif amount_type == "lore-value-of":
                target_ids = context.current_targets or ((context.target,) if context.target is not None else ())
                if not target_ids:
                    raise EffectResolutionError("lore-value-of amount requires selected target")
                return self.engine.effective_lore(state, int(target_ids[0]))
            elif amount_type == "filtered-count":
                return self._filtered_count_amount(state, raw_amount, context)
            elif amount_type == "characters-in-play":
                controller = context.actor if raw_amount.get("controller") in {None, "you"} else state.opponent(context.actor)
                return sum(1 for cid in state.players[controller].play if self.engine.card_def(state, cid).card_type == "character")
            elif amount_type == "difference":
                left = self._amount_operand_value(state, raw_amount.get("left"), context)
                right = self._amount_operand_value(state, raw_amount.get("right"), context)
                value = right - left if raw_amount.get("invert") else left - right
                return max(0, int(value))
            elif amount_type == "trigger-amount":
                return int(state.turn_metadata.get(f"trigger_amount:{context.source}", 0) or 0)

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

    def _amount_operand_value(self, state: GameState, operand: Any, context: EffectResolutionContext) -> int:
        if not isinstance(operand, dict):
            return 0
        controller = context.actor
        if operand.get("controller") == "opponent":
            controller = state.opponent(context.actor)
        if operand.get("type") == "cards-in-hand":
            return len(state.players[controller].hand)
        return 0

    def _filtered_count_amount(self, state: GameState, raw_amount: dict[str, Any], context: EffectResolutionContext) -> int:
        owner = raw_amount.get("owner")
        controller_filter = None
        if owner == "you":
            controller_filter = context.actor
        elif owner == "opponent":
            controller_filter = state.opponent(context.actor)
        zones = tuple(raw_amount.get("zones") or ("play",))
        card_type = raw_amount.get("cardType")
        exclude_self = bool(raw_amount.get("excludeSelf"))
        filters = raw_amount.get("filters") or ()
        if isinstance(filters, dict):
            filters = (filters,)
        count = 0
        for cid, inst in state.cards.items():
            if inst.zone not in zones:
                continue
            if controller_filter is not None and inst.controller != controller_filter:
                continue
            if exclude_self and cid == context.source:
                continue
            cdef = self.engine.card_def(state, cid)
            if card_type and cdef.card_type != card_type:
                continue
            if not self._amount_filters_match(cdef, filters):
                continue
            count += 1
        return count * int(raw_amount.get("multiplier") or 1)

    def _amount_filters_match(self, cdef: Any, filters: tuple[Any, ...]) -> bool:
        for filter_def in filters:
            if not isinstance(filter_def, dict):
                return False
            if filter_def.get("type") in {"has-name", "name"} and filter_def.get("name") not in {cdef.full_name, cdef.name, cdef.simple_name}:
                return False
        return True

    def _keyword(self, effect: EffectDef) -> str:
        if not effect.keyword:
            raise EffectResolutionError("keyword_grant requires keyword")
        return effect.keyword.strip().upper().replace(" ", "_")

    def _resolve_shuffle_into_deck(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        for target in self._target_cards(state, effect, context):
            owner = state.cards[target].owner
            self.engine._move_card_eventful(
                state,
                target,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=owner,
                queue_triggers=False,
            )
            self.engine._shuffle_deck(state, owner, salt=f"shuffle_into_deck:{context.source}:{target}")

    def _resolve_play_card(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if raw.get("from") != "discard" or raw.get("cost") != "free" or raw.get("cardType") != "character":
            raise EffectResolutionError("Unsupported play-card shape")
        target_ids = context.current_targets or ((context.target,) if context.target is not None else ())
        if len(target_ids) != 1:
            raise EffectResolutionError("play-card requires exactly one selected card")
        target = int(target_ids[0])
        inst = state.cards[target]
        if inst.owner != context.actor or inst.zone != ZONE_DISCARD:
            raise EffectResolutionError("play-card target must be your character in discard")
        card = self.engine.card_def(state, target)
        if card.card_type != "character":
            raise EffectResolutionError("play-card target must be a character")
        self.engine._move_card_eventful(state, target, ZONE_PLAY, actor=context.actor, controller=context.actor)
        self.engine._ready_eventful(state, target, actor=context.actor, source_id=context.source, emit_event=False)
        inst.damage = 0
        inst.drying = True
        inst.just_played = True
        inst.played_cost_type = "free"
        self.engine._register_lifecycle_effects_for_public_permanent(state, target)
        self.engine.emit_event(
            state,
            "CARD_PLAYED",
            actor=context.actor,
            source=target,
            payload={
                "player_id": context.actor,
                "subject_card_id": target,
                "card_type": card.card_type,
                "played_from": ZONE_DISCARD,
                "played_to": ZONE_PLAY,
                "used_shift": False,
                "sung": False,
                "free": True,
                "source_card_id": context.source,
            },
        )

    def _resolve_move_damage(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        from_ref = raw.get("from")
        to_target = raw.get("to")
        raw_amount = raw.get("amount")
        if not (isinstance(from_ref, dict) and from_ref.get("ref") == "self"):
            raise EffectResolutionError("Unsupported move-damage source")
        if not (isinstance(raw_amount, dict) and raw_amount.get("type") == "up-to"):
            raise EffectResolutionError("Unsupported move-damage amount")
        source = context.source
        if source is None:
            raise EffectResolutionError("move-damage requires a source")
        target_ids = context.current_targets or ((context.target,) if context.target is not None else ())
        if len(target_ids) != 1:
            raise EffectResolutionError("move-damage requires exactly one target")
        amount_choice = int(context.choice or 0)
        maximum = min(int(raw_amount.get("value") or 0), state.cards[source].damage)
        if amount_choice < 0 or amount_choice > maximum:
            raise EffectResolutionError("move-damage amount outside legal range")
        if amount_choice == 0:
            return
        self.engine._remove_damage_eventful(state, source, amount_choice, actor=context.actor, source_id=source)
        moved_effect = EffectDef("deal_damage", amount_choice, to_target, raw={"moved_damage": True})
        for target in self._target_cards(state, moved_effect, context):
            self.engine._deal_damage_eventful(
                state,
                target_id=target,
                source_id=source,
                amount=amount_choice,
                actor=context.actor,
                is_challenge=False,
                apply_resist=False,
            )

    def _resolve_move_to_location(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = self._source_raw(effect)
        slotted = context.slotted_targets if isinstance(context.slotted_targets, dict) else None

        character_ids: tuple[int, ...] = ()
        location_ids: tuple[int, ...] = ()

        if slotted and slotted.get("kind") == "move-to-location":
            character_ids = tuple(int(cid) for cid in slotted.get("subject", ()) or ())
            location_ids = tuple(int(cid) for cid in slotted.get("location", ()) or ())
        else:
            character_target = raw.get("character") or raw.get("subject")
            location_target = raw.get("location")

            if character_target is not None:
                character_effect = EffectDef("select_target", target=character_target, raw={"raw": {"target": character_target}})
                character_ids = tuple(self._target_cards(state, character_effect, context, require_target=False))

            if location_target is not None:
                location_effect = EffectDef("select_target", target=location_target, raw={"raw": {"target": location_target}})
                location_ids = tuple(self._target_cards(state, location_effect, context, require_target=False))

        if raw.get("includeSelf") is True and context.source is not None:
            source_card = self.engine.card_def(state, context.source)
            if source_card.card_type == "character":
                character_ids = tuple(dict.fromkeys((*character_ids, context.source)))

        if len(location_ids) != 1:
            raise EffectResolutionError("move-to-location requires exactly one location target")

        location_id = int(location_ids[0])
        if location_id not in state.cards or self.engine.card_def(state, location_id).card_type != "location":
            raise EffectResolutionError("move-to-location location target must be a location")

        moved_any = False
        for character_id in character_ids:
            if character_id not in state.cards:
                continue
            if self.engine.card_def(state, character_id).card_type != "character":
                continue
            if state.cards[character_id].zone != ZONE_PLAY:
                continue
            previous_location = state.cards[character_id].location_instance_id
            state.cards[character_id].location_instance_id = location_id
            moved_any = True
            self.engine.emit_event(
                state,
                EVENT_MOVED_TO_LOCATION,
                actor=context.actor,
                source=character_id,
                target=location_id,
                payload={
                    "player_id": context.actor,
                    "subject_card_id": character_id,
                    "location_id": location_id,
                    "from_zone": f"location:{previous_location}" if previous_location is not None else ZONE_PLAY,
                    "to_zone": f"location:{location_id}",
                    "source_card_id": context.source,
                    "trigger_source_card_id": context.source,
                },
            )

        if not moved_any and not raw.get("includeSelf"):
            return

    def _resolve_return_from_discard(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if raw.get("target") not in {"CONTROLLER", "controller"}:
            raise EffectResolutionError("Unsupported return-from-discard target")
        card_type = raw.get("cardType")
        target_ids = tuple(context.current_targets or ((context.target,) if context.target is not None else ()))
        if len(target_ids) != 1:
            raise EffectResolutionError("return-from-discard requires exactly one selected card")
        target = int(target_ids[0])
        if state.cards[target].zone != ZONE_DISCARD or state.cards[target].owner != context.actor:
            raise EffectResolutionError("return-from-discard target must be in your discard")
        if card_type and self.engine.card_def(state, target).card_type != card_type:
            raise EffectResolutionError("return-from-discard target card type mismatch")
        self.engine._move_card_eventful(state, target, ZONE_HAND, actor=context.actor, source_id=context.source)

    def _resolve_restriction(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if raw.get("restriction") != "cant-quest" or raw.get("duration") not in {None, "this-turn", "this_turn"}:
            raise EffectResolutionError("Unsupported restriction effect")
        blocked = set(state.turn_metadata.get("cant_quest_until_turn_end", ()) or ())
        for target in self._target_cards(state, effect, context):
            blocked.add(target)
        state.turn_metadata["cant_quest_until_turn_end"] = tuple(sorted(blocked))

    def _resolve_pay_cost(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        cost = raw.get("cost")
        child_raw = raw.get("effect")
        if not (isinstance(cost, dict) and set(cost) == {"ink"} and isinstance(child_raw, dict)):
            raise EffectResolutionError("Unsupported pay-cost shape")
        ink = int(cost.get("ink") or 0)
        if ink < 0 or self.engine.available_ink(state, context.actor) < ink:
            raise EffectResolutionError("Cannot pay pay-cost ink")
        from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect

        child = map_raw_effect(child_raw)
        if child is None:
            raise EffectResolutionError("Unsupported pay-cost child effect")
        self.engine._pay_ink(state, context.actor, ink)
        self.resolve(state, EffectDef(
            kind=child.kind.replace("-", "_"),
            amount=child.amount or 0,
            target=child.target,
            effects=tuple(EffectDef(
                kind=nested.kind.replace("-", "_"),
                amount=nested.amount or 0,
                target=nested.target,
                raw=nested.raw,
            ) for nested in child.effects),
            raw=child.raw,
        ), context)

    def _resolve_grant_ability(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        ability_raw = raw.get("ability")
        if ability_raw == "gain-lore-when-challenging":
            for target in self._target_cards(state, effect, context):
                state.cards[target].temporary_granted_abilities.append({
                    "type": "gain-lore-when-challenging",
                    "amount": 1,
                    "duration": raw.get("duration") or "this-turn",
                })
            return
        if not isinstance(ability_raw, dict):
            raise EffectResolutionError("grant-ability requires raw ability")
        from lorcana_bot.importers.lorcanito_source_mapper import map_raw_ability

        granted = map_raw_ability(ability_raw)
        for target in self._target_cards(state, effect, context):
            state.cards[target].temporary_granted_abilities.append(granted)

    def _resolve_create_replacement_effect(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        replacement = raw.get("replacement")
        if not isinstance(replacement, dict):
            raise EffectResolutionError("create-replacement-effect requires replacement")
        if replacement.get("type") != "prevent-damage" or replacement.get("targetRef") != "source":
            raise EffectResolutionError("Unsupported create-replacement-effect shape")
        from lorcana_bot.replacement_effects import ReplacementEffectEntry, ReplacementEffectType, register_replacement_effect

        register_replacement_effect(
            state,
            ReplacementEffectEntry(
                source_id=int(context.source) if context.source is not None else -1,
                effect_type=ReplacementEffectType.PREVENT_DAMAGE,
                target_mode="self",
                amount=999,
                replacement_effect="prevent_damage",
                usage_key=f"trigger_prevent_damage:{context.pending_trigger_id or context.source}",
                event_kinds=tuple(replacement.get("eventKinds", ()) or ()),
                consume_on_apply=bool(replacement.get("consumeOnApply")),
                duration=str(raw.get("duration") or "this-turn"),
            ),
        )

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

        amount = self._amount(state, effect, context)
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
        amount = self._amount(state, effect, context)
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
        amount = self._amount(state, effect, context)
        if amount <= 0:
            amount = 1

        revealed_for_effect: list[int] = []
        for player in self._target_players(state, effect, context):
            player_deck = state.players[player].deck

            if not player_deck:
                continue

            # Reveal top card(s)
            revealed_cards = []
            for i in range(min(amount, len(player_deck))):
                cid = player_deck[i]
                inst = state.cards[cid]

                # Mark as revealed (public info)
                inst.revealed = True
                revealed_cards.append(cid)
                revealed_for_effect.append(cid)

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
        state.turn_metadata[f"revealed_for_effect:{context.source}"] = tuple(revealed_for_effect)

    def _resolve_count(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        if raw.get("what") != "distinct-revealed-ink-types":
            raise EffectResolutionError("Unsupported count effect")
        revealed = tuple(state.turn_metadata.get(f"revealed_for_effect:{context.source}", ()) or ())
        inks = {self.engine.card_def(state, cid).ink for cid in revealed if cid in state.cards}
        state.turn_metadata[f"trigger_amount:{context.source}"] = len(inks)

    def _resolve_return_random_from_inkwell(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
        leave = int(raw.get("leave") or 0)
        import random

        for player in self._target_players(state, effect, context):
            inkwell = list(state.players[player].inkwell)
            if len(inkwell) <= leave:
                continue
            rng = random.Random(f"{state.seed}:return_random_from_inkwell:{context.source}:{player}:{state.turn_number}")
            rng.shuffle(inkwell)
            for cid in inkwell[:len(inkwell) - leave]:
                self.engine._move_card_eventful(state, cid, ZONE_HAND, actor=player, source_id=context.source)

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

    def _resolve_put_card_on_top(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Move selected/resolved cards to the top of their owners' decks.

        Lorcanito uses selected target order when the player supplied ordering.
        The supplied order should become the final top order.
        """
        targets = tuple(context.current_targets or ())
        if not targets:
            targets = tuple(self._target_cards(state, effect, context, require_target=False))
        if not targets and context.choice is not None:
            targets = (int(context.choice),)

        # To make final deck top order match selected order, move in reverse
        # because each move inserts at index 0.
        for card_id in reversed(tuple(int(cid) for cid in targets)):
            if card_id not in state.cards:
                continue
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
                index=0,
            )

        return self._mark_result(
            context,
            performed=bool(targets),
            target_count=len(targets),
        )

    def _resolve_put_card_on_bottom(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Move selected/resolved cards to the bottom of their owners' decks.

        For ordering: player-choice, current_targets carries the selected order.
        """
        targets = tuple(context.current_targets or ())
        if not targets:
            targets = tuple(self._target_cards(state, effect, context, require_target=False))
        if not targets and context.choice is not None:
            targets = (int(context.choice),)

        # Keep supplied order for bottom movement. _move_card_eventful without
        # index appends to deck bottom in current engine movement semantics.
        for card_id in tuple(int(cid) for cid in targets):
            if card_id not in state.cards:
                continue
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
            )

        return self._mark_result(
            context,
            performed=bool(targets),
            target_count=len(targets),
        )

    def _draw_until_hand_size(self, effect: EffectDef) -> int:
        raw = effect.raw or {}
        source_raw = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
        for key in ("size", "target_size", "hand_size", "value"):
            if key in source_raw:
                return int(source_raw[key])
        if effect.value is not None:
            return int(effect.value)
        if effect.amount:
            return int(effect.amount)
        raise EffectResolutionError("draw_until_hand_size requires target hand size")

    def _resolve_put_into_inkwell(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        source_raw = self._source_raw(effect)
        exerted = bool(source_raw.get("exerted", True))
        source_shape = source_raw.get("source")
        if source_shape == "hand" or isinstance(source_shape, dict):
            targets = tuple(context.current_targets or ((context.target,) if context.target is not None else ()))
            if not targets:
                raise EffectResolutionError("put-into-inkwell requires selected source card")
        else:
            targets = tuple(self._target_cards(state, effect, context))
        for target in targets:
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

    def _resolve_name_a_card(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Handle name_a_card effect.

        If a named card is already present in context, return a performed
        context. Otherwise create pending input and suspend without performing.
        """
        named_card_id = context.named_card or (str(context.choice) if context.choice is not None else None)
        if named_card_id:
            return self._ctx(
                context,
                named_card=named_card_id,
                last_effect_performed=True,
                last_effect_target_count=0,
            )

        from .pending_effects import create_named_card_pending_effect

        raw = self._source_raw(effect)
        chooser_id = self._resolve_effect_chooser(state, raw, context)
        raw_valid_ids = raw.get("valid_card_def_ids") or raw.get("validCardDefIds") or ()
        valid_card_def_ids = tuple(str(card_id) for card_id in raw_valid_ids)

        pe = create_named_card_pending_effect(
            state=state,
            controller_id=context.actor,
            chooser_id=chooser_id,
            source_id=context.source,
            source_card_id=self.engine.card_def(state, context.source).id if context.source else None,
            valid_card_def_ids=valid_card_def_ids,
            origin="name_a_card",
        )
        pe.raw["target_actor"] = context.actor
        pe.raw["protection_actor"] = chooser_id
        pe.raw["context_targets"] = context.context_targets
        pe.raw["current_targets"] = context.current_targets
        pe.raw["last_effect_performed"] = context.last_effect_performed
        pe.raw["last_effect_target_count"] = context.last_effect_target_count

        return self._mark_result(context, performed=False)

    def _resolve_reveal_and_route(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
        """Reveal the top card and route it according to Lorcanito routes/fallback.

        Supports the currently reported named-card patterns:
        - name-a-card
        - reveal top card
        - if revealed matches named, move to hand/inkwell and run side effects
        - otherwise fallback to top/bottom
        """
        source_raw = self._source_raw(effect)
        player = self._target_player(state, effect, context)
        player_deck = state.players[player].deck

        if not player_deck:
            return self._mark_result(context, performed=False)

        cid = player_deck[0]
        inst = state.cards[cid]
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

        routes = source_raw.get("routes") if isinstance(source_raw.get("routes"), list) else ()
        matched_route: dict[str, Any] | None = None

        for route in routes:
            if not isinstance(route, dict):
                continue
            condition = route.get("condition")
            if self._reveal_route_condition_matches(state, cid, condition, context):
                matched_route = route
                break

        if matched_route is not None:
            destination = matched_route.get("destination") or {}
            self._move_revealed_card_to_destination(state, cid, destination, player, context)
            context = self._mark_result(context, performed=True, target_count=1)

            side_effects = matched_route.get("sideEffects") or matched_route.get("side_effects") or ()
            if isinstance(side_effects, dict):
                side_effects = (side_effects,)
            for raw_side_effect in side_effects:
                if isinstance(raw_side_effect, dict):
                    from lorcana_bot.importers.lorcanito_source_mapper import map_raw_effect
                    mapped = map_raw_effect(raw_side_effect)
                    if mapped is not None:
                        context = self.resolve(state, EffectDef(
                            kind=mapped.kind.replace("-", "_"),
                            amount=mapped.amount,
                            target=mapped.target,
                            value=mapped.value,
                            keyword=mapped.keyword,
                            raw=mapped.raw,
                        ), context)
            return context

        fallback = source_raw.get("fallback")
        if isinstance(fallback, dict):
            self._move_revealed_card_to_destination(state, cid, fallback, player, context)
        else:
            destination = self._route_destination(source_raw, effect.value)
            self._move_revealed_card_to_destination(state, cid, {"zone": destination}, player, context)

        return self._mark_result(context, performed=False, target_count=1)

    def _reveal_route_condition_matches(
        self,
        state: GameState,
        card_id: int,
        condition: Any,
        context: EffectResolutionContext,
    ) -> bool:
        if not isinstance(condition, dict):
            return True
        kind = str(condition.get("type") or condition.get("kind") or "")
        if kind == "revealed-matches-named":
            if not context.named_card:
                return False
            cdef = self.engine.card_def(state, card_id)
            names = {
                cdef.id,
                cdef.full_name,
                getattr(cdef, "name", ""),
                getattr(cdef, "simple_name", ""),
            }
            return context.named_card in names
        return False

    def _move_revealed_card_to_destination(
        self,
        state: GameState,
        card_id: int,
        destination: dict[str, Any],
        player: int,
        context: EffectResolutionContext,
    ) -> None:
        zone = self._route_destination(destination, destination.get("zone"))
        if zone == "hand":
            self.engine._move_card_eventful(state, card_id, ZONE_HAND, actor=player, source_id=context.source)
        elif zone == "discard":
            self.engine._move_card_eventful(state, card_id, ZONE_DISCARD, actor=player, source_id=context.source)
        elif zone == "deck-top":
            self.engine._move_card_eventful(state, card_id, ZONE_DECK, actor=player, source_id=context.source, index=0)
        elif zone == "deck-bottom":
            self.engine._move_card_eventful(state, card_id, ZONE_DECK, actor=player, source_id=context.source)
        elif zone == "inkwell":
            self.engine._put_into_inkwell_eventful(
                state,
                card_id,
                actor=player,
                source_id=context.source,
                queue_triggers=False,
                exerted=bool(destination.get("exerted", True)),
            )
        elif zone == "play":
            cdef = self.engine.card_def(state, card_id)
            if cdef.card_type == "character":
                self.engine._move_card_eventful(state, card_id, ZONE_PLAY, actor=player, source_id=context.source)
        else:
            raise EffectResolutionError(f"Unsupported reveal route destination {zone!r}")

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

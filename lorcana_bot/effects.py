from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import EffectDef
from .constants import CARD_CHARACTER, ZONE_DISCARD, ZONE_HAND
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
            state.players[self._target_player(state, effect, context)].lore += self._amount(effect)
        elif kind == "lose_lore":
            player = self._target_player(state, effect, context)
            state.players[player].lore = max(0, state.players[player].lore - self._amount(effect))
        elif kind == "deal_damage":
            for target in self._target_cards(state, effect, context):
                target_def = self.engine.card_def(state, target)
                state.cards[target].damage += self.engine.damage_after_resist(target_def, self._amount(effect))
        elif kind == "remove_damage":
            for target in self._target_cards(state, effect, context):
                state.cards[target].damage = max(0, state.cards[target].damage - self._amount(effect))
        elif kind == "banish":
            for target in self._target_cards(state, effect, context):
                state.move_card(target, ZONE_DISCARD)
        elif kind == "discard":
            self._discard(state, effect, context)
        elif kind == "return_to_hand":
            for target in self._target_cards(state, effect, context):
                state.move_card(target, ZONE_HAND)
        elif kind == "ready":
            for target in self._target_cards(state, effect, context):
                state.cards[target].exerted = False
        elif kind == "exert":
            for target in self._target_cards(state, effect, context):
                state.cards[target].exerted = True
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
                state.move_card(target, ZONE_DISCARD)
            return

        player = self._target_player(state, effect, context)
        for _ in range(min(self._amount(effect), len(state.players[player].hand))):
            state.move_card(state.players[player].hand[0], ZONE_DISCARD)

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
        if target in {None, "chosen_character", "chosen_card", "target", "opposing_character"}:
            if context.target is None:
                if require_target:
                    raise EffectResolutionError(f"Effect {effect.kind} requires a target")
                return []
            return [context.target]
        if target == "self":
            if context.source is None:
                raise EffectResolutionError(f"Effect {effect.kind} requires a source")
            return [context.source]
        if target in {"your_characters", "opposing_characters", "all_characters"}:
            return self._collection(state, target, context)
        raise EffectResolutionError(f"Unsupported card target {target!r} for {effect.kind}")

    def _collection(self, state: GameState, collection: str, context: EffectResolutionContext) -> list[int]:
        players: tuple[int, ...]
        if collection in {"your_characters", "friendly_characters"}:
            players = (context.actor,)
        elif collection == "opposing_characters":
            players = (state.opponent(context.actor),)
        elif collection == "all_characters":
            players = (0, 1)
        else:
            raise EffectResolutionError(f"Unsupported for_each collection {collection!r}")
        result: list[int] = []
        for player in players:
            for cid in state.players[player].play:
                if self.engine.card_def(state, cid).card_type == CARD_CHARACTER:
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

# Phase Completion Guide — Routing / Choice / Slot / Sequence Engine Parity

This guide replaces the earlier phase-completion guide with a more exact implementation plan.

It is written against the current `main` state after the Multifix 21–23 agent implementation.

The goal is **not** another small patch. The goal is to finish the remaining GameEngine routing layer so LorcanaChamp behaves like Lorcanito for:

```text
selected targets
slotted targets
opponent / chooser-owned choices
optional and choice continuation
sequence currentTargets/contextTargets
previous-target / selected-all routing
destination/order preservation
lastEffectPerformed / if-you-do
name-a-card + reveal-and-route continuation
truthful runtime executability reporting
```

This phase should be implemented as one end-to-end engine-routing phase. The gates below are only validation checkpoints, not scope narrowing.

---

# 0. Current baseline and why this guide exists

Current post-agent report baseline:

```text
cards_loaded: 2754
ability_records_loaded: 3445
errors: []

execution_status_counts:
  executable: 11139
  mapped_not_executable: 516
  unsupported_choice: 18
  unsupported_condition: 290
  unsupported_cost: 52
  unsupported_engine_mechanic: 210
  unsupported_targeting: 354
  unsupported_trigger: 1

unsupported_by_reason:
  mapped_not_executable: 516
  unsupported_choice: 18
  unsupported_condition: 224
  unsupported_cost: 24
  unsupported_engine_mechanic: 210
  unsupported_targeting: 253
```

Important distinction:

```text
unsupported_targeting by-reason: 253
unsupported_targeting detailed: 354
```

The current implementation made real progress, but the remaining phase is incomplete because:

```text
1. opponent-choice is over-classified as supported.
2. chooser actor and target-semantics actor are conflated.
3. slotted target selections do not consistently emit BE_CHOSEN.
4. move-to-location emits a non-canonical event name.
5. sequence resolution does not carry currentTargets/contextTargets like Lorcanito.
6. if-you-do cannot work correctly without lastEffectPerformed propagation.
7. name-a-card and reveal-and-route still create input but do not continue a sequence correctly.
8. runtime executability can claim support before the runtime path truly exists.
```

---

# 1. Lorcanito source research summary

Use these Lorcanito source files as the parity source for this phase:

```text
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/types.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/conditional-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/select-target-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/move-to-location-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-on-top-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-on-bottom-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/reveal-and-route-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/player-target-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/event-snapshot-utils.ts
```

## 1.1 Lorcanito `ActionResolutionInput`

Lorcanito `types.ts` carries this full resolution input:

```ts
type ActionResolutionInput = {
  targets?: TargetSelectionInput;
  slottedTargets?: SlottedTargetInput;
  currentTargets?: TargetSelectionInput;
  contextTargets?: TargetSelectionInput;
  targetSelectionResolved?: boolean;
  amount?: Amount;
  namedCard?: string;
  resolveOptional?: boolean;
  enterPlayExerted?: boolean;
  choiceIndex?: number;
  destinations?: { zone: string; cards: CardInstanceId | CardInstanceId[] }[];
  eventSnapshot?: DynamicAmountEventSnapshot;
  triggerContext?: ReplacementTriggerContext;
  chooserPlayerId?: PlayerId;
};
```

LorcanaChamp equivalent must carry these same concepts:

```text
targets/current_targets
context_targets
slotted_targets
destinations
named_card
choice / choice_index
resolve_optional / optional_choices
chooser
last_effect_performed
last_effect_target_count
```

## 1.2 Lorcanito selection state

Lorcanito `selection-state.ts` has these key semantics:

```text
getCurrentSelectionTargets() = currentTargets ?? targets
getContextSelectionTargets() = contextTargets
getCombinedSelectionTargets() = contextTargets + currentTargets
getEffectTargetSelectionInput(target) uses:
  - context for pure refs like { ref: "previous-target" }
  - combined for selected-all / CARD_OWNER / chosen-for-effect
  - current for selector: "chosen"
promoteCurrentSelectionTargetsToContext():
  contextTargets = contextTargets + currentTargets
  currentTargets = undefined
  targets = undefined
```

LorcanaChamp currently has `current_targets` and `context_targets`, but the resolver still resolves sequence effects in a plain loop without returning or promoting updated context.

## 1.3 Lorcanito chooser resolution

Lorcanito `selection-context.ts` separates chooser from controller.

Important behavior:

```text
chosenBy: "you"       -> controller
chosenBy: "opponent"  -> opponent of controller
chosenBy: "TARGET"    -> selected player or selected card owner
chooser: "CHOSEN_PLAYER" -> selected player
chooser: "CARD_OWNER"    -> selected card owner
chooser: "OPPONENT"      -> opponent of controller
outer optional chooser is inherited by inner target prompt unless overridden
```

LorcanaChamp must not treat `chooser` and `actor` as the same concept.

Required split:

```text
context.actor = original effect controller / semantic owner of the effect
context.chooser = current player making a decision, when different
TargetQueryContext.actor = semantic actor for owner/controller filters
TargetQueryContext.protection_actor = player physically choosing the target for Ward/protection
```

## 1.4 Lorcanito pending effects

Lorcanito `pending-action-effects.ts` preserves:

```text
cardPlayed
effect
continuation
resolutionInput
selectionContext
chooserId
controllerId
```

LorcanaChamp pending effects must preserve enough equivalent state to resume the original sequence after input:

```text
controller_id
chooser_id
source_id
source_card_id
effects
current effect
origin
origin_id
raw["continuation_effects"]
raw["resolution_input"]
raw["current_targets"]
raw["context_targets"]
raw["slotted_targets"]
raw["destinations"]
raw["named_card"]
raw["last_effect_performed"]
```

## 1.5 Lorcanito lastEffectPerformed

Lorcanito uses `event-snapshot-utils.ts`:

```ts
didLastEffectPerform(eventSnapshot)
markLastEffectPerformed(eventSnapshot, performed)
resetLastEffectPerformed(eventSnapshot)
```

This powers `if-you-do`.

LorcanaChamp must carry this as immutable `EffectResolutionContext.last_effect_performed`.

## 1.6 Lorcanito select-target

Lorcanito `select-target-effect.ts` does not mutate board state, but it still marks whether selection happened:

```text
selectedCards.length > 0 || selectedPlayers.length > 0
```

LorcanaChamp must treat successful selection as `last_effect_performed=True`.

## 1.7 Lorcanito put-on-top / put-on-bottom

Lorcanito uses selected target order for `ordering: "player-choice"`:

```text
put-on-top: selected order becomes final top order
put-on-bottom: selected order is preserved by owner
```

LorcanaChamp already partially implements this. This guide keeps it but adds `last_effect_performed` and target count tracking.

---

# 2. Current LorcanaChamp files that must be updated

This phase edits:

```text
lorcana_bot/targeting.py
lorcana_bot/effect_types.py
lorcana_bot/effects.py
lorcana_bot/abilities.py
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
lorcana_bot/card_logic/resolution_requirements.py
lorcana_bot/decks/runtime_executability.py
tests/test_targeting.py
tests/test_effects.py
tests/test_pending_effects.py
tests/test_activated_abilities_execution.py
tests/test_bag_resolution.py
tests/test_source_projection_policy.py
```

Optional but recommended:

```text
tests/test_runtime_executability.py
tests/test_real_deck_runtime_executability.py
```

---

# 3. Gate 1 — Target semantics actor vs chooser/protection actor

## 3.1 Edit `lorcana_bot/targeting.py`

### Location

Current file anchor:

```text
lorcana_bot/targeting.py
around line 65
class TargetQueryContext
```

### Old code

```python
@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    """Context for target query resolution.

    Contains all the information needed to resolve a target descriptor
    against the current game state.
    """
    actor: int
    source_id: int | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
```

### Replacement code

```python
@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    """Context for target query resolution.

    actor:
        The semantic controller of the effect. Owner/controller target filters
        such as owner="you" and owner="opponent" are evaluated relative to this
        player.

    chooser:
        The player currently making an input choice, when different from actor.

    protection_actor:
        The player whose act of choosing should be used for Ward and
        cannot-be-targeted checks. This is normally chooser when a prompt is
        pending, otherwise actor.

    This split mirrors Lorcanito's controller/chooser separation.
    """
    actor: int
    source_id: int | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
    chooser: int | None = None
    protection_actor: int | None = None

    @property
    def chooser_actor(self) -> int:
        return self.chooser if self.chooser is not None else self.actor

    @property
    def protection_player(self) -> int:
        if self.protection_actor is not None:
            return self.protection_actor
        if self.chooser is not None:
            return self.chooser
        return self.actor
```

---

## 3.2 Edit `lorcana_bot/targeting.py`

### Location

Current file anchor:

```text
lorcana_bot/targeting.py
around line 1645
def apply_target_protections(...)
```

### Old code block inside `apply_target_protections`

```python
    actor = context.actor
    seen_ids: set[tuple[str, int]] = set()
    results: list[TargetCandidate] = []
```

### Replacement code

```python
    semantic_actor = context.actor
    protection_actor = context.protection_player
    seen_ids: set[tuple[str, int]] = set()
    results: list[TargetCandidate] = []
```

### Old Ward/cannot-be-targeted code

```python
        # Ward protection applies when the opponent is choosing a card target.
        if (
            requires_explicit_target_selection(descriptor.selector)
            and engine is not None
            and inst.controller != actor
            and engine.has_keyword(state, cid, "WARD")
        ):
            continue

        # Cannot-be-targeted protection
        if _is_protected_from_targeting(state, cid, actor, source_id):
            continue
```

### Replacement code

```python
        # Ward protection applies when the choosing player is choosing an
        # opposing card. For chosenBy: opponent, the descriptor may still be
        # semantically relative to the original controller, but Ward must be
        # evaluated relative to the physical chooser.
        if (
            requires_explicit_target_selection(descriptor.selector)
            and engine is not None
            and inst.controller != protection_actor
            and engine.has_keyword(state, cid, "WARD")
        ):
            continue

        # Cannot-be-targeted protection is also evaluated relative to the
        # physical chooser, not necessarily the original effect controller.
        if _is_protected_from_targeting(state, cid, protection_actor, source_id):
            continue
```

### Notes

Do **not** change candidate resolution ownership semantics. `resolve_candidate_targets()` should still use `context.actor` for owner/controller filters. Only protection filtering switches to `context.protection_player`.

---

# 4. Gate 2 — Complete EffectResolutionContext

## 4.1 Edit `lorcana_bot/effect_types.py`

### Location

Current file anchor:

```text
lorcana_bot/effect_types.py
around line 28
class EffectResolutionContext
```

### Old code

```python
@dataclass(frozen=True, slots=True)
class EffectResolutionContext:
    actor: int
    source: int | None = None
    target: int | None = None
    choice: Any | None = None
    optional_choices: dict[str, bool] = field(default_factory=dict)
    # B2: Trigger context fields for proper effect resolution
    event: Any | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    pending_trigger_id: str | None = None
    trigger_source: int | None = None
    trigger_subject: int | None = None
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
    slotted_targets: dict[str, Any] | None = None
    destinations: tuple[dict[str, Any], ...] = ()
    last_effect_performed: bool = False
```

### Replacement code

```python
@dataclass(frozen=True, slots=True)
class EffectResolutionContext:
    """Runtime context carried through action-effect resolution.

    actor is always the original effect controller / semantic player.
    chooser is the current player supplying input when different from actor.

    This dataclass is frozen intentionally. Do not mutate it. Use
    dataclasses.replace() or helper builders in EffectResolver.
    """
    actor: int
    source: int | None = None
    target: int | None = None
    choice: Any | None = None
    optional_choices: dict[str, bool] = field(default_factory=dict)

    # Current chooser, if a nested chooser/optional/opponent choice is active.
    chooser: int | None = None

    # Trigger context fields for proper effect resolution.
    event: Any | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    pending_trigger_id: str | None = None
    trigger_source: int | None = None
    trigger_subject: int | None = None

    # Lorcanito-aligned selection state.
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
    slotted_targets: dict[str, Any] | None = None
    destinations: tuple[dict[str, Any], ...] = ()

    # Additional pending/action resolution input.
    named_card: str | None = None
    amount_choice: int | None = None
    choice_index: int | None = None
    resolve_optional: bool | None = None
    enter_play_exerted: bool | None = None
    target_selection_resolved: bool = False

    # Result state used by if-you-do / downstream dynamic effects.
    last_effect_performed: bool = False
    last_effect_target_count: int = 0
```

---

# 5. Gate 3 — Helper builders in `effects.py`

## 5.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
line 3
from dataclasses import replace
```

Current file already imports `replace`. Keep that import.

---

## 5.2 Insert helper methods in `EffectResolver`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 18
class EffectResolver:
    def __init__(...)
```

Insert the following methods immediately after `__init__`.

### Insert this block

```python
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
```

---

# 6. Gate 4 — Replace resolver orchestration

This is the most important change.

The current resolver does this:

```python
def resolve_many(...):
    for effect in effects:
        self.resolve(state, effect, context)
```

That loses updated sequence state. Replace it with a context-returning resolver.

## 6.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 22
def resolve_many(...)
```

### Old code

```python
    def resolve_many(self, state: GameState, effects: tuple[EffectDef, ...], context: EffectResolutionContext) -> None:
        for effect in effects:
            self.resolve(state, effect, context)
```

### Replacement code

```python
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
```

---

## 6.2 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 26
def resolve(...)
```

### Old first block

```python
    def resolve(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        if effect.kind not in SUPPORTED_EFFECT_KINDS:
            raise EffectResolutionError(f"Unsupported effect kind {effect.kind}")

        kind = effect.kind
        if self._effect_chosen_by_opponent(effect) and context.source is not None and not context.current_targets:
            self._create_opponent_target_pending(state, effect, context)
            return

        if kind == "sequence":
            self.resolve_many(state, effect.effects, context)
        elif kind == "optional":
            if self._optional_accepted(effect, context):
                self.resolve_many(state, effect.effects, context)
        elif kind == "choice":
            self._resolve_choice(state, effect, context)
        elif kind == "select_target":
            return
        elif kind == "restriction":
            self._resolve_restriction(state, effect, context)
```

### Replace only that first block with this code

```python
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

        if kind == "restriction":
            self._resolve_restriction(state, effect, context)
```

### Then add this return at the very end of `resolve()`

Find the end of the long `if/elif kind == ...` dispatcher, currently ending with:

```python
        elif kind == "return_random_from_inkwell":
            self._resolve_return_random_from_inkwell(state, effect, context)
```

Replace that end block with:

```python
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
```

### Important

After this replacement, all callers that previously ignored return values still work because Python allows the return value to be ignored. But sequence resolution now uses the returned context.

---

# 7. Gate 5 — Replace choice, optional, conditional, and select-target methods

## 7.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 185
def _resolve_choice(...)
```

### Old code

```python
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
```

### Replacement code

```python
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
```

---

## 7.2 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 285
def _optional_accepted(...)
```

Keep `_optional_accepted()` if other tests still use it, but add a new `_resolve_optional()` immediately before it.

### Insert this block before `_optional_accepted`

```python
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
```

---

## 7.3 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
current conditional branch in resolve() was replaced above
```

Add this method near `_resolve_optional()`.

### Insert this block

```python
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
```

---

## 7.4 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
there is currently no _resolve_select_target method
```

Insert this method near `_resolve_conditional()`.

### Insert this block

```python
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
```

---

# 8. Gate 6 — Chooser resolver and pending creation

## 8.1 Edit `lorcana_bot/effects.py`

### Location

Insert these helpers after `_create_opponent_target_pending()` or replace that method entirely as instructed below.

### Old code to replace

```python
    def _effect_chosen_by_opponent(self, effect: EffectDef) -> bool:
        raw = self._source_raw(effect)
        target = raw.get("target")
        return target is not None and str(raw.get("chosenBy") or raw.get("chosen_by") or "").casefold() == "opponent"

    def _create_opponent_target_pending(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        from .pending_effects import create_pending_effect

        raw = self._source_raw(effect)
        target = raw.get("target") or effect.target
        if target is None:
            raise EffectResolutionError("chosenBy opponent effect requires a target")

        source_card_id = self.engine.card_def(state, context.source).id if context.source in state.cards else None
        pending_target = "target" if isinstance(effect.target, dict) else effect.target
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
            chooser_id=state.opponent(context.actor),
            source_id=context.source,
            source_card_id=source_card_id,
            effects=(pending_effect,),
            origin="opponent_choice",
            raw={
                "requirement_kind": "opponent_choice",
                "choice_type": "target",
                "target": target,
                "target_actor": context.actor,
                "selected_targets": context.current_targets,
                "context_targets": context.context_targets,
            },
        )
```

### Replacement code

```python
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
        pending_target = target if isinstance(target, dict) else effect.target

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
```

---

# 9. Gate 7 — Fix target query context construction

## 9.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 520
def _target_query_context(...)
```

### Old return block

```python
        return TargetQueryContext(
            actor=context.actor,
            source_id=context.source,
            event_payload=event_payload,
            current_targets=context.current_targets,
            context_targets=context.context_targets,
        )
```

### Replacement block

```python
        return TargetQueryContext(
            actor=context.actor,
            source_id=context.source,
            event_payload=event_payload,
            current_targets=context.current_targets,
            context_targets=context.context_targets,
            chooser=context.chooser,
            protection_actor=context.chooser,
        )
```

---

## 9.2 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 545
def _selected_card_targets_from_context(...)
```

### Old code

```python
    def _selected_card_targets_from_context(self, context: EffectResolutionContext) -> tuple[int, ...]:
        if context.current_targets:
            return context.current_targets
        if context.target is not None:
            return (context.target,)
        return ()
```

### Replacement code

```python
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
```

---

# 10. Gate 8 — Fix slotted target validation and BE_CHOSEN emission

## 10.1 Edit `lorcana_bot/pending_effects.py`

### Location

Current file anchor:

```text
lorcana_bot/pending_effects.py
around line 1710
def resolve_slotted_target_selection(...)
```

### Old validation call

```python
    normalized = normalize_slotted_target_input(slotted_targets)
    validate_slotted_targets(state, normalized, actor=pe.chooser_id, source_id=pe.source_id, engine=engine)
    flat_targets = flatten_slotted_targets(normalized)
```

### Replacement code

```python
    normalized = normalize_slotted_target_input(slotted_targets)
    validate_slotted_targets(
        state,
        normalized,
        actor=pe.raw.get("target_actor", pe.controller_id),
        source_id=pe.source_id,
        engine=engine,
    )
    flat_targets = flatten_slotted_targets(normalized)
```

### Then add these raw fields immediately after `pe.raw["slotted_targets"] = normalized`

```python
    pe.raw["target_actor"] = pe.raw.get("target_actor", pe.controller_id)
    pe.raw["protection_actor"] = pe.raw.get("protection_actor", pe.chooser_id)
```

Final function middle should look like:

```python
    pe.selected_targets = flat_targets
    pe.raw["slotted_targets"] = normalized
    pe.raw["target_actor"] = pe.raw.get("target_actor", pe.controller_id)
    pe.raw["protection_actor"] = pe.raw.get("protection_actor", pe.chooser_id)
    resolution_input = pe.raw.setdefault("resolution_input", {})
    resolution_input["slotted_targets"] = normalized
    resolution_input["targets"] = flat_targets
```

---

## 10.2 Edit `lorcana_bot/engine.py`

### Location

Current file anchor:

```text
lorcana_bot/engine.py
around line 3230
def _resolve_effects(...)
```

### Old selected target block

```python
        selected_targets = current_targets or ((target,) if target is not None else ())
        self._emit_be_chosen_events(
            state,
            actor=player,
            source=source,
            selected_targets=tuple(int(target_id) for target_id in selected_targets),
        )
```

### Replacement block

```python
        selected_targets = current_targets or ((target,) if target is not None else ())
        slotted_flat: tuple[int, ...] = ()
        if slotted_targets:
            from .targeting import flatten_slotted_targets, normalize_slotted_target_input
            slotted_flat = flatten_slotted_targets(normalize_slotted_target_input(slotted_targets))
        be_chosen_targets = tuple(dict.fromkeys((
            *(int(target_id) for target_id in selected_targets),
            *(int(target_id) for target_id in slotted_flat),
        )))
        self._emit_be_chosen_events(
            state,
            actor=player,
            source=source,
            selected_targets=be_chosen_targets,
        )
```

---

## 10.3 Edit `lorcana_bot/abilities.py`

### Location

Current file anchor:

```text
lorcana_bot/abilities.py
around line 370
execute_ability_effects(...)
```

### Old BE_CHOSEN block starts

```python
    if selected_targets:
        from lorcana_bot.constants import CARD_ACTION, CARD_CHARACTER, CARD_ITEM, EVENT_BE_CHOSEN

        source_card = engine.card_def(state, ability.source_instance_id)
        if source_card.card_type in {CARD_ACTION, CARD_ITEM, CARD_CHARACTER}:
            seen: set[int] = set()
            for target_id in selected_targets:
```

### Replace the line `if selected_targets:` and target loop setup with this

```python
    slotted_flat: tuple[int, ...] = ()
    if slotted_targets:
        from lorcana_bot.targeting import flatten_slotted_targets, normalize_slotted_target_input
        slotted_flat = flatten_slotted_targets(normalize_slotted_target_input(slotted_targets))

    be_chosen_targets = tuple(dict.fromkeys((*selected_targets, *slotted_flat)))

    if be_chosen_targets:
        from lorcana_bot.constants import CARD_ACTION, CARD_CHARACTER, CARD_ITEM, CARD_LOCATION, EVENT_BE_CHOSEN

        source_card = engine.card_def(state, ability.source_instance_id)
        if source_card.card_type in {CARD_ACTION, CARD_ITEM, CARD_CHARACTER, CARD_LOCATION}:
            seen: set[int] = set()
            for target_id in be_chosen_targets:
```

---

# 11. Gate 9 — Fix move-to-location event name

## 11.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 840
def _resolve_move_to_location(...)
```

### Old event call

```python
            self.engine.emit_event(
                state,
                "CARD_MOVED_TO_LOCATION",
                actor=context.actor,
                source=character_id,
                target=location_id,
```

### Replacement event call

First add import at top of `effects.py`:

### Old import line

```python
from .constants import ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
```

### Replacement import line

```python
from .constants import EVENT_MOVED_TO_LOCATION, ZONE_DECK, ZONE_DISCARD, ZONE_HAND, ZONE_INKWELL, ZONE_PLAY
```

Then replace the event name:

```python
            self.engine.emit_event(
                state,
                EVENT_MOVED_TO_LOCATION,
                actor=context.actor,
                source=character_id,
                target=location_id,
```

---

# 12. Gate 10 — Pending target candidate actor split

## 12.1 Edit `lorcana_bot/pending_effects.py`

### Location

Current file anchor:

```text
lorcana_bot/pending_effects.py
around line 2120
def get_valid_target_candidates_for_pending(...)
```

### Old context block

```python
    raw = pe.raw or {}
    target_actor = raw.get("target_actor", chooser_id)
    context = TargetQueryContext(
        actor=target_actor,
        source_id=pe.source_id,
        event_payload=raw.get("event_payload", {}) or {},
        current_targets=tuple(raw.get("current_targets", ()) or ()),
        context_targets=tuple(raw.get("context_targets", ()) or ()),
    )
```

### Replacement code

```python
    raw = pe.raw or {}
    target_actor = raw.get("target_actor", pe.controller_id)
    protection_actor = raw.get("protection_actor", chooser_id)
    context = TargetQueryContext(
        actor=int(target_actor),
        source_id=pe.source_id,
        event_payload=raw.get("event_payload", {}) or {},
        current_targets=tuple(raw.get("current_targets", ()) or raw.get("selected_targets", ()) or ()),
        context_targets=tuple(raw.get("context_targets", ()) or ()),
        chooser=chooser_id,
        protection_actor=int(protection_actor),
    )
```

### Why this matters

This fixes the most important semantic bug found in the audit:

```text
owner/controller filters stay relative to original effect controller
Ward/cannot-be-targeted stays relative to actual chooser
```

---

# 13. Gate 11 — Resolve pending effects into full context

## 13.1 Edit `lorcana_bot/engine.py`

### Location

Current file anchor:

```text
lorcana_bot/engine.py
around line 3860
inside _apply_resolve_pending_effect()
current EffectResolutionContext(...)
```

### Old context block

```python
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
```

### Replacement block

```python
            resolution_input = raw.get("resolution_input", {}) or {}
            context = EffectResolutionContext(
                actor=pe.controller_id,
                chooser=pe.chooser_id,
                source=pe.source_id,
                target=selected_target,
                event=event,
                event_payload=event_payload,
                choice=selected_choice,
                choice_index=selected_choice if isinstance(selected_choice, int) else None,
                pending_trigger_id=pe.origin_id if pe.origin == "bag" else None,
                trigger_source=pe.source_id if pe.origin == "bag" else None,
                trigger_subject=raw.get("trigger_subject"),
                current_targets=selected_targets or tuple(resolution_input.get("targets", ()) or ()),
                context_targets=tuple(raw.get("context_targets", ()) or resolution_input.get("context_targets", ()) or ()),
                slotted_targets=raw.get("slotted_targets") or resolution_input.get("slotted_targets"),
                destinations=tuple(
                    dict(destination)
                    for destination in (
                        raw.get("destinations")
                        or resolution_input.get("destinations")
                        or ()
                    )
                    if isinstance(destination, dict)
                ),
                named_card=raw.get("named_card") or resolution_input.get("named_card"),
                amount_choice=raw.get("amount") or resolution_input.get("amount"),
                resolve_optional=raw.get("resolve_optional") or resolution_input.get("resolve_optional"),
                enter_play_exerted=raw.get("enter_play_exerted") or resolution_input.get("enter_play_exerted"),
                last_effect_performed=bool(raw.get("last_effect_performed", False)),
                last_effect_target_count=int(raw.get("last_effect_target_count", 0) or 0),
            )
```

### Old effect resolution call

```python
            self.effect_resolver.resolve(state, current_effect, context)
```

### Replacement code

```python
            updated_context = self.effect_resolver.resolve(state, current_effect, context)
            pe.raw["last_effect_performed"] = updated_context.last_effect_performed
            pe.raw["last_effect_target_count"] = updated_context.last_effect_target_count
            pe.raw["current_targets"] = updated_context.current_targets
            pe.raw["context_targets"] = updated_context.context_targets
            pe.raw["named_card"] = updated_context.named_card
```

---

# 14. Gate 12 — Name-a-card must resume sequence context

## 14.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 1380
def _resolve_name_a_card(...)
```

### Old code

```python
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
```

### Replacement code

```python
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
```

### Also update dispatcher branch

In `resolve()`, replace:

```python
        elif kind == "name_a_card":
            self._resolve_name_a_card(state, effect, context)
```

with:

```python
        elif kind == "name_a_card":
            return self._resolve_name_a_card(state, effect, context)
```

---

# 15. Gate 13 — Reveal-and-route must use named_card and mark lastEffectPerformed

## 15.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 1405
def _resolve_reveal_and_route(...)
```

### Current behavior

The current implementation reveals the top card and routes to a static destination, but does not use the Lorcanito `routes` condition + `fallback` pattern well enough for `name-a-card` sequences.

### Replacement method

Replace the entire `_resolve_reveal_and_route()` method with:

```python
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
```

### Also update dispatcher branch

Replace:

```python
        elif kind == "reveal_and_route":
            self._resolve_reveal_and_route(state, effect, context)
```

with:

```python
        elif kind == "reveal_and_route":
            return self._resolve_reveal_and_route(state, effect, context)
```

---

# 16. Gate 14 — Put-on-top/bottom performed tracking

## 16.1 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 1270
def _resolve_put_card_on_top(...)
```

The current order logic is good. Change only the return behavior.

### Old signature

```python
    def _resolve_put_card_on_top(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
```

### Replacement signature

```python
    def _resolve_put_card_on_top(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
```

### Add this line at the very end of the method

```python
        return self._mark_result(context, performed=bool(targets), target_count=len(targets))
```

### Update dispatcher branch

Replace:

```python
        elif kind == "put_card_on_top":
            self._resolve_put_card_on_top(state, effect, context)
```

with:

```python
        elif kind == "put_card_on_top":
            return self._resolve_put_card_on_top(state, effect, context)
```

---

## 16.2 Edit `lorcana_bot/effects.py`

### Location

Current file anchor:

```text
lorcana_bot/effects.py
around line 1295
def _resolve_put_card_on_bottom(...)
```

### Old signature

```python
    def _resolve_put_card_on_bottom(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
```

### Replacement signature

```python
    def _resolve_put_card_on_bottom(
        self,
        state: GameState,
        effect: EffectDef,
        context: EffectResolutionContext,
    ) -> EffectResolutionContext:
```

### Add this line at the very end of the method

```python
        return self._mark_result(context, performed=bool(targets), target_count=len(targets))
```

### Update dispatcher branch

Replace:

```python
        elif kind == "put_card_on_bottom":
            self._resolve_put_card_on_bottom(state, effect, context)
```

with:

```python
        elif kind == "put_card_on_bottom":
            return self._resolve_put_card_on_bottom(state, effect, context)
```

---

# 17. Gate 15 — Runtime executability must be truthful

## 17.1 Edit `lorcana_bot/decks/runtime_executability.py`

### Location

Current file anchor:

```text
lorcana_bot/decks/runtime_executability.py
around line 730
def _source_opponent_choice_requirement_supported(...)
```

### Old code

```python
def _source_opponent_choice_requirement_supported(effect: SourceEffectDef) -> bool:
    raw = effect.raw or {}

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            if str(value.get("chosenBy", value.get("chosen_by", ""))).casefold() == "opponent":
                return True
            if str(value.get("chooser", "")).casefold() == "opponent":
                return True
            return any(walk(child) for child in value.values())
        if isinstance(value, (list, tuple)):
            return any(walk(child) for child in value)
        return False

    return walk(raw)
```

### Replacement code

```python
def _source_opponent_choice_requirement_supported(effect: SourceEffectDef) -> bool:
    """Return True only for opponent-choice shapes the runtime actually supports.

    Supported:
      1. leaf effect with chosenBy/chosen_by="opponent"
      2. leaf effect has a supported target shape
      3. effect kind is executable by EffectResolver

    Not supported here:
      - parent optional with chooser="OPPONENT"
      - parent choice with chooser="OPPONENT"
      - arbitrary nested chooser inheritance
      - for-each-opponent
    Those become executable only after their runtime continuation tests exist.
    """
    raw = effect.raw or {}
    chosen_by = str(raw.get("chosenBy") or raw.get("chosen_by") or "").casefold()
    if chosen_by != "opponent":
        return False

    target = raw.get("target")
    if target is None:
        return False

    if not _source_target_shape_supported(target):
        return False

    engine_kind = _runtime_effect_kind(effect.kind)
    return engine_kind in SUPPORTED_EFFECT_KINDS
```

### After full chooser/optional tests pass

Only after the optional/choice continuation tests in this guide pass, extend this function with explicit support for:

```text
optional chooser=OPPONENT with one executable child effect
choice chooser=OPPONENT with executable options
```

Do not use recursive `walk()` as a support classifier again.

---

# 18. Gate 16 — Resolution requirement classification

## 18.1 Edit `lorcana_bot/card_logic/resolution_requirements.py`

### Location

Current file anchor:

```text
lorcana_bot/card_logic/resolution_requirements.py
around line 18
_ALWAYS_SUPPORTED_REQUIREMENTS
```

### Current code

```python
_ALWAYS_SUPPORTED_REQUIREMENTS = frozenset({
    "optional",
    "choice",
    "target",
    "opponent_choice",
})
```

### Replacement code

```python
_ALWAYS_SUPPORTED_REQUIREMENTS = frozenset({
    "optional",
    "choice",
    "target",
})
```

### Then update `_requirement_supported_for_effect(...)`

### Old code

```python
def _requirement_supported_for_effect(effect: SourceEffectDef, requirement: str) -> bool:
    if requirement in _ALWAYS_SUPPORTED_REQUIREMENTS:
        return True
    return requirement in _SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND.get(effect.kind, frozenset())
```

### Replacement code

```python
def _requirement_supported_for_effect(effect: SourceEffectDef, requirement: str) -> bool:
    if requirement in _ALWAYS_SUPPORTED_REQUIREMENTS:
        return True
    if requirement == "opponent_choice":
        raw = effect.raw or {}
        chosen_by = str(raw.get("chosenBy") or raw.get("chosen_by") or "").casefold()
        return chosen_by == "opponent" and raw.get("target") is not None
    return requirement in _SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND.get(effect.kind, frozenset())
```

This prevents parent `chooser: "OPPONENT"` shapes from being blindly marked supported until their continuation path is truly implemented.

---

# 19. Gate 17 — Tests to add

## 19.1 `tests/test_targeting.py`

Add:

```python
def test_protection_actor_allows_opponent_to_choose_own_ward_character(engine, state):
    from lorcana_bot.constants import KEYWORD_WARD, ZONE_PLAY
    from lorcana_bot.targeting import (
        TargetQueryContext,
        apply_target_protections,
        normalize_target_descriptor,
        resolve_candidate_targets,
    )
    from tests.conftest import put_card

    ward_card = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY)
    state.cards[ward_card].temporary_keywords.append(KEYWORD_WARD)

    descriptor = normalize_target_descriptor({
        "selector": "chosen",
        "owner": "opponent",
        "zones": ["play"],
        "cardTypes": ["character"],
    })
    assert descriptor is not None

    # Semantic actor is player 0, so owner="opponent" means player 1.
    # Physical chooser/protection actor is player 1, so Ward should not block.
    context = TargetQueryContext(actor=0, chooser=1, protection_actor=1)
    candidates = resolve_candidate_targets(state, engine, descriptor, context)
    protected = apply_target_protections(state, engine, candidates, descriptor, context)

    assert ward_card in {candidate.id for candidate in protected}
```

---

## 19.2 `tests/test_effects.py`

Add:

```python
def test_sequence_promotes_current_targets_for_previous_target(engine, state):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import ZONE_PLAY
    from tests.conftest import put_card

    source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
    target = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY)

    effect = EffectDef(
        "sequence",
        effects=(
            EffectDef("select_target", target="chosen_character"),
            EffectDef("deal_damage", amount=2, target={"ref": "previous-target"}),
        ),
    )

    engine.effect_resolver.resolve(
        state,
        effect,
        EffectResolutionContext(actor=0, source=source, current_targets=(target,)),
    )

    assert state.cards[target].damage == 2
```

Add:

```python
def test_if_you_do_uses_last_effect_performed_true(engine, state):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import ZONE_PLAY
    from tests.conftest import put_card

    source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
    target = put_card(state, engine, 1, "Amber Guard", ZONE_PLAY)

    effect = EffectDef(
        "sequence",
        effects=(
            EffectDef("exert", target="chosen_character"),
            EffectDef(
                "conditional",
                condition={"type": "if-you-do"},
                effects=(EffectDef("draw", amount=1, target="controller"),),
            ),
        ),
    )

    hand_before = len(state.players[0].hand)

    engine.effect_resolver.resolve(
        state,
        effect,
        EffectResolutionContext(actor=0, source=source, current_targets=(target,)),
    )

    assert state.cards[target].exerted is True
    assert len(state.players[0].hand) == hand_before + 1
```

Add:

```python
def test_if_you_do_false_when_previous_effect_did_not_perform(engine, state):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import ZONE_PLAY
    from tests.conftest import put_card

    source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)

    effect = EffectDef(
        "sequence",
        effects=(
            EffectDef("select_target", target="chosen_character"),
            EffectDef(
                "conditional",
                condition={"type": "if-you-do"},
                effects=(EffectDef("draw", amount=1, target="controller"),),
            ),
        ),
    )

    hand_before = len(state.players[0].hand)

    engine.effect_resolver.resolve(
        state,
        effect,
        EffectResolutionContext(actor=0, source=source, current_targets=()),
    )

    assert len(state.players[0].hand) == hand_before
```

Add:

```python
def test_slotted_targets_emit_be_chosen_for_subject_and_location(engine, state):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import EVENT_BE_CHOSEN, ZONE_PLAY
    from tests.conftest import put_card

    source = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY)
    character = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
    location = put_card(state, engine, 0, "Location", ZONE_PLAY)

    # Ensure card_def for `location` is a location in your local fixture.
    # If the fixture lacks a location, use the test helper from
    # test_activated_abilities_execution.py that creates a CardDatabase with a location.

    effect = EffectDef(
        "move_to_location",
        raw={
            "raw": {
                "character": {"selector": "chosen", "owner": "you", "zones": ["play"], "cardTypes": ["character"]},
                "location": {"selector": "chosen", "owner": "you", "zones": ["play"], "cardTypes": ["location"]},
            }
        },
    )

    engine.effect_resolver.resolve(
        state,
        effect,
        EffectResolutionContext(
            actor=0,
            source=source,
            slotted_targets={
                "kind": "move-to-location",
                "subject": (character,),
                "location": (location,),
            },
        ),
    )

    be_chosen_targets = [
        event.target for event in state.event_log
        if event.event_type == EVENT_BE_CHOSEN
    ]
    assert character in be_chosen_targets
    assert location in be_chosen_targets
```

---

## 19.3 `tests/test_pending_effects.py`

Add:

```python
def test_chosen_by_opponent_effect_creates_pending_for_opponent_and_resolves_under_controller(state_with_pending):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import ACTION_RESOLVE_PENDING_EFFECT, ZONE_PLAY
    from lorcana_bot.state import CardInstance

    state, engine = state_with_pending

    state.cards[1] = CardInstance(instance_id=1, card_id=DEMO_FEATURE_CARD_IDS["basic_character"], owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    state.cards[40] = CardInstance(instance_id=40, card_id=DEMO_FEATURE_CARD_IDS["basic_character"], owner=1, controller=1, zone=ZONE_PLAY)
    state.players[1].play.append(40)

    effect = EffectDef(
        "deal_damage",
        amount=1,
        target={
            "selector": "chosen",
            "owner": "opponent",
            "zones": ["play"],
            "cardTypes": ["character"],
        },
        raw={
            "raw": {
                "type": "deal-damage",
                "amount": 1,
                "chosenBy": "opponent",
                "target": {
                    "selector": "chosen",
                    "owner": "opponent",
                    "zones": ["play"],
                    "cardTypes": ["character"],
                },
            }
        },
    )

    engine.effect_resolver.resolve(state, effect, EffectResolutionContext(actor=0, source=1))

    assert len(state.pending_effects) == 1
    pe = state.pending_effects[0]
    assert pe.controller_id == 0
    assert pe.chooser_id == 1
    assert pe.raw["target_actor"] == 0
    assert pe.raw["protection_actor"] == 1

    assert not [a for a in engine.legal_actions(state, 0) if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
    actions = [a for a in engine.legal_actions(state, 1) if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
    assert actions
    action = next(a for a in actions if a.target == 40)

    next_state = engine.apply_action(state, action)

    assert next_state.cards[40].damage == 1
    assert not next_state.pending_effects
```

Add:

```python
def test_opponent_choice_ward_uses_chooser_for_protection(state_with_pending):
    from lorcana_bot.cards import EffectDef
    from lorcana_bot.effect_types import EffectResolutionContext
    from lorcana_bot.constants import ACTION_RESOLVE_PENDING_EFFECT, KEYWORD_WARD, ZONE_PLAY
    from lorcana_bot.state import CardInstance

    state, engine = state_with_pending

    state.cards[1] = CardInstance(instance_id=1, card_id=DEMO_FEATURE_CARD_IDS["basic_character"], owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    state.cards[40] = CardInstance(instance_id=40, card_id=DEMO_FEATURE_CARD_IDS["basic_character"], owner=1, controller=1, zone=ZONE_PLAY)
    state.cards[40].temporary_keywords.append(KEYWORD_WARD)
    state.players[1].play.append(40)

    effect = EffectDef(
        "deal_damage",
        amount=1,
        target={"selector": "chosen", "owner": "opponent", "zones": ["play"], "cardTypes": ["character"]},
        raw={"raw": {"chosenBy": "opponent", "target": {"selector": "chosen", "owner": "opponent", "zones": ["play"], "cardTypes": ["character"]}}},
    )

    engine.effect_resolver.resolve(state, effect, EffectResolutionContext(actor=0, source=1))

    actions = [a for a in engine.legal_actions(state, 1) if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
    assert any(a.target == 40 for a in actions)
```

---

## 19.4 `tests/test_source_projection_policy.py`

Add:

```python
def test_opponent_choice_parent_chooser_not_marked_supported_without_runtime_shape():
    ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "play", "on": "SELF", "timing": "when"},
        "effect": {
            "type": "optional",
            "chooser": "OPPONENT",
            "effect": {
                "type": "discard",
                "target": "OPPONENT",
                "chosen": True,
                "amount": 1,
                "from": "hand",
            },
        },
    })

    # This should remain unsupported until optional chooser continuation is
    # fully tested end-to-end. Do not allow broad recursive classifier support.
    assert ability.execution_status != ExecutionStatus.EXECUTABLE
```

Add:

```python
def test_leaf_chosen_by_opponent_target_shape_projects_supported():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "deal-damage",
            "amount": 1,
            "chosenBy": "opponent",
            "target": {
                "selector": "chosen",
                "owner": "opponent",
                "zones": ["play"],
                "cardTypes": ["character"],
            },
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
```

---

# 20. Validation commands

Run after each gate if implementing incrementally:

```bash
python3 -m py_compile \
  lorcana_bot/targeting.py \
  lorcana_bot/effect_types.py \
  lorcana_bot/effects.py \
  lorcana_bot/abilities.py \
  lorcana_bot/engine.py \
  lorcana_bot/pending_effects.py \
  lorcana_bot/card_logic/resolution_requirements.py \
  lorcana_bot/decks/runtime_executability.py
```

Targeted tests:

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_activated_abilities_execution.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
```

Full tests:

```bash
python3 -m pytest -q
```

Import check:

```bash
python3 - <<'PY'
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

db, report = import_lorcanito_source_cards(
    "data/lorcanito_runtime_extracted/cards.normalized.json"
)

print("cards:", len(db))
print("errors:", report.errors)
print("ability records:", report.ability_records_loaded)
print("unsupported:", report.unsupported_by_reason)
print("execution status counts:", report.execution_status_counts)
PY
```

Regenerate report:

```bash
python3 scripts/report_lorcanito_v2_unsupported.py
```

---

# 21. Expected report movement

After truthful classifier correction, you may see an initial movement like:

```text
unsupported_choice may increase slightly
unsupported_condition may remain high
unsupported_targeting may remain close to current
```

That is acceptable if it is caused by removing false support for parent `chooser: OPPONENT`.

After the full runtime implementation and tests pass, expected final movement:

```text
unsupported_choice should stay low or decrease from 18
effect_condition:if-you-do should decrease from 59
effect.type:sequence:unsupported_condition should decrease
effect.type:optional:unsupported_condition should decrease
name-a-card unsupported_choice records should decrease
reveal-and-route conditional records should move deeper or become executable
```

Red flags:

```text
errors must remain []
unsupported_choice must not drop by broad recursive classifier support
if-you-do must not be marked supported unless last_effect_performed is tested
opponent chooser tests must fail if controller tries to resolve opponent choice
Ward test must prove protection actor is the chooser, not the semantic controller
```

---

# 22. Acceptance criteria

Do not accept the phase unless all are true:

```text
1. Full pytest passes.
2. Import errors remain [].
3. Runtime report regenerated.
4. opponent_choice support is no longer broad-recursive.
5. leaf chosenBy: opponent target effect creates pending for opponent.
6. controller cannot resolve opponent pending.
7. opponent can resolve pending.
8. target owner semantics remain relative to controller.
9. Ward/protection semantics use chooser.
10. slotted move-to-location emits MOVED_TO_LOCATION.
11. slotted target subject and location emit BE_CHOSEN.
12. sequence carries context_targets across effects.
13. previous-target works from context_targets.
14. if-you-do true branch runs only after performed effects.
15. if-you-do false branch does not run after failed/no-op effects.
16. name-a-card pending stores named_card into resumed context.
17. reveal-and-route consumes named_card and fallback/route logic.
18. put-on-top and put-on-bottom still preserve selected target order.
19. unsupported report changes match real runtime behavior.
20. no unsupported records are suppressed globally.
```

---

# 23. Why this is the correct completion of the phase

This completes the Lorcanito-equivalent routing layer currently relevant to LorcanaChamp's GameEngine.

It does **not** claim total Lorcanito parity for later mechanics such as:

```text
static/replacement full registry parity
put-under / move-cards-from-under
advanced costs
full reveal-until-match
boost
all multiplayer for-each-opponent details
```

But it should complete the engine architecture needed before those future workstreams:

```text
controller vs chooser
pending input continuation
selection state
slot state
destination state
last effect result state
truthful support classification
```

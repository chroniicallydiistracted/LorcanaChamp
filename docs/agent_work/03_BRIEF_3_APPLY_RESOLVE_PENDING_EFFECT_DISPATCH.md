# TECHNICAL IMPLEMENTATION BRIEF 3 — Dispatch Special Pending Requirements in `_apply_resolve_pending_effect()`

Goal:
Make `GameEngine._apply_resolve_pending_effect()` actually route `requirement_kind` actions to the corresponding pending resolver. This is the core Microfix 4 runtime change.

Do not modify `legal_actions()` in this brief.
Do not modify tests in this brief.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 1480-1565`
* **Snippet:**
```python
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
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
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
                    top_cards = tuple(action.choice.get("top_cards", ()))
                    bottom_cards = tuple(action.choice.get("bottom_cards", ()))
                    resolve_scry_ordering(state, pending_id, top_cards, bottom_cards)

                elif requirement_kind == "search_selection":
                    selected_card_id = action.choice.get("selected_card_id")
                    if selected_card_id is None and choice_index is not None:
                        try:
                            selected_card_id = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid search choice index {choice_index}") from exc
                    if selected_card_id is None:
                        raise IllegalActionError("search_selection requires selected_card_id")
                    resolve_search_selection(state, pending_id, selected_card_id)

                elif requirement_kind == "reveal_routing":
                    destination = action.choice.get("destination")
                    resolve_reveal_routing(state, pending_id, destination)

                elif requirement_kind == "named_card":
                    named_card = action.choice.get("named_card")
                    if named_card is None and choice_index is not None:
                        try:
                            named_card = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid named-card choice index {choice_index}") from exc
                    if not named_card:
                        raise IllegalActionError("named_card requirement requires named_card")
                    resolve_named_card(state, pending_id, str(named_card))

                elif requirement_kind == "destination":
                    destination = action.choice.get("destination")
                    if destination is None and choice_index is not None:
                        try:
                            destination = pe.choice_options[choice_index]
                        except IndexError as exc:
                            raise IllegalActionError(f"Invalid destination choice index {choice_index}") from exc
                    if not destination:
                        raise IllegalActionError("destination requirement requires destination")
                    resolve_destination_choice(state, pending_id, str(destination))

            except ValueError as exc:
                raise IllegalActionError(str(exc)) from exc

            complete_pending_effect(state, pending_id)
            return

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
```

Also update the pending_effect imports at the top of `engine.py`.

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Lines 68-80`
* **Current Snippet:**
```python
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
```

* **Expected Target State:**
```python
from .pending_effects import (
    has_pending_effects,
    get_current_pending_effect,
    get_pending_effect_by_id,
    get_valid_targets_for_requirement,
    resolve_pending_effect_target,
    resolve_pending_effect_choice,
    resolve_pending_effect_optional,
    resolve_scry_ordering,
    resolve_search_selection,
    resolve_reveal_routing,
    resolve_named_card,
    resolve_destination_choice,
    advance_pending_effect,
    complete_pending_effect,
    get_next_pending_effect_chooser,
)
```

### 3. Fixes Needed

* **Action:** `REPLACE`
* **Delta Description:** Add a `requirement_kind` dispatch block after optional accept/decline handling and before generic target/choice resolution. This block must route `scry_ordering`, `search_selection`, `reveal_routing`, `named_card`, and `destination` to their specialized pending resolvers. Specialized pending effects must complete and return immediately. Generic target/choice/current_effect behavior must remain unchanged for ordinary pending effects.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Pending resolution dispatch sections`
* **Logic Context:**
```typescript
// Pending effects are resumed according to the required resolution input.
// Scry/search/reveal/named/destination inputs are not resolved as generic
// current effects; the stored requirement decides how player input is applied.
function resolvePendingActionEffect(
  pendingEffectId: string,
  resolutionInput: PendingActionResolutionInput,
) {
  // validate and merge resolution input
  // route based on the pending effect requirement
  // complete or continue the pending effect
}
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Manual checks:
```bash
grep -n "requirement_kind in" lorcana_bot/engine.py
grep -n "resolve_scry_ordering" lorcana_bot/engine.py
grep -n "resolve_search_selection" lorcana_bot/engine.py
grep -n "resolve_reveal_routing" lorcana_bot/engine.py
grep -n "resolve_named_card" lorcana_bot/engine.py
grep -n "resolve_destination_choice" lorcana_bot/engine.py
```

Expected:
- `_apply_resolve_pending_effect()` dispatches special requirement kinds.
- Generic pending effect resolution still exists after the special dispatch block.
- Invalid special choices raise `IllegalActionError`.

### 6. Final Response Requirements

The implementation agent must report:
1. Files changed.
2. Requirement kinds dispatched in `_apply_resolve_pending_effect()`.
3. Whether special requirement dispatch completes and returns.
4. Whether generic pending effect behavior remains.
5. Exact pytest commands run and results.
6. Confirmation that `legal_actions()` was not modified in this brief.

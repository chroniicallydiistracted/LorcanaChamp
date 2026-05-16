# TECHNICAL IMPLEMENTATION BRIEF 1 — Pending Resolution Input Foundation

Goal:
Add the shared pending-resolution input foundation in `pending_effects.py` so Microfix 9 requirement kinds can persist player choices consistently before engine dispatch is expanded.

Do not modify `engine.py` in this brief.
Do not modify automation in this brief.
Do not implement the Microfix 10 targeting service here.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/pending_effects.py`
* **Line Range:** `Lines 98-112`
* **Snippet:**
```python
PENDING_REQUIREMENT_KINDS = frozenset({
    "choice",  # Index-based choice
    "optional",  # Accept/decline
    "named_card",  # Name a specific card
    "amount",  # Choose a numeric amount
    "destination",  # Choose destination zone
    "ordering",  # Order cards (top/bottom)
    "opponent_choice",  # Opponent chooses
    "scry_ordering",  # Scry: put N on top, rest on bottom
    "reveal_routing",  # Reveal and route to destination
    "search_selection",  # Search deck and select card
    "deck_ordering",  # General deck ordering
})
```

Current gaps:

```text
target, multi_target, discard_choice, and enter_play_exerted are not listed.
There is no shared helper for writing pe.raw["resolution_input"].
General requirement resolvers do not exist for amount, target(s), discard-choice, choice, optional, opponent-choice, or enter-play-exerted.
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
PENDING_REQUIREMENT_KINDS = frozenset({
    "choice",
    "optional",
    "named_card",
    "amount",
    "target",
    "multi_target",
    "discard_choice",
    "destination",
    "ordering",
    "opponent_choice",
    "enter_play_exerted",
    "scry_ordering",
    "reveal_routing",
    "search_selection",
    "deck_ordering",
})
```

Add helper functions:

```python
def get_resolution_input(pe: PendingEffect) -> dict[str, Any]:
    return pe.raw.setdefault("resolution_input", {})


def set_resolution_input(pe: PendingEffect, key: str, value: Any) -> None:
    get_resolution_input(pe)[key] = value
```

Add resolver functions after the existing generic pending resolvers:

```python
def resolve_amount_choice(state: GameState, pending_id: str, amount: int) -> None: ...
def resolve_target_selection(state: GameState, pending_id: str, targets: tuple[int, ...]) -> None: ...
def resolve_discard_choice(state: GameState, pending_id: str, card_ids: tuple[int, ...]) -> None: ...
def resolve_choice_index(state: GameState, pending_id: str, choice_index: int) -> None: ...
def resolve_optional_choice(state: GameState, pending_id: str, accepted: bool) -> None: ...
def resolve_enter_play_exerted_choice(state: GameState, pending_id: str, enter_play_exerted: bool) -> None: ...
```

Resolver storage rules:

```text
amount -> pe.raw["amount"] and pe.raw["resolution_input"]["amount"]
target -> pe.selected_targets and pe.raw["resolution_input"]["targets"]
multi_target -> pe.selected_targets and pe.raw["resolution_input"]["targets"]
discard_choice -> pe.raw["discard_card_ids"] and pe.raw["resolution_input"]["targets"]
choice -> pe.selected_choice and pe.raw["resolution_input"]["choice_index"]
optional -> pe.accepted and pe.raw["resolution_input"]["resolve_optional"]
enter_play_exerted -> pe.raw["enter_play_exerted"] and pe.raw["resolution_input"]["enter_play_exerted"]
```

Validation rules:

```text
amount: integer, within min/max/options if present in pe.raw or pe.raw["requirement"]
targets: all IDs exist in state.cards, count within min/max if present
discard_choice: all IDs exist, belong to chooser/controller candidate list if present, count within min/max
choice_index: integer in range of choice_options/options if options exist
optional: boolean
enter_play_exerted: boolean
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add missing requirement kind names and shared `resolution_input` helper functions.
* **Delta Description:** Add resolver helpers that validate and persist player inputs but do not yet change engine legal-action enumeration.
* **Delta Description:** Keep existing special resolvers (`resolve_scry_ordering`, `resolve_search_selection`, `resolve_reveal_routing`, `resolve_named_card`, `resolve_destination_choice`) intact.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/runtime-state.ts`
* **Line Range:** `Lines 448-471`
* **Logic Context:**
```typescript
export interface PendingActionResolutionInput {
  targets?: ...
  amount?: Amount;
  namedCard?: string;
  resolveOptional?: boolean;
  enterPlayExerted?: boolean;
  choiceIndex?: number;
  destinations?: ...
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts`
* **Line Range:** `Lines 151-178`
* **Logic Context:** Lorcanito normalizes `amount`, `choiceIndex`, `resolveOptional`, `enterPlayExerted`, and `namedCard` from pending resolution input into the active selection.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Manual checks:
```bash
grep -n "def get_resolution_input" lorcana_bot/pending_effects.py
grep -n "def resolve_amount_choice" lorcana_bot/pending_effects.py
grep -n "def resolve_discard_choice" lorcana_bot/pending_effects.py
grep -n "\"discard_choice\"" lorcana_bot/pending_effects.py
grep -n "\"enter_play_exerted\"" lorcana_bot/pending_effects.py
```

Expected:
- Resolver helpers exist.
- Resolver helpers write into `pe.raw["resolution_input"]`.
- Existing pending tests continue to pass.
- `engine.py` and automation files are not modified.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Requirement kinds added.
3. Resolver helpers added.
4. Exact fields written into `resolution_input`.
5. Exact pytest commands run and results.
6. Confirmation that `engine.py` was not modified.

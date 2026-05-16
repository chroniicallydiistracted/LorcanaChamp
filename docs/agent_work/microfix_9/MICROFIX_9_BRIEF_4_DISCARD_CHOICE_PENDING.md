# TECHNICAL IMPLEMENTATION BRIEF 4 — Discard Choice Pending Requirement

Goal:
Implement engine-path discard-choice pending behavior for discard effects that require explicit card selection instead of silently discarding the first card.

This brief depends on Briefs 1-3.
Do not implement the full Microfix 10 targeting service here.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Lines 207-234`
* **Snippet:**
```python
player = self._target_player(state, effect, context)
for _ in range(min(self._amount(effect), len(state.players[player].hand))):
    self.engine._discard_eventful(
        state,
        state.players[player].hand[0],
        actor=player,
        source_id=context.source,
        reason="effect",
    )
```

Current issue:

```text
Effects that should let a player choose discard cards currently discard from the front of hand.
Opponent-chosen and explicit chosen discard effects cannot suspend into pending selection.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
When a discard effect requires explicit choice:
1. Build discard candidates from the target player's hand.
2. Create a pending effect with requirement_kind="discard_choice".
3. Store candidate IDs, min/max selection count, chooser_id, target_player_id, and source metadata.
4. Do not discard immediately.
5. legal_actions() exposes discard_card_ids choices.
6. _apply_resolve_pending_effect() validates the selected IDs and calls _discard_eventful for each selected card.
```

Add a helper in `pending_effects.py`:

```python
def create_discard_choice_pending_effect(
    state: GameState,
    *,
    controller_id: int,
    chooser_id: int,
    source_id: int | None,
    source_card_id: str | None,
    target_player_id: int,
    candidate_ids: tuple[int, ...],
    min_select: int,
    max_select: int,
    origin: str = "discard_choice",
    origin_id: str | None = None,
    raw: dict[str, Any] | None = None,
) -> PendingEffect: ...
```

Discard effect rules for this brief:

```text
If effect.raw["chosen"] is true, create pending discard_choice.
If effect.raw["chosen_by"] or effect.raw["chosenBy"] is "opponent", chooser is opponent of controller.
If target player is not the resolving actor and explicit choice is required, create pending discard_choice.
If no explicit choice is required, preserve current deterministic discard behavior.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add discard-choice pending creation helper.
* **Delta Description:** Update `EffectResolver._discard()` to create a pending effect when explicit discard selection is required.
* **Delta Description:** Update `_apply_resolve_pending_effect()` so resolving `discard_choice` discards selected cards through `GameEngine._discard_eventful`.
* **Delta Description:** Store selected discard IDs in `pe.raw["resolution_input"]["targets"]`.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/discard-effect.ts`
* **Line Range:** `Lines 204-258`
* **Logic Context:** Lorcanito computes discard candidates, determines chooser, creates a `discard-choice` pending action effect when explicit selection is required, and suspends resolution.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest -q
```

New tests required:

```text
chosen discard creates discard_choice pending and does not discard immediately.
legal_actions exposes exact discard combinations.
apply discard_choice moves selected cards to discard through _discard_eventful.
opponent-chosen discard makes opponent the chooser.
invalid discard selection raises IllegalActionError.
non-explicit discard preserves existing deterministic behavior.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. How discard-choice candidates are built.
3. How chooser is determined.
4. Exact eventful discard route used.
5. Tests added.
6. Exact pytest commands run and results.

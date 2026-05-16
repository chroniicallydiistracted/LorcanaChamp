# TECHNICAL IMPLEMENTATION BRIEF 4 — Engine Legal Action Integration

Goal:
Use the targeting service for normal action-card target enumeration and validation in `GameEngine`.

This brief depends on Briefs 1-3.
Do not modify pending target enumeration yet; that is Brief 5.
Do not implement slotted targets yet.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `Around _effect_targets_for_card()`
* **Snippet:**
```python
def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]:
    card = self.card_def(state, source)
    targets: set[int] = set()
    for target_kind in self._effect_target_kinds(card.effects):
        if target_kind == "opposing_character":
            ...
        elif target_kind == "chosen_character":
            ...
    return sorted(targets)
```

Current issue:

```text
Only a narrow subset of target aliases is legal-action visible.
chosen_item, chosen_location, chosen_player, damaged/exerted filters, current/context aliases, and future DSL descriptors are not centralized.
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
GameEngine._effect_targets_for_card() delegates to lorcana_bot.targeting.
GameEngine._effect_requires_target() uses normalized target descriptors.
legal_actions() for ACTION_PLAY_CARD emits target actions from the service.
apply_action(validate=True) continues to reject illegal target actions.
```

Integration rules:

```text
Action cards with chosen card targets enumerate legal card targets.
chosen_player emits player target actions.
Ward and cannot-be-targeted are honored through targeting service.
ZONE_UNDER cards are excluded.
Items and locations can be selected when the effect target asks for them.
Existing challenge targets remain unchanged in this brief.
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Replace direct target enumeration in `_effect_targets_for_card()` with targeting service calls.
* **Delta Description:** Keep fallback behavior for unsupported descriptors conservative: no target actions rather than broad illegal targets.
* **Delta Description:** Add engine-path tests for action-card targets.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts`
* **Logic Context:** Lorcanito target availability determines when explicit target selection is required and which candidates are legal.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
```

New tests required:

```text
chosen_character action excludes opposing Ward.
chosen_item action can target items.
chosen_location action can target locations.
chosen_player action emits player targets.
chosen_damaged_character only emits damaged characters.
ZONE_UNDER card is not a legal action target.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Engine methods revised.
3. Target aliases now visible in legal actions.
4. Tests added.
5. Exact pytest commands run and results.

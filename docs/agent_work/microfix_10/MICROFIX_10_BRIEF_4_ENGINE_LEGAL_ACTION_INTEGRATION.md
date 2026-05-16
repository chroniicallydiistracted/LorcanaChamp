# TECHNICAL IMPLEMENTATION BRIEF 4 — Engine Legal Action Integration

Goal:
Use the targeting service for normal action-card target enumeration and validation in `GameEngine`.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Briefs 1-3.
Do not modify pending target enumeration yet; that is Brief 5.
Do not implement slotted targets yet.
Do not rewrite targeting.py except for a very small compatibility fix if engine integration exposes one.

Corrected Brief 1-3 baseline that must remain true:
```text
resolve_candidate_targets(), apply_target_protections(), and analyze_target_selection_availability() already exist.
TargetDescriptor has allow_duplicate_targets.
TargetSelectionAvailability has allows_explicit_empty_target_selection.
Context-derived card candidates are already validated by targeting.py; do not add raw context-target paths in engine.py.
Unknown/unsupported descriptors must produce no target actions.
tests/test_targeting.py currently collects 116 tests before Brief 4 work begins.
```

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

Expected integration shape:
```text
Build TargetDescriptor objects with normalize_target_descriptor()/normalize_target_descriptors().
Build TargetQueryContext(actor=player, source_id=source).
Call resolve_candidate_targets().
Call apply_target_protections() on the returned candidates.
Call analyze_target_selection_availability() on the protected candidates.
Only emit target actions when availability says an explicit selection is satisfiable.
Keep ACTION_CHALLENGE and location movement target logic unchanged in this brief.
```

Recommended engine shape:
```python
def _effect_target_descriptors_for_card(self, state: GameState, source: int) -> tuple[TargetDescriptor, ...]: ...

def _effect_target_candidates_for_card(
    self,
    state: GameState,
    player: int,
    source: int,
) -> tuple[TargetCandidate, ...]: ...

def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]:
    """Backward-compatible card-only wrapper for existing callers/tests."""
```

Action encoding rules:
```text
Card targets: emit Action(ACTION_PLAY_CARD, actor=player, card=cid, target=card_instance_id).
Player targets: do not store player IDs in Action.target. Emit Action(ACTION_PLAY_CARD, actor=player, card=cid, choice={"target_kind": "player", "player": player_id}).
When applying an ACTION_PLAY_CARD with a player choice, pass that player ID into EffectResolutionContext.choice so EffectResolver._target_player(..., "chosen_player") can consume it.
Do not change Action dataclass shape in this brief.
Do not encode card targets in Action.choice in this brief.
```

Integration rules:

```text
Action cards with chosen card targets enumerate legal card targets.
chosen_player emits player target actions.
chosen_player legal actions use Action.choice, not Action.target.
Ward and cannot-be-targeted are honored through targeting service.
ZONE_UNDER cards are excluded.
Items and locations can be selected when the effect target asks for them.
Existing challenge targets remain unchanged in this brief.
Unsupported/unknown target descriptors must not create broad fallback targets.
Action cards with mandatory explicit targets and zero protected candidates must not emit a no-target ACTION_PLAY_CARD.
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Replace direct target enumeration in `_effect_targets_for_card()` with targeting service calls.
* **Delta Description:** Add or revise a helper that returns `TargetCandidate` objects so legal action construction can distinguish card targets from player targets.
* **Delta Description:** Preserve `_effect_targets_for_card()` as a card-only wrapper if existing tests/callers rely on its list[int] return.
* **Delta Description:** For chosen_player action cards, update `_apply_play()`/`_resolve_effects()` minimally so `Action.choice["player"]` becomes `EffectResolutionContext.choice`.
* **Delta Description:** Keep fallback behavior for unsupported descriptors conservative: no target actions rather than broad illegal targets.
* **Delta Description:** Add engine-path tests for action-card targets.
* **Delta Description:** Do not revise pending target/multi_target branches in this brief.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts`
* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts`
* **Logic Context:** Lorcanito target availability determines when explicit target selection is required and which candidates are legal. Resolved target queries distinguish card IDs from player IDs; preserve that distinction in Python action encoding.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_locations_and_keywords.py -q
python3 -m pytest -q
git diff --check
```

New tests required:

```text
chosen_character action excludes opposing Ward.
chosen_item action can target items.
chosen_location action can target locations.
chosen_player action emits player targets through Action.choice and resolves through EffectResolutionContext.choice.
chosen_damaged_character only emits damaged characters.
ZONE_UNDER card is not a legal action target.
mandatory chosen_character action with only Ward/protected candidates emits no no-target play action.
unsupported target descriptor emits no broad fallback targets.
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. Engine methods revised.
3. Target aliases now visible in legal actions.
4. Tests added.
5. How card-target actions and player-target actions are encoded.
6. Exact pytest commands run and results.

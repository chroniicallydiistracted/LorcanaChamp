# TECHNICAL IMPLEMENTATION BRIEF 3 — Selection Availability And Protections

Goal:
Add target availability analysis and protection rules: min/max selections, Ward, cannot-be-targeted, and non-public shifted-stack exclusions.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Briefs 1-2.
Do not integrate into `engine.py` yet except importing helpers in tests if needed.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/targeting.py`
* **Line Range:** `After candidate resolution helpers`
* **Snippet:**
```text
No central TargetSelectionAvailability equivalent exists.
Ward/cannot-be-targeted checks are split between engine and pending_effects.
Brief 1 already excludes cards with stack_parent_id in is_card_target_candidate(); this brief must preserve that behavior and ensure availability/protection filtering also excludes non-public shifted-stack cards.
```

Current scattered checks:

```python
# lorcana_bot/engine.py
if who != player and self.has_keyword(state, cid, KEYWORD_WARD):
    continue
if check_cannot_be_targeted(state, cid, source):
    continue
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
@dataclass(frozen=True, slots=True)
class TargetSelectionAvailability:
    candidate_count: int
    card_candidate_count: int
    player_candidate_count: int
    min_selections: int
    max_selections: int
    can_satisfy_required_selection: bool
    requires_explicit_target_selection: bool
    should_auto_reject_for_no_valid_targets: bool


def analyze_target_selection_availability(...) -> TargetSelectionAvailability: ...
def apply_target_protections(
    state: GameState,
    engine: GameEngine,
    candidates: tuple[TargetCandidate, ...],
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[TargetCandidate, ...]: ...
```

Protection behavior:

```text
Opposing Ward cards cannot be chosen by opponent effects.
check_cannot_be_targeted() restrictions exclude illegal card candidates.
Cards in ZONE_UNDER or with stack_parent_id are not public play candidates.
Cards not in allowed zones are excluded.
Duplicate target IDs are rejected unless descriptor explicitly allows duplicates.
min_count/max_count drive availability; max_count=None means all/unbounded candidates.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add availability dataclass and analysis function.
* **Delta Description:** Add protection filtering to candidate resolution.
* **Delta Description:** Add tests for Ward, cannot-be-targeted, `ZONE_UNDER`, min/max, empty required selections, and duplicate rejection.
* **Delta Description:** Do not move legal-action integration into this brief; engine usage starts in Brief 4.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts`
* **Line Range:** `Lines 28-71`
* **Logic Context:**
```typescript
export type TargetSelectionAvailability = {
  candidateCount: number;
  cardCandidateCount: number;
  playerCandidateCount: number;
  minSelections: number;
  maxSelections: number;
  canSatisfyRequiredSelection: boolean;
  requiresExplicitTargetSelection: boolean;
};
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
```

Expected:
- Ward and cannot-be-targeted protections are centralized.
- Cards under shifted stacks are not candidates.
- Availability tests pass.
- Existing Brief 1 and Brief 2 targeting tests still pass without weakening assertions.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Protection rules implemented.
3. Availability fields implemented.
4. Tests added.
5. Exact pytest commands run and results.

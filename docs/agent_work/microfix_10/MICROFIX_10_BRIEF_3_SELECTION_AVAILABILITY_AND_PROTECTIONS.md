# TECHNICAL IMPLEMENTATION BRIEF 3 — Selection Availability And Protections

Goal:
Add target availability analysis and protection rules: min/max selections, Ward, cannot-be-targeted, and non-public shifted-stack exclusions.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Briefs 1-2.
Do not integrate into `engine.py` yet except importing helpers in tests if needed.
Do not rewrite or bypass the Brief 2 candidate-resolution helpers.

Corrected Brief 2 baseline that must remain true:
```text
resolve_candidate_targets(), resolve_candidate_card_ids(), and resolve_candidate_player_ids() already exist.
self, event_source, event_target, trigger_subject, current_targets, and context_targets already route through validated card-candidate checks.
Context-derived card IDs must not be returned raw.
exclude_trigger_subject is already wired into generic candidate resolution through the current context subject.
Unknown allow_players=True selectors return no players, not both players.
Existing tests/test_targeting.py currently passes with 89 tests before Brief 3 work begins.
```

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/targeting.py`
* **Line Range:** `After candidate resolution helpers`
* **Snippet:**
```text
No central TargetSelectionAvailability equivalent exists.
Ward/cannot-be-targeted checks are split between engine and pending_effects.
Briefs 1-2 already exclude cards with stack_parent_id and ZONE_UNDER through candidate validation; this brief must preserve that behavior and ensure protection filtering never reintroduces non-public shifted-stack cards.
Brief 2 already validates context selectors; this brief adds protection and availability analysis on top of those candidates instead of adding new raw context-target paths.
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
    allows_explicit_empty_target_selection: bool
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
    *,
    source_id: int | None = None,
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
`allow_duplicate_targets=True` allows duplicate candidate slots and can satisfy multi-target minimums with one legal candidate.
Chosen selectors require explicit target selection even when `min_count=0`; empty "up to" selections carry `allows_explicit_empty_target_selection=True`.
Protections preserve TargetCandidate kind/id/controller/zone values for candidates that remain legal.
Protection filtering must operate on candidate tuples returned by Brief 2 helpers; do not re-resolve context selectors by reading raw IDs directly.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add availability dataclass and analysis function.
* **Delta Description:** Add protection filtering to candidate resolution.
* **Delta Description:** Add tests for Ward, cannot-be-targeted, `ZONE_UNDER`, min/max, empty required selections, duplicate rejection, and context-derived candidates staying validated after protection filtering.
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
python3 -m py_compile lorcana_bot/targeting.py
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_state_invariants.py -q
python3 -m pytest -q
git diff --check
```

Expected:
- Ward and cannot-be-targeted protections are centralized.
- Cards under shifted stacks are not candidates.
- Context selectors remain validated and do not bypass protections.
- Unknown `allow_players=True` selectors still return no players.
- Availability tests pass.
- Existing Brief 1 and Brief 2 targeting tests still pass without weakening assertions.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Protection rules implemented.
3. Availability fields implemented.
4. Tests added.
5. Exact pytest commands run and results.

# TECHNICAL IMPLEMENTATION BRIEF 5 — Pending Targeting Integration

Goal:
Integrate the Microfix 10 targeting service into pending `target`, `multi_target`, and target-style `opponent_choice` requirements.

This brief depends on Briefs 1-4. Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before editing.

Do not recreate action-card legal-action targeting from Brief 4.
Do not implement slotted targets in this brief.
Do not rewrite `EffectResolver` in this brief except for the minimal pending chosen-player continuation described below.
Do not put player IDs in `Action.target`.
Do not store player IDs in `PendingEffect.selected_targets`; that field is for card instance IDs only.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/pending_effects.py`
* **Line Range:** `TargetRequirement / get_valid_targets_for_requirement() / resolve_target_selection()`
* **Current Context:**
```python
@dataclass(slots=True)
class TargetRequirement:
    """Describes a required target for a pending effect."""
    kind: str
    min_targets: int = 1
    max_targets: int = 1
    optional: bool = False
    card_type: str | None = None
    must_be_damaged: bool = False
    must_be_exerted: bool = False
    owner_filter: str | None = None


@dataclass(slots=True)
class PendingEffect:
    ...
    required_targets: tuple[TargetRequirement, ...] = ()
    selected_targets: tuple[int, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
```

Current `get_valid_targets_for_requirement()` manually searches play zones, manually checks card type/damage/exerted, and manually applies Ward. That duplicates the targeting service and does not support all target descriptor aliases from Microfix 10.

Current target resolvers only support card targets:
```python
def resolve_target_selection(
    state: GameState,
    pending_id: str,
    targets: tuple[int, ...],
    *,
    engine: GameEngine | None = None,
) -> None:
    _validate_targets(state, pe, targets)
    pe.selected_targets = targets
    pe.raw.setdefault("resolution_input", {})["targets"] = targets
```

* **File Path:** `lorcana_bot/engine.py`
* **Line Range:** `legal_actions()` pending requirement branches and `_apply_resolve_pending_effect()`
* **Current Context:**
```python
elif requirement_kind == "target":
    candidate_ids = (
        (pe.raw or {}).get("candidate_ids")
        or getattr(raw_requirement, "candidate_ids", None)
        or []
    )
    if candidate_ids:
        for target_id in candidate_ids:
            actions.append(Action(
                ACTION_RESOLVE_PENDING_EFFECT,
                actor=player,
                source=pe.source_id,
                target=target_id,
                choice={"pending_effect_id": pe.id, "targets": (target_id,)}
            ))
    elif requirement is not None:
        valid_targets = get_valid_targets_for_requirement(state, requirement, player, self)
        for target in valid_targets:
            actions.append(Action(
                ACTION_RESOLVE_PENDING_EFFECT,
                actor=player,
                source=pe.source_id,
                target=target,
                choice={"pending_effect_id": pe.id, "targets": (target,)}
            ))
```

Current gaps:
```text
1. Pending target enumeration does not use TargetDescriptor/TargetCandidate.
2. Raw candidate_ids bypass Ward, ZONE_UNDER, stack child, card type, and descriptor filtering.
3. chosen_item, chosen_location, chosen_damaged_character, chosen_player, and descriptor-dict pending targets are not handled consistently.
4. target-style opponent_choice uses raw candidate_ids instead of the targeting service.
5. Player targets need a separate storage path from card targets.
6. Unknown target descriptors must fail closed instead of falling back to broad board targeting.
```

---

### 2. Expected Code (The Solution)

* **Target State:**

Use `lorcana_bot.targeting` as the only pending target candidate resolver.

Add centralized helper functions in `lorcana_bot/pending_effects.py`. Exact helper names may vary, but the behavior must match this target:
```python
def target_descriptor_from_requirement(requirement: TargetRequirement | None) -> TargetDescriptor | None:
    ...


def pending_target_descriptors(pe: PendingEffect) -> tuple[TargetDescriptor, ...]:
    ...


def get_valid_target_candidates_for_pending(
    state: GameState,
    pe: PendingEffect,
    chooser_id: int,
    engine: GameEngine,
) -> tuple[TargetCandidate, ...]:
    ...
```

Descriptor source precedence must be explicit:
```text
1. pe.raw["target_descriptor"]
2. pe.raw["target_dsl"]
3. pe.raw["target"]
4. pe.raw["selector"]
5. pe.raw["requirement"] if descriptor-like
6. pe.current_requirement / TargetRequirement fallback
7. raw_requirement.kind / raw_requirement.target / raw_requirement.selector only if present and descriptor-like
```

Do not infer unknown strings into broad default descriptors. If no descriptor can be normalized, return no targeting-service candidates and rely only on an explicit `TargetRequirement` fallback when it is known.

`TargetRequirement` conversion must be deterministic:
```python
kind_map = {
    "chosen_card": "chosen_card",
    "chosen_character": "chosen_character",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_player": "chosen_player",
}
```

When converting a `TargetRequirement`, preserve:
```text
min_targets -> TargetDescriptor.min_count
max_targets -> TargetDescriptor.max_count
card_type -> TargetDescriptor.card_types
must_be_damaged -> {"type": "damaged"} filter
must_be_exerted -> {"type": "exerted"} filter
owner_filter == "opponent" -> controller="opponent"
owner_filter == "controller" -> controller="you"
optional=True -> min_count=0 unless raw min explicitly overrides it
```

Candidate narrowing rules:
```text
1. Resolve candidates through resolve_candidate_targets().
2. Apply apply_target_protections().
3. Narrow card candidates by raw candidate_ids, card_candidate_ids, or target_candidate_ids if present.
4. Narrow player candidates by raw player_candidate_ids or player_candidates if present.
5. candidate_ids are card IDs only; never treat them as player IDs.
6. Unknown descriptors or unsupported target shapes produce no candidates.
```

Pending legal action encoding must be exact:
```python
# Card target
Action(
    ACTION_RESOLVE_PENDING_EFFECT,
    actor=player,
    source=pe.source_id,
    target=card_id,
    choice={"pending_effect_id": pe.id, "targets": (card_id,)},
)

# Player target
Action(
    ACTION_RESOLVE_PENDING_EFFECT,
    actor=player,
    source=pe.source_id,
    target=None,
    choice={
        "pending_effect_id": pe.id,
        "target_kind": "player",
        "player_targets": (player_id,),
        "player": player_id,
    },
)

# Multi-card target
Action(
    ACTION_RESOLVE_PENDING_EFFECT,
    actor=player,
    source=pe.source_id,
    target=combo[0] if combo else None,
    choice={"pending_effect_id": pe.id, "targets": combo},
)
```

Do not emit a no-target pending action for a mandatory explicit target with no valid candidates.
If `allows_explicit_empty_target_selection` is already available and `min_count == 0`, an explicit empty target action may be emitted. If this becomes complicated, fail closed and leave explicit empty target selection to the slotted-target brief.

Player-target storage must be separate from card-target storage. Implement one of these two approaches:
```python
@dataclass(slots=True)
class PendingEffect:
    ...
    selected_player_targets: tuple[int, ...] = ()
```

or:
```python
pe.raw.setdefault("resolution_input", {})["player_targets"] = player_targets
pe.raw["selected_player_targets"] = player_targets
```

Required behavior either way:
```text
Card targets:
- validate against state.cards
- store in pe.selected_targets
- store in pe.raw["resolution_input"]["targets"]
- continue effects with EffectResolutionContext.target/current_targets

Player targets:
- validate player IDs are legal player IDs, currently 0 or 1
- do not store in pe.selected_targets
- store in pe.raw["resolution_input"]["player_targets"]
- continue chosen-player effects with EffectResolutionContext.choice set to the selected player ID
- keep EffectResolutionContext.target as None for player-only selections
```

`opponent_choice` with `choice_type` `"target"` or `"targets"` must use the same pending-target helper and must apply the same protection and narrowing rules. Do not leave target-style `opponent_choice` on raw `candidate_ids`.

Do not change `discard_choice` in this brief. Discard-choice is hand-card selection and remains separate unless test fallout exposes a direct compatibility issue.

---

### 3. Fixes Needed

* **Action:** `EXPAND / REVISE`
* **Delta Description:** Replace the pending `target`, `multi_target`, and target-style `opponent_choice` legal-action enumeration with targeting-service candidate resolution.
* **Delta Description:** Refactor `get_valid_targets_for_requirement()` so it delegates to the targeting service instead of manual board scans, while preserving its backward-compatible `list[int]` return shape.
* **Delta Description:** Add player-target pending resolution/storage without mixing player IDs into card target fields.
* **Delta Description:** Ensure raw candidate lists narrow targeting-service candidates rather than bypassing validation and protections.
* **Delta Description:** Add regression tests that prove unknown descriptors fail closed and that Ward/ZONE_UNDER/Shift stack protections apply to pending targets.

---

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts`
* **Line Range:** `Lines 754-860`
* **Logic Context:**
```typescript
function buildGenericTargetSelectionContext(...) {
  const chooserScopedCtx = {
    ...args.ctx,
    playerId: args.chooserId,
  };
  const analysis = analyzeEffectTargets(...);
  const effectTargetRequiresSelection = effectTargetUsesSelectionContext(effectTarget);
  const runtimeCardCandidates =
    effectTarget !== undefined && effectTargetRequiresSelection
      ? resolveCandidateTargets(...)
      : analysis.cardCandidates;
  const runtimePlayerCandidates =
    effectTarget !== undefined && effectTargetRequiresSelection
      ? resolveTargetPlayerIds(...)
      : analysis.playerCandidates;
  const cardCandidates = [...new Set(runtimeCardCandidates)];
  const playerCandidates = [...new Set(runtimePlayerCandidates)];
  const hasCandidates = cardCandidates.length > 0 || playerCandidates.length > 0;
  if (!analysis.requiresExplicitSelection) {
    return undefined;
  }
  if (!hasCandidates && !allowEmptyResolution) {
    return undefined;
  }
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-analysis.ts`
* **Line Range:** `Lines 1799-1878`
* **Logic Context:**
```typescript
export function validateAndNormalizeTargetSelection(
  targets: unknown,
  analysis: TargetAnalysis,
  context?: TargetSelectionRestrictionContext,
): TargetValidationResult {
  const cardCandidateSet = new Set(analysis.cardCandidates);
  const playerCandidateSet = new Set(analysis.playerCandidates);
  const cardIds: CardInstanceId[] = [];
  const playerIds: PlayerId[] = [];

  for (const target of rawTargets) {
    if (!analysis.allowDuplicateTargets && seen.has(target)) {
      return { valid: false, errorCode: "DUPLICATE_TARGETS", ... };
    }
    if (cardCandidateSet.has(target as CardInstanceId)) {
      cardIds.push(target as CardInstanceId);
      continue;
    }
    if (playerCandidateSet.has(target as PlayerId)) {
      playerIds.push(target as PlayerId);
      continue;
    }
    return { valid: false, errorCode: "INVALID_ACTION_TARGET", ... };
  }
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts`
* **Line Range:** `Lines 998-1035`
* **Logic Context:**
```typescript
const rawTargets = ctx.args.params?.targets;
const cardTargets = rawTargets !== undefined
  ? Array.isArray(rawTargets)
    ? rawTargets.filter((target): target is SelectionTarget => typeof target === "string")
    : typeof rawTargets === "string"
      ? [rawTargets]
      : []
  : [];
const playerTargets: SelectionTarget[] = Array.isArray(paramsWithPlayerTargets?.playerTargets)
  ? paramsWithPlayerTargets.playerTargets.filter(
      (target): target is SelectionTarget => typeof target === "string",
    )
  : typeof paramsWithPlayerTargets?.playerTargets === "string"
    ? [paramsWithPlayerTargets.playerTargets]
    : [];
const allTargets = [...cardTargets, ...playerTargets];
if (allTargets.length > 0) {
  const nextResolutionInput = withCurrentSelectionTargets(resolutionInput, allTargets);
  Object.assign(resolutionInput, nextResolutionInput);
}
```

Authority interpretation:
```text
Lorcanito resolves card candidates and player candidates separately.
Lorcanito validates selected targets against candidate sets.
Lorcanito passes playerTargets separately from card targets, then merges them only into resolution input.
Python must therefore keep card instance IDs and player IDs separate at action encoding and pending storage boundaries.
```

---

### 5. Required Tests

Add focused tests to `tests/test_pending_effects.py` or `tests/test_targeting.py`. Use existing test builders and patterns.

Required coverage:
```text
1. get_valid_targets_for_requirement() delegates to targeting-service behavior and preserves the old list[int] API.
2. Pending target requirement for chosen_item emits only item card resolve actions.
3. Pending target requirement for chosen_location emits only location card resolve actions.
4. Pending target requirement for chosen_damaged_character emits only damaged character resolve actions.
5. Pending explicit opposing target excludes a Ward card.
6. Pending target excludes a ZONE_UNDER card and a card with stack_parent_id.
7. Raw candidate_ids narrow targeting-service card candidates; invalid/raw protected candidates are filtered out.
8. multi_target enumerates card combinations after filtering and respects min_targets/max_targets.
9. chosen_player pending emits player target actions with Action.target is None and choice["player_targets"].
10. Applying a chosen_player pending action writes pe.raw["resolution_input"]["player_targets"] and continues effect resolution with EffectResolutionContext.choice.
11. target-style opponent_choice uses the same helper and filters out protected/invalid candidates.
12. Unknown pending target descriptor emits no broad fallback target actions.
```

Do not weaken existing tests.

---

### 6. Acceptance Check(s)

Run:
```bash
python3 -m py_compile lorcana_bot/pending_effects.py lorcana_bot/engine.py lorcana_bot/targeting.py
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
git diff --check
```

Expected:
```text
All tests pass.
Pending card target legal actions use Action.target plus choice["targets"].
Pending player target legal actions use Action.target=None plus choice["player_targets"].
Raw candidate lists narrow candidate resolution instead of bypassing protections.
No player ID is stored in PendingEffect.selected_targets.
No unsupported/unknown pending target descriptor creates broad fallback target actions.
```

---

### 7. Final Response Requirements

Report:
1. Files changed.
2. New pending-target helper functions added.
3. Exact pending card-target action shape.
4. Exact pending player-target action shape.
5. Exact `resolution_input` fields written for card targets and player targets.
6. Tests added.
7. Exact pytest commands run and results.
8. Confirmation that action-card legal-action targeting from Brief 4 was not rewritten.

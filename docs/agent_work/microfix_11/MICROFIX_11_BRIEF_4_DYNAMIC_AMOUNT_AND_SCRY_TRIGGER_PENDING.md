# TECHNICAL IMPLEMENTATION BRIEF 4 - Dynamic Amount And Scry Trigger Pending

Goal:
Make trigger effects with amount requirements and scry ordering resolve through real runtime state instead of being projected as zero or reported as unsupported.

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` before starting.

This brief depends on Briefs 1-3. Do not rewrite all effect resolution. Implement only amount shapes present in current Lorcanito source cards and blocker reports.

---

### 1. Current Missing Or Incorrect Code

* **File Path:** `lorcana_bot/importers/lorcanito_source_mapper.py`
* **Line Range:** `_project_trigger_effect()`
* **Snippet:**
```python
return EffectDef(
    kind=kind,
    target=target,
    amount=int(effect.amount) if isinstance(effect.amount, (int, str)) and str(effect.amount).isdigit() else 0,
    raw=asdict(effect),
)
```

Current gaps:

```text
Dynamic/non-integer amounts are silently projected as 0.
Trigger effect amount requirements are still reported as blockers.
Scry trigger effects are reported as requiring scry_ordering even though pending scry machinery exists.
EffectResolver._amount() only returns int(effect.amount or 0) and does not inspect raw Lorcanito amount shapes, event snapshots, or pending/bag resolution input.
```

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `_amount()`
* **Snippet:**
```python
def _amount(self, effect: EffectDef) -> int:
    return int(effect.amount or 0)
```

### 2. Expected Code (The Solution)

* **Target State:**
```text
1. Trigger projection preserves raw amount information.

2. EffectResolver amount resolution supports current blocker-card amount shapes:
   - integer amounts
   - numeric string amounts
   - amount from resolution_input["amount"]
   - amount from event_snapshot where Lorcanito stores dynamic event data
   - "all" where existing effect semantics can safely determine all valid targets/cards

3. Unsupported amount shapes fail loudly in projection/report or runtime tests; they must not become amount=0 silently.

4. Triggered scry effects create a pending scry_ordering requirement through existing pending effect helpers.

5. Bag-origin scry pending effects keep origin="bag" and remove the bag entry only after pending resolution completes.

6. trigger_blocker_report no longer counts amount/scry_ordering as blockers for shapes covered by tests.
```

### 3. Fixes Needed

* **Action:** `REVISE / EXPAND`
* **Delta Description:** Replace silent dynamic amount-to-zero projection with preserved raw amount plus a runtime resolver.
* **Delta Description:** Extend `EffectResolver._amount()` or introduce an amount helper that receives `EffectResolutionContext`.
* **Delta Description:** Route scry trigger effects through existing pending scry ordering behavior.
* **Delta Description:** Add tests for current blocker examples such as Nani/Gramma Tala/Robin Hood style scry and Calhoun/Fa Zhou/Pluto style gain-lore amounts, using demo card IDs or real extracted card definitions.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/amount-resolver.ts`
* **Line Range:** `Lines 34-216`
* **Logic Context:**
```typescript
const eventSnapshot = ctx.resolutionInput?.eventSnapshot;

export function resolveAmount(amount, ctx) {
  if (typeof amount === "number") {
    return amount;
  }

  if (typeof amount === "string") {
    return resolveDynamicAmountString(amount, ctx);
  }

  if (amount && typeof amount === "object") {
    return resolveDynamicAmountObject(amount, ctx);
  }
}
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/types/domain-events.ts`
* **Line Range:** `Lines 18-73`
* **Logic Context:**
```typescript
export interface DynamicAmountEventSnapshot {
  cardsUnderCountBeforeBanish?: number;
  drawnCount?: number;
  drawCountForPlayerThisTurn?: number;
  damageDealt?: number;
  lastEffectTargetCount?: number;
  subjectCardId?: CardInstanceId;
  triggerSourceCardId?: CardInstanceId;
}
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_engine_trigger_pipeline.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_blocker_report.py -q
python3 -m pytest -q
git diff --check
```

Expected:

```text
Dynamic amounts are never silently converted to zero.
Supported amount shapes resolve to the expected integer at runtime.
Triggered scry creates and resolves a pending scry_ordering effect.
Bag entry completion waits for pending scry resolution.
Report amount/scry_ordering blockers are reduced only for supported shapes.
Full test suite passes.
```

### 6. Final Response Requirements

Report:

1. Files changed.
2. Amount shapes implemented.
3. Unsupported amount behavior.
4. Scry pending route implemented.
5. Projection/report changes.
6. Exact commands run and results.

# TECHNICAL IMPLEMENTATION BRIEF 7 — Slotted Targets

Goal:
Add Python slotted-target support for multi-slot effects such as move-damage, move-to-location, shift-and-choose, and banish-and-play.

This brief depends on Briefs 1-6.
Do not implement the full rules for those effects unless already present; this brief is about input shape, validation, flattening, and pending/automation preservation.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/targeting.py`
* **Line Range:** `Slotted target support missing`
* **Snippet:**
```text
There is no Python equivalent for Lorcanito SlottedTargetInput.
Pending resolution input only carries flat targets.
Automation only round-trips flat targets.
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
SLOTTED_TARGET_KINDS = (
    "move-damage",
    "move-to-location",
    "shift-and-choose",
    "banish-and-play",
)

SLOTTED_TARGET_SLOT_KEYS = {
    "move-damage": ("from", "to"),
    "move-to-location": ("subject", "location"),
    "shift-and-choose": ("chosenCard",),
    "banish-and-play": ("banish", "play"),
}

def is_slotted_target_input(value: Any) -> bool: ...
def flatten_slotted_targets(value: dict[str, Any]) -> tuple[int, ...]: ...
def validate_slotted_targets(state, value, descriptor_by_slot=None) -> None: ...
```

Integration:

```text
pending_effects stores raw["resolution_input"]["slotted_targets"].
engine._apply_resolve_pending_effect() can accept choice["slotted_targets"] for target/multi_target requirements.
automation candidates preserve slotted_targets in metadata and move_adapter writes it back.
flat targets remain supported.
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add slotted target helpers to `targeting.py`.
* **Delta Description:** Add pending apply support for `slotted_targets`.
* **Delta Description:** Add automation round-trip support.
* **Delta Description:** Add tests for each slotted kind and flattening order.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/slotted-targets.ts`
* **Line Range:** `Lines 15-43 and 87-102`
* **Logic Context:**
```typescript
export type SlottedTargetInput =
  | { kind: "move-damage"; from: ...; to: ... }
  | { kind: "move-to-location"; subject: ...; location: ... }
  | { kind: "shift-and-choose"; chosenCard: ... }
  | { kind: "banish-and-play"; banish: ...; play: ... };

export function flattenSlottedTargets(...)
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_automation_pending_effects.py -q
python3 -m pytest -q
```

Expected:
- Slotted target helper tests pass.
- Pending and automation preserve `slotted_targets`.
- Flat target paths remain unchanged.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Slotted target kinds supported.
3. Pending/automation fields added.
4. Tests added.
5. Exact pytest commands run and results.

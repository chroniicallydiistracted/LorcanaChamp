# TECHNICAL IMPLEMENTATION BRIEF 2 — Harden Active Source Guards In Static And Replacement Registries

Goal:
Make static and replacement registries reject duplicate source entries and treat only public `ZONE_PLAY` cards with no `stack_parent_id` as active effect sources.

Do not change engine movement in this brief.
Do not change parsing behavior in this brief.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/static_effects.py`
* **Line Range:** Around `StaticEffectRegistry.register_effect()` and `StaticEffectEntry.applies_to()`
* **Snippet:**
```python
def register_effect(self, entry: StaticEffectEntry) -> None:
    """Add a static effect to the registry."""
    self.effects.append(entry)
```

```python
source_inst = state.cards.get(self.source_id)
if source_inst is None or source_inst.zone != "play":
    return False
```

* **File Path:** `lorcana_bot/replacement_effects.py`
* **Line Range:** Around `ReplacementEffectRegistry.register_effect()` and `_applies_to()`
* **Snippet:**
```python
def register_effect(self, entry: ReplacementEffectEntry) -> None:
    """Add a replacement effect to the registry."""
    self.effects.append(entry)
```

```python
source_inst = state.cards.get(effect.source_id)
if source_inst is None or source_inst.zone != "play":
    return False
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
def _is_active_public_source(state: GameState, source_id: int) -> bool:
    from .constants import ZONE_PLAY

    source_inst = state.cards.get(source_id)
    return (
        source_inst is not None
        and source_inst.zone == ZONE_PLAY
        and source_inst.stack_parent_id is None
    )
```

Use the helper in both static and replacement applicability checks.

Update registry registration to avoid duplicate entries for the same source and same effect identity:
```python
def register_effect(self, entry: StaticEffectEntry) -> None:
    if entry not in self.effects:
        self.effects.append(entry)
```

```python
def register_effect(self, entry: ReplacementEffectEntry) -> None:
    if entry not in self.effects:
        self.effects.append(entry)
```

### 3. Fixes Needed

* **Action:** `REVISE`
* **Delta Description:** Replace string literal `"play"` source checks with an explicit public-source guard using `ZONE_PLAY` and `stack_parent_id is None`.
* **Delta Description:** Make registry registration idempotent so repeated lifecycle registration does not duplicate active effects.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts`
* **Logic Context:** Static effects are active only from live public sources.

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/state/shift-stack.ts`
* **Logic Context:** Cards under a shifted top are removed from public play and stored as stack metadata.

### 5. Acceptance Check(s)

Add tests proving:
- duplicate registration of the same parsed static effect does not create duplicates.
- duplicate registration of the same parsed replacement effect does not create duplicates.
- a static source in `ZONE_UNDER` gives no modifiers/restrictions.
- a replacement source in `ZONE_UNDER` does not prevent damage or replace banish.

Run:
```bash
python3 -m pytest tests/test_static_effects.py -q
python3 -m pytest tests/test_replacement_effects.py -q
```

### 6. Final Response Requirements

Report:
1. Files changed.
2. The exact helper or guard added for public active sources.
3. The idempotent registration behavior.
4. Exact pytest commands run and results.

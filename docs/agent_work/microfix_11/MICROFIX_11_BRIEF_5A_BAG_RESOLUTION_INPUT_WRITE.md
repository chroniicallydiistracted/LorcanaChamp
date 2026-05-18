# TECHNICAL IMPLEMENTATION BRIEF 5A - Bag Resolution Input Write

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Make `ACTION_RESOLVE_BAG` persist player-provided intermediate input on `BagEffectEntry.resolution_input` before bag effect execution starts.

This brief writes input only. Brief 5B handles pending-effect continuation and final bag removal.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/engine.py
tests/test_bag_resolution.py
```

---

## Current Python Logic To Inspect

Inspect these exact locations before editing:

```text
lorcana_bot/engine.py::GameEngine._apply_resolve_bag
lorcana_bot/state.py::BagEffectEntry
lorcana_bot/constants.py::ACTION_RESOLVE_BAG
tests/test_bag_resolution.py
```

Current expected shape:

```python
@dataclass
class BagEffectEntry:
    id: str
    player_id: int
    source_id: int | None
    ability_id: str | None
    effects: tuple[EffectDef, ...]
    controller_id: int
    event: PendingTriggeredEvent | None = None
    optional: bool = False
    condition: Any | None = None
    resolution_input: dict[str, Any] = field(default_factory=dict)
```

`Action.choice` is the only field that may contain the intermediate player input for this brief.

---

## Exact Required Runtime Changes

### 1. Add This Helper To `GameEngine`

Add this private method near `_apply_resolve_bag()` in `lorcana_bot/engine.py`.

```python
def _merge_bag_resolution_input(self, entry: BagEffectEntry, choice: dict[str, Any]) -> None:
    key_map = {
        "amount": "amount",
        "targets": "targets",
        "player_targets": "player_targets",
        "slotted_targets": "slotted_targets",
        "choice_index": "choice_index",
        "resolve_optional": "resolve_optional",
        "named_card": "named_card",
        "destinations": "destinations",
        "enter_play_exerted": "enter_play_exerted",
    }
    for choice_key, input_key in key_map.items():
        if choice_key in choice:
            entry.resolution_input[input_key] = choice[choice_key]
```

Do not add `bag_id` to `resolution_input`.
Do not add `accept` to `resolution_input`.
Do not rename `destinations` to `destination`.

### 2. Call The Helper From `_apply_resolve_bag()`

In `GameEngine._apply_resolve_bag()`:

1. Keep the existing lookup of the bag entry.
2. Keep the existing `accept is False` decline/removal behavior.
3. After the decline branch has returned or been bypassed, call:

```python
self._merge_bag_resolution_input(entry, action.choice)
```

The call must happen before:

```python
event_payload = {}
```

or before any effect resolution call if the local code has moved.

Do not remove the bag entry merely because input was written.
Do not short-circuit effect resolution merely because input was written.
Do not change `_apply_resolve_pending_effect()` in this brief.

---

## Lorcanito Source Reference

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/resolve-bag.ts`
* **Logic Context:**

```typescript
const updatedResolutionInput = {
  ...bagItem.resolutionInput,
  ...resolutionInput,
};
```

Lorcanito preserves partial player input on the bag item and resumes resolution using the accumulated input. This Python brief implements the equivalent input accumulation on `BagEffectEntry.resolution_input`.

---

## Exact Required Tests

Add these tests to `tests/test_bag_resolution.py`.

```text
tests/test_bag_resolution.py::test_resolve_bag_amount_input_persists_resolution_input
tests/test_bag_resolution.py::test_resolve_bag_target_input_persists_resolution_input
tests/test_bag_resolution.py::test_resolve_bag_named_card_input_persists_resolution_input
tests/test_bag_resolution.py::test_resolve_bag_does_not_copy_bag_id_or_accept_to_resolution_input
tests/test_bag_resolution.py::test_resolve_bag_decline_still_removes_optional_entry
```

Test construction requirements:

```text
1. Use real demo card definitions from the repository test helpers. Do not invent card_def_id values absent from the demo database.
2. Use a bag effect that creates a pending effect, such as an existing scry/search pending route, so the bag entry remains inspectable after ACTION_RESOLVE_BAG.
3. Assert the existing BagEffectEntry object has the expected resolution_input keys after apply_action().
4. Assert accept=False still removes the optional bag entry and does not create a pending effect.
```

For the first three tests, the assertion pattern must be:

```python
engine.apply_action(state, Action(ACTION_RESOLVE_BAG, actor=0, choice={"bag_id": bag_id, "amount": 2}))
assert entry.resolution_input["amount"] == 2
```

Use the equivalent `targets` and `named_card` keys in the target and named-card tests.

---

## Forbidden Changes

Do not edit `lorcana_bot/pending_effects.py`.

Do not edit `_apply_resolve_pending_effect()`.

Do not edit projector or report files.

Do not add broad legal action enumeration.

Do not change trigger blocker taxonomy.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report:

```text
1. Files changed.
2. Exact resolution_input keys supported.
3. Confirmation that bag_id and accept are not copied into resolution_input.
4. Decline behavior result.
5. Exact tests added.
6. Exact command results.
7. Five yes/no self-audit answers from MICROFIX_11_SHARED_RULES.md.
```

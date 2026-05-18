# TECHNICAL IMPLEMENTATION BRIEF 4B - Triggered Scry Pending

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Ensure triggered scry effects suspend into existing pending scry ordering and resume through bag completion.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/effects.py
lorcana_bot/engine.py
lorcana_bot/pending_effects.py
tests/test_pending_effects.py
tests/test_bag_resolution.py
tests/test_engine_trigger_pipeline.py
```

Do not edit projector/report files.

---

## Exact Required Runtime Changes

Use existing pending helpers. Do not create a second scry system.

Required behavior:

```text
1. Resolving a bag-origin triggered scry effect creates a pending effect with requirement_kind == "scry_ordering".
2. The pending effect raw data includes:
   origin == "bag"
   origin_id == bag_id
   resolution_input copied from the bag entry
3. The bag item remains in state.bag while the pending effect is unresolved.
4. Resolving the pending scry effect removes exactly one matching bag item.
5. Deck order changes according to resolved top/bottom ordering.
```

If this behavior already exists, do not rewrite it. Add tests proving it.

---

## Exact Required Tests

Add tests:

```text
tests/test_bag_resolution.py::test_triggered_scry_creates_bag_origin_pending_effect
tests/test_bag_resolution.py::test_resolving_bag_origin_scry_pending_removes_bag_item_once
tests/test_pending_effects.py::test_bag_origin_scry_pending_preserves_resolution_input
```

---

## Forbidden Changes

Do not implement new amount resolver logic here.

Do not update report support.

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_bag_resolution.py tests/test_pending_effects.py tests/test_engine_trigger_pipeline.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report whether code changed or tests proved existing behavior, exact tests added, command results, and five yes/no self-audit answers.

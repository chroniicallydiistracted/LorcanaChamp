# TECHNICAL IMPLEMENTATION BRIEF 4A - Amount Resolver Foundation

Read `docs/agent_work/microfix_11/MICROFIX_11_SHARED_RULES.md` first.

Goal:
Stop silent `amount=0` behavior by adding a runtime amount resolver for known safe amount shapes. No report updates in this brief.

---

## Allowed Files

You may edit only:

```text
lorcana_bot/effects.py
tests/test_effects.py
```

---

## Exact Required Runtime Changes

Modify amount handling in `lorcana_bot/effects.py`.

Replace this behavior:

```python
def _amount(self, effect: EffectDef) -> int:
    return int(effect.amount or 0)
```

with a resolver that can inspect:

```text
EffectDef.amount
EffectDef.raw["amount"]
EffectResolutionContext.resolution_input["amount"] if available
EffectResolutionContext.event_snapshot values if available
```

If the existing `EffectResolutionContext` does not expose `resolution_input` or `event_snapshot`, inspect its current fields and use the existing field where bag/pending resolution input is stored. Do not invent a parallel context object.

Supported amount shapes:

```text
integer
numeric string
{"type": "static", "amount": N}
{"type": "event-snapshot", "key": "drawnCount"}
{"type": "event-snapshot", "key": "cardsUnderCountBeforeBanish"}
```

Unsupported amount shapes must raise a clear exception. They must not return 0.

Update these internal calls from `_amount(effect)` to `_amount(effect, context)`:

```text
_resolve_draw
_resolve_gain_lore
_resolve_lose_lore
_resolve_deal_damage
_resolve_remove_damage
_resolve_scry
every other resolver in `lorcana_bot/effects.py` currently calling `_amount(effect)`
```

---

## Exact Required Tests

Add tests:

```text
tests/test_effects.py::test_amount_resolver_integer
tests/test_effects.py::test_amount_resolver_numeric_string_from_raw
tests/test_effects.py::test_amount_resolver_static_object
tests/test_effects.py::test_amount_resolver_event_snapshot_key
tests/test_effects.py::test_amount_resolver_unsupported_shape_raises
```

---

## Forbidden Changes

Do not edit `lorcanito_source_mapper.py`.

Do not edit `trigger_blocker_report.py`.

Do not convert unsupported amount shapes to 0.

---

## Lorcanito Source Reference

```text
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/amount-resolver.ts
```

---

## Acceptance Checks

Run:

```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest -q
git diff --check
```

---

## Final Response Requirements

Report amount shapes implemented, unsupported-shape behavior, tests added, command results, and five yes/no self-audit answers.

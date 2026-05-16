# TECHNICAL IMPLEMENTATION BRIEF 1 — EffectResolver Mutation Audit Guard

Goal:
Add a focused regression test that prevents `lorcana_bot/effects.py` from reintroducing direct gameplay mutation. Microfix 8 is about forcing effect resolution through engine-owned event boundaries.

Do not modify `engine.py` in this brief.
Do not change effect behavior in this brief unless the audit test exposes a direct mutation that already violates the allowed list below.

---

### 1. Current Risk Area

* **File Path:** `lorcana_bot/effects.py`
* **Line Range:** `Lines 43-129 and 564-645`
* **Snippet:**
```python
elif kind == "draw":
    self.engine.draw_cards(state, self._target_player(state, effect, context), self._amount(effect))
elif kind == "gain_lore":
    self.engine._gain_lore_eventful(
        state,
        self._target_player(state, effect, context),
        self._amount(effect),
        source_id=context.source,
    )
elif kind == "lose_lore":
    self.engine._lose_lore_eventful(
        state,
        self._target_player(state, effect, context),
        self._amount(effect),
        source_id=context.source,
    )
elif kind == "deal_damage":
    for target in self._target_cards(state, effect, context):
        self.engine._deal_damage_eventful(
            state,
            target_id=target,
            source_id=context.source,
            amount=self._amount(effect),
            actor=context.actor,
            is_challenge=False,
            apply_resist=True,
        )
elif kind == "remove_damage":
    for target in self._target_cards(state, effect, context):
        self.engine._remove_damage_eventful(
            state,
            target,
            self._amount(effect),
            actor=context.actor,
            source_id=context.source,
        )
elif kind == "banish":
    for target in self._target_cards(state, effect, context):
        self.engine._banish_eventful(
            state,
            target,
            actor=context.actor,
            source_id=context.source,
            reason="effect",
        )
```

```python
if card_id in state.cards:
    self.engine._move_card_eventful(
        state,
        card_id,
        ZONE_HAND,
        actor=context.actor,
        source_id=context.source,
        controller=state.cards[card_id].owner,
        event_type="CARD_MOVED_TO_HAND",
        payload={"player": state.cards[card_id].owner},
    )
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
def test_effect_resolver_does_not_directly_mutate_gameplay_state():
    source = Path("lorcana_bot/effects.py").read_text()

    forbidden_patterns = {
        "state.move_card(": "zone movement must go through GameEngine._move_card_eventful or a more specific helper",
        ".lore +=": "lore gain must go through GameEngine._gain_lore_eventful",
        ".lore -=": "lore loss must go through GameEngine._lose_lore_eventful",
        ".damage +=": "damage must go through GameEngine._deal_damage_eventful",
        ".damage -=": "damage removal must go through GameEngine._remove_damage_eventful",
        ".exerted = True": "exertion must go through GameEngine._exert_eventful",
        ".exerted = False": "readying must go through GameEngine._ready_eventful unless it is in an engine helper",
        "state.event_log.append(": "events must go through GameEngine.emit_event",
        "GameEvent(": "events must go through GameEngine.emit_event",
    }

    violations = {
        pattern: reason
        for pattern, reason in forbidden_patterns.items()
        if pattern in source
    }
    assert violations == {}
```

The test may live in `tests/test_effects.py` or a new `tests/test_effect_resolver_boundaries.py`. If a new file is created, it must be included by normal pytest discovery.

Allowed resolver-local mutations:

```text
state.players[context.actor].cost_reductions.append(...)
state.cards[target].temporary_keywords.append(...)
state.cards[target].temporary_modifiers[...] = ...
state.cards[cid].revealed = True
state.shuffle_counter += 1
rng.shuffle(state.players[player].deck)
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add an automated guard test that scans `lorcana_bot/effects.py` for direct gameplay mutation patterns. The guard must fail if future code bypasses engine-owned helpers for card movement, lore, damage, exert/ready, or event emission.
* **Delta Description:** Do not forbid temporary effect state, reveal flags, or deterministic shuffle metadata in this brief.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/composed-effect-resolver.ts`
* **Line Range:** `Lines 1-80`
* **Logic Context:**
```typescript
import type {
  ActionEffectResolutionOptions,
  ActionResolutionInput,
  ActionResolutionResult,
  PlayCardExecutionContext,
} from "./types";
```

Lorcanito composes effect resolvers over a runtime context. Rule-significant mutation is performed through framework zones, cards, events, and specialized effect modules rather than arbitrary direct state writes in a catch-all resolver.

### 5. Acceptance Check(s)

Run:
```bash
rg -n "state\\.move_card\\(|\\.lore \\+=|\\.lore -=|\\.damage \\+=|\\.damage -=|\\.exerted = True|\\.exerted = False|state\\.event_log\\.append\\(|GameEvent\\(" lorcana_bot/effects.py
python3 -m pytest tests/test_effects.py -q
python3 -m pytest -q
```

Expected:
- The search command returns no prohibited direct gameplay mutation in `lorcana_bot/effects.py`.
- The new guard test passes.
- Existing effect tests pass.
- Full suite passes.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Exact guard patterns added.
3. Any allowed resolver-local mutations deliberately excluded from the guard.
4. Exact pytest commands run and results.
5. Confirmation that `engine.py` was not modified.

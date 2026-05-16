# TECHNICAL IMPLEMENTATION BRIEF 4 — Add Engine-Path Tests for Special Pending Requirements

Goal:
Add tests proving special pending requirements work through real `GameEngine.legal_actions()` and `GameEngine.apply_action()`, not only helper functions.

Do not modify production code unless a test exposes a small defect from Briefs 1–3.

---

### 1. Current Incorrect Code

* **File Path:** `tests/test_pending_effects.py`
* **Line Range:** `Lines 1-18`
* **Snippet:**
```python
"""Tests for pending effect layer and target choice prompts."""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase
from lorcana_bot.pending_effects import (
    PendingEffect,
    TargetRequirement,
    create_pending_effect,
    get_current_pending_effect,
    get_pending_effects_for_chooser,
    get_valid_targets_for_requirement,
    resolve_pending_effect_optional,
    complete_pending_effect,
    has_pending_effects,
    get_pending_effect_by_id,
)
from lorcana_bot.constants import (
    ACTION_RESOLVE_PENDING_EFFECT,
    ZONE_PLAY,
)
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
"""Tests for pending effect layer and target choice prompts."""

import pytest

from lorcana_bot.engine import GameEngine
from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.state import Action, CardInstance, GameState, PlayerState
from lorcana_bot.pending_effects import (
    PendingEffect,
    TargetRequirement,
    NamedCardRequirement,
    create_pending_effect,
    create_scry_pending_effect,
    create_search_pending_effect,
    create_reveal_routing_pending_effect,
    get_current_pending_effect,
    get_pending_effects_for_chooser,
    get_valid_targets_for_requirement,
    resolve_pending_effect_optional,
    complete_pending_effect,
    has_pending_effects,
    get_pending_effect_by_id,
)
from lorcana_bot.constants import (
    ACTION_RESOLVE_PENDING_EFFECT,
    ZONE_DECK,
    ZONE_HAND,
    ZONE_PLAY,
)
```

Add the following tests at the end of `tests/test_pending_effects.py`:

```python
class TestSpecialPendingRequirementEngineRouting:
    """Engine-path tests for special pending requirement_kind dispatch."""

    def _engine(self) -> GameEngine:
        cards = [
            CardDef("a", "A", "amber", 1, True, "character", 1, 1, 1),
            CardDef("b", "B", "amber", 1, True, "character", 1, 1, 1),
            CardDef("c", "C", "amber", 1, True, "character", 1, 1, 1),
        ]
        return GameEngine(CardDatabase(cards))

    def _state_with_deck(self) -> GameState:
        state = GameState(players=[PlayerState(), PlayerState()], cards={})
        state.cards[1] = CardInstance(instance_id=1, card_id="a", owner=0, controller=0, zone=ZONE_DECK)
        state.cards[2] = CardInstance(instance_id=2, card_id="b", owner=0, controller=0, zone=ZONE_DECK)
        state.cards[3] = CardInstance(instance_id=3, card_id="c", owner=0, controller=0, zone=ZONE_DECK)
        state.players[0].deck = [1, 2, 3]
        state.active_player = 0
        return state

    def test_scry_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_scry_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            amount=2,
        )

        actions = engine.legal_actions(state, 0)
        resolve_actions = [a for a in actions if a.kind == ACTION_RESOLVE_PENDING_EFFECT]
        assert any(a.choice.get("top_cards") == (1, 2) for a in resolve_actions)

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={
                "pending_effect_id": pe.id,
                "top_cards": (2,),
                "bottom_cards": (1,),
            },
        )
        next_state = engine.apply_action(state, action)

        assert next_state.players[0].deck == [2, 3, 1]
        assert next_state.pending_effects == []

    def test_search_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_search_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            candidate_ids=(1, 2),
            destination=ZONE_HAND,
            shuffle_after=False,
        )

        actions = engine.legal_actions(state, 0)
        assert any(
            a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("selected_card_id") == 2
            for a in actions
        )

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pe.id, "selected_card_id": 2},
        )
        next_state = engine.apply_action(state, action)

        assert 2 in next_state.players[0].hand
        assert 2 not in next_state.players[0].deck
        assert next_state.pending_effects == []

    def test_reveal_routing_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pe = create_reveal_routing_pending_effect(
            state,
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            card_ids=(1,),
            destination=None,
            destination_options=(ZONE_HAND, ZONE_DECK),
        )

        actions = engine.legal_actions(state, 0)
        assert any(
            a.kind == ACTION_RESOLVE_PENDING_EFFECT
            and a.choice.get("destination") == ZONE_HAND
            for a in actions
        )

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pe.id, "destination": ZONE_HAND},
        )
        next_state = engine.apply_action(state, action)

        assert next_state.cards[1].revealed is True
        assert 1 in next_state.players[0].hand
        assert next_state.pending_effects == []

    def test_named_card_pending_requirement_resolves_through_engine_action(self):
        engine = self._engine()
        state = self._state_with_deck()

        pending = PendingEffect(
            id="pe_named",
            controller_id=0,
            chooser_id=0,
            source_id=None,
            source_card_id=None,
            effects=(),
            choice_options=("a", "b"),
            raw={
                "requirement_kind": "named_card",
                "requirement": NamedCardRequirement(valid_card_def_ids=("a", "b"), chooser_id=0),
            },
        )
        state.pending_effects.append(pending)

        actions = engine.legal_actions(state, 0)
        assert any(a.choice.get("named_card") == "b" for a in actions)

        action = Action(
            ACTION_RESOLVE_PENDING_EFFECT,
            actor=0,
            choice={"pending_effect_id": pending.id, "named_card": "b"},
        )
        next_state = engine.apply_action(state, action)

        assert next_state.pending_effects == []
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add engine-path tests that construct special pending requirements, confirm `legal_actions()` exposes concrete resolution choices, and resolve them through `apply_action()`. These tests must prove the special dispatch branch works and removes completed pending effects.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Pending action effect tests and execution sections`
* **Logic Context:**
```typescript
// Tests resolve pending action effects through public runtime moves rather than
// calling only helper functions.
ctx.moves.resolvePendingAction({
  pendingEffectId,
  resolutionInput,
});
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Expected:
- New scry engine-path test passes.
- New search engine-path test passes.
- New reveal-routing engine-path test passes.
- New named-card engine-path test passes.
- Existing pending tests still pass.

### 6. Final Response Requirements

The implementation agent must report:
1. Files changed.
2. Tests added.
3. Whether tests use `engine.legal_actions()`.
4. Whether tests use `engine.apply_action()`.
5. Requirement kinds tested.
6. Exact pytest commands run and results.
7. If production code was changed, identify the exact defect the tests exposed.

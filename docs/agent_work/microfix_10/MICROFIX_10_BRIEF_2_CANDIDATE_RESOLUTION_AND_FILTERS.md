# TECHNICAL IMPLEMENTATION BRIEF 2 — Candidate Resolution And Filters

Goal:
Implement card/player target candidate resolution and core filters in `lorcana_bot/targeting.py`.

Required shared context:
Read `docs/agent_work/microfix_10/MICROFIX_10_SHARED_RULES.md` before making changes.

This brief depends on Brief 1.
Do not integrate into `engine.py` yet.
Do not implement slotted targets yet.
Do not implement Ward/cannot-be-targeted protection filtering here; that is Brief 3.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/targeting.py`
* **Line Range:** `After foundation helpers`
* **Snippet:**
```text
The targeting foundation can normalize descriptors, but it does not yet resolve
candidate card/player IDs or apply card filters.
```

Existing Brief 1 baseline to preserve:
```python
ACTION_SELECTION_ZONES = (ZONE_DECK, ZONE_HAND, ZONE_PLAY, ZONE_DISCARD, ZONE_INKWELL, ZONE_LIMBO)

class TargetDescriptor:
    selector: str
    min_count: int = 1
    max_count: int | None = 1
    zones: tuple[str, ...] = (ZONE_PLAY,)
    card_types: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    filters: tuple[dict[str, Any], ...] = ()
    exclude_self: bool = False
    exclude_trigger_subject: bool = False
    allow_players: bool = False
```

Scattered current logic:

```python
# lorcana_bot/effects.py
if target in {"your_characters", "your_other_characters", "opposing_characters", ...}:
    return self._collection(state, target, context)
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
def resolve_candidate_targets(
    state: GameState,
    engine: GameEngine,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[TargetCandidate, ...]: ...


def resolve_candidate_card_ids(
    state: GameState,
    engine: GameEngine,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]: ...


def resolve_candidate_player_ids(
    state: GameState,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]: ...
```

Candidate selection support:

```text
card/player distinction
chosen card selectors
all card selectors
self/source
event_source
event_target
trigger_subject
current_targets
context_targets
you/controller
opponent
each_player
zones: deck, hand, play, discard, inkwell, limbo
ZONE_UNDER must stay excluded from public candidate resolution
```

Filter support:

```text
card_type / cardTypes: character, action, item, location
classification / classifications
keyword / keywords
ink / color
owner/controller: you, opponent, any
damaged
exerted
ready
drying
location_instance_id / at_location
exclude_self
exclude_trigger_subject
```

Field aliases to accept in descriptors and filters:
```text
card_type/cardType/card_types/cardTypes
classification/classifications
keyword/keywords
ink/color
owner/controller
location_instance_id/locationInstanceId/at_location/atLocation
```

Use existing engine methods where available:

```text
engine.card_def(state, cid)
engine.has_keyword(state, cid, keyword)
engine.keywords_for_instance(state, cid)
engine.effective_strength/willpower/lore when needed by filters
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add candidate resolution functions to `targeting.py`.
* **Delta Description:** Add filter tests covering card type, classification, keyword, ink, damaged, exerted, owner/controller, and location association.
* **Delta Description:** Extend existing Brief 1 helpers where useful; do not duplicate the same selector logic in a new parallel path.
* **Delta Description:** Do not change engine legal actions yet.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts`
* **Line Range:** `Lines 39-90 and 234-240`
* **Logic Context:**
```typescript
export type ResolvedTargetQuery =
  | { kind: "card"; cardIds: CardInstanceId[] }
  | { kind: "player"; playerIds: PlayerId[] };

export function normalizeTargetDescriptor(target: unknown): TargetDescriptor | undefined
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/variants/__tests__/`
* **Logic Context:** Lorcanito tests variants for `chosen`, `all`, `each-player`, `opponent`, `self`, `source`, `trigger-subject`, and selected-target behavior.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest -q
```

Expected:
- `resolve_candidate_targets()` returns card and player candidates.
- Filters are covered by focused tests.
- Existing engine behavior unchanged.
- `chosen_card` can return character, item, or location card candidates when filters allow.
- `chosen_character` remains character-only.
- `ZONE_UNDER` cards remain excluded.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Selectors implemented.
3. Filters implemented.
4. Tests added.
5. Exact pytest commands run and results.

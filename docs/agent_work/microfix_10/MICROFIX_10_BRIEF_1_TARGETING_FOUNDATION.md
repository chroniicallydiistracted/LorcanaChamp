# TECHNICAL IMPLEMENTATION BRIEF 1 — Targeting Service Foundation

Goal:
Create the Python targeting-service foundation in `lorcana_bot/targeting.py`: normalized descriptors, candidate/result dataclasses, zone helpers, and lightweight selector/filter parsing.

Do not integrate the service into `engine.py` in this brief.
Do not change pending effects in this brief.
Do not implement trigger expansion from Microfix 11.

---

### 1. Current Missing Or Incomplete Code

* **File Path:** `lorcana_bot/targeting.py`
* **Line Range:** `File missing`
* **Snippet:**
```text
No central targeting service exists.
Target behavior is split across engine._effect_targets_for_card(),
pending_effects.get_valid_targets_for_requirement(), and EffectResolver helpers.
```

Current scattered examples:

```python
# lorcana_bot/engine.py
def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]:
    targets: set[int] = set()
    for target_kind in self._effect_target_kinds(card.effects):
        ...
```

```python
# lorcana_bot/pending_effects.py
def get_valid_targets_for_requirement(...):
    ...
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
@dataclass(frozen=True, slots=True)
class TargetDescriptor:
    selector: str
    min_count: int = 1
    max_count: int = 1
    zones: tuple[str, ...] = (ZONE_PLAY,)
    card_types: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    filters: tuple[dict[str, Any], ...] = ()
    exclude_self: bool = False
    exclude_trigger_subject: bool = False
    allow_players: bool = False


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    kind: str  # "card" or "player"
    id: int
    controller: int | None = None
    zone: str | None = None


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    actor: int
    source_id: int | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
```

Required functions:

```python
def normalize_target_descriptor(raw: Any) -> TargetDescriptor | None: ...
def normalize_target_descriptors(raw: Any) -> tuple[TargetDescriptor, ...]: ...
def infer_candidate_zones(candidate_ids: tuple[int, ...], state: GameState) -> tuple[str, ...]: ...
def is_card_target_candidate(state: GameState, card_id: int, descriptor: TargetDescriptor) -> bool: ...
def is_player_target_candidate(player_id: int, descriptor: TargetDescriptor) -> bool: ...
```

Normalization must support current Python aliases:

```text
chosen_character
chosen_card
chosen_item
chosen_location
chosen_opposing_character
chosen_damaged_character
opposing_character
self
event_source
event_target
trigger_subject
your_characters
your_other_characters
opposing_characters
all_characters
damaged_characters
opposing_damaged_characters
chosen_player
you
opponent
each_player
```

### 3. Fixes Needed

* **Action:** `ADD`
* **Delta Description:** Add `lorcana_bot/targeting.py` with dataclasses and normalization helpers only.
* **Delta Description:** Add `tests/test_targeting.py` foundation tests for alias normalization and zone inference.
* **Delta Description:** Keep engine behavior unchanged in this brief.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts`
* **Line Range:** `Lines 12-42`
* **Logic Context:**
```typescript
export type ActionSelectionZone = "deck" | "hand" | "play" | "discard" | "inkwell" | "limbo";
export function inferActionSelectionZonesFromCandidates(...)
export function isCardInstanceCandidate(...)
```

* **Reference File:** `lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts`
* **Line Range:** `Lines 48-90`
* **Logic Context:** Lorcanito normalizes target descriptors and target selection input into card/player query resolution.

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest -q
```

Expected:
- `lorcana_bot/targeting.py` exists.
- Alias normalization tests pass.
- No `engine.py` changes in this brief.

### 6. Final Response Requirements

Report:
1. Files changed.
2. Dataclasses added.
3. Alias descriptors supported.
4. Tests added.
5. Exact pytest commands run and results.
6. Confirmation that `engine.py` was not modified.

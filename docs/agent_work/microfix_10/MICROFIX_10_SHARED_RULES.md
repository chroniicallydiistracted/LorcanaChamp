# Microfix 10 Shared Targeting Rules

Use this file as required context for every Microfix 10 Technical Implementation Brief.

Microfix 10 Goal:
Centralize LorcanaChamp target interpretation in `lorcana_bot/targeting.py` so action legal-action enumeration, pending target selection, effect resolution, automation, and later slotted-target handling share one Lorcanito-aligned interpretation.

---

## 1. Completed Brief 1 Baseline

Brief 1 is already implemented. Do not recreate the foundation or rewrite it wholesale.

Current foundation files:
```text
lorcana_bot/targeting.py
tests/test_targeting.py
```

Current foundation API:
```python
ACTION_SELECTION_ZONES = (ZONE_DECK, ZONE_HAND, ZONE_PLAY, ZONE_DISCARD, ZONE_INKWELL, ZONE_LIMBO)

@dataclass(frozen=True, slots=True)
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
    allow_duplicate_targets: bool = False


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    kind: str
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

Current foundation helper functions:
```python
def normalize_target_descriptor(raw: Any) -> TargetDescriptor | None: ...
def normalize_target_descriptors(raw: Any) -> tuple[TargetDescriptor, ...]: ...
def infer_candidate_zones(candidate_ids: tuple[int, ...], state: GameState) -> tuple[str, ...]: ...
def is_card_target_candidate(...) -> bool: ...
def is_player_target_candidate(...) -> bool: ...
```

Important baseline behavior:
```text
chosen_card remains distinct from chosen_character.
max_count=None means unbounded/all.
ACTION_SELECTION_ZONES intentionally excludes ZONE_UNDER.
infer_candidate_zones() returns zones in Lorcanito order: deck, hand, play, discard, inkwell, limbo.
is_card_target_candidate() already excludes cards with stack_parent_id because cards under Shift stacks are not public candidates.
Normalization accepts Python and Lorcanito-style keys: card_type/cardType, card_types/cardTypes, min_count/minCount, max_count/maxCount, exclude_self/excludeSelf, exclude_trigger_subject/excludeTriggerSubject.
```

---

## 2. Current Supported Aliases

Do not regress any of these aliases:
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

Expected selector defaults:
```text
chosen_card: any public card, no card_types restriction
chosen_character: card_types=("character",)
chosen_item: card_types=("item",)
chosen_location: card_types=("location",)
chosen_opposing_character: controller="opponent"
chosen_damaged_character: damaged filter
your_characters: controller="you", max_count=None
your_other_characters: controller="you", exclude_self=True, max_count=None
opposing_characters: controller="opponent", max_count=None
all_characters: max_count=None
damaged_characters: damaged filter, max_count=None
opposing_damaged_characters: controller="opponent", damaged filter, max_count=None
chosen_player/you/opponent/each_player: allow_players=True
```

---

## 3. Completed Brief 2 Baseline

Brief 2 is already implemented. Do not recreate candidate resolution or rewrite it wholesale.

Current candidate-resolution API:
```python
def resolve_candidate_targets(
    state: GameState,
    engine: Any,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[TargetCandidate, ...]: ...

def resolve_candidate_card_ids(
    state: GameState,
    engine: Any,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]: ...

def resolve_candidate_player_ids(
    state: GameState,
    descriptor: TargetDescriptor,
    context: TargetQueryContext,
) -> tuple[int, ...]: ...
```

Important Brief 2 behavior:
```text
self, event_source, event_target, trigger_subject, current_targets, and context_targets are validated through the same candidate checks as normal card selectors.
Context-derived card IDs must not be returned raw.
event_source supports source, source_id, source_card_id, and trigger_source_card_id payload keys.
event_target supports target, target_id, target_card_id, event_target_id, defender_id, and subject_card_id payload keys.
trigger_subject supports subject, trigger_subject, subject_id, subject_card_id, defender_id, and target_id payload keys.
exclude_trigger_subject is wired into generic candidate resolution through the current context subject.
Unknown selectors with allow_players=True return no players instead of defaulting to both players.
Cards in ZONE_UNDER or with stack_parent_id remain excluded from public candidate resolution.
```

Current Brief 2 regression tests include:
```text
self selector respects descriptor zone
event target respects card type filters
trigger subject supports subject_card_id payload key
exclude_trigger_subject uses context subject
current_targets are validated against zone and under-stack rules
unknown allow_players selector returns no players
```

---

## 4. Sequencing Rules

Keep implementation boundaries strict:
```text
Brief 2: targeting.py candidate resolution and card/player filters only. Do not edit engine.py, pending_effects.py, effects.py, or automation.
Brief 3: targeting.py availability/protection filtering. Do not integrate engine legal actions yet.
Brief 4: engine.py action-card legal-action targeting only. Do not modify pending target enumeration.
Brief 5: pending_effects.py and engine.py pending target/multi_target integration.
Brief 6: effects.py EffectResolver integration. Do not add new effect kinds.
Brief 7: slotted target input shape, pending preservation, and automation round-trip.
Brief 8: consolidation, report audit, and roadmap update only after all earlier briefs pass.
```

When a brief depends on earlier helpers, extend those helpers instead of duplicating equivalent logic in another module.

---

## 5. Completed Brief 4 Baseline

Brief 4 is already implemented and audited. Do not recreate action-card legal-action targeting.

Current engine integration API:
```python
def _effect_target_descriptors_for_card(self, state: GameState, source: int) -> tuple[TargetDescriptor, ...]: ...
def _effect_target_candidates_for_card(self, state: GameState, player: int, source: int) -> tuple[TargetCandidate, ...]: ...
def _effect_targets_for_card(self, state: GameState, player: int, source: int) -> list[int]: ...
def _effect_requires_target(self, effect) -> bool: ...
def _effect_has_unsupported_target(self, effects) -> bool: ...
```

Current Brief 4 behavior:
```text
Only explicit target-selection descriptors create legal-action target choices.
Fixed player targets such as opponent/you/controller and collection targets such as all_characters are resolved by EffectResolver, not by legal-action target prompts.
Card targets use Action.target.
Player targets use Action.choice={"target_kind": "player", "player": player_id}; do not put player IDs in Action.target.
_resolve_effects(..., choice=player_id) passes chosen-player action targets into EffectResolutionContext.choice.
Unsupported action target descriptors fail closed and do not create broad fallback play actions.
```

The shared explicit-selection predicate is:
```python
def requires_explicit_target_selection(selector: str) -> bool:
    return selector.startswith("chosen") or selector == "opposing_character"
```

Do not widen Ward to automatic collection effects. Ward applies to explicit opponent target choices, not to collection effects that are resolved without a player selecting a target.

---

## 6. Lorcanito Source Authority

Use these source files as the authority for Microfix 10:
```text
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/targeting-service.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/slotted-targets.ts
lorcanito-full-src-code/packages/lorcana/lorcana-engine/src/targeting/variants/__tests__/
```

Relevant Lorcanito concepts:
```text
ActionSelectionZone is exactly deck, hand, play, discard, inkwell, limbo.
ResolvedTargetQuery distinguishes card IDs from player IDs.
Target availability computes candidate counts, card/player candidate counts, min/max, and whether explicit selection is required.
Target availability also carries `allowsExplicitEmptyTargetSelection`; in Python this is `allows_explicit_empty_target_selection`.
Duplicate-allowed target requirements can satisfy a multi-target minimum with one candidate; in Python this is `TargetDescriptor.allow_duplicate_targets`.
SlottedTargetInput preserves structured multi-slot choices and can be flattened deterministically.
```

---

## 7. Testing Rules

Every brief must run:
```bash
python3 -m pytest tests/test_targeting.py -q
```

Every brief that touches runtime behavior must also run the targeted tests named in that brief and:
```bash
python3 -m pytest -q
git diff --check
```

Tests must prove both the new behavior and that existing foundation behavior still works. Do not delete or weaken existing `tests/test_targeting.py` assertions to make new code pass.

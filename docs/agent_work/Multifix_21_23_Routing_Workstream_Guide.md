# Multifix 21–23 — Routing Workstream: Target Aliases, Slotted Inputs, Opponent Choice, and Destination/Ordering

This guide starts from the current `main` baseline after Microfix 20.

The goal is to handle the next **engine-development workstream**, not the largest individual card bucket. The current report shows that the biggest architectural blocker is still routing, especially targeting inside triggered/sequence/optional effects, not `if-you-do` yet.

Current Microfix 20 baseline:

```text
cards_loaded: 2754
ability_records_loaded: 3445
errors: []
executable: 10893
detailed_record_count: 1687

unsupported_by_reason:
  mapped_not_executable: 512
  unsupported_choice: 148
  unsupported_condition: 198
  unsupported_cost: 24
  unsupported_engine_mechanic: 242
  unsupported_targeting: 334

detailed_reason_counts:
  mapped_not_executable: 512
  unsupported_choice: 148
  unsupported_condition: 264
  unsupported_cost: 52
  unsupported_engine_mechanic: 242
  unsupported_targeting: 468
  unsupported_trigger: 1
```

Top routing-relevant patterns:

```text
ability.type:triggered:unsupported_targeting: 58
effect.type:sequence:unsupported_targeting: 45
effect.type:optional:unsupported_targeting: 36
effect.type:gain-keyword:unsupported_targeting: 29
effect.type:banish:unsupported_targeting: 20
effect.type:modify-stat:unsupported_targeting: 20
ability.type:triggered:unsupported_choice: 31
effect.type:sequence:unsupported_choice: 26
ability.type:action:unsupported_choice: 19
```

This fix is intentionally a **Multifix** because these are connected by the same runtime problem:

```text
1. remaining target aliases/object selectors
2. role-labeled slotted target inputs
3. chooser transfer for opponent choice
4. ordered/destination routing preservation
```

However, implement it in the exact gates below. If a gate fails, stop and fix that gate before moving to the next.

---

# 1. Lorcanito source paths inspected

Confirmed against these Lorcanito source files:

```text
lorcana/lorcana-types/src/abilities/target-types.ts
lorcana/lorcana-types/src/targeting/enum-expansions.ts
lorcana/lorcana-types/src/targeting/normalize.ts
lorcana/lorcana-engine/src/targeting/runtime/target-availability.ts
lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-context.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/selection-state.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/move-to-location-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/for-each-opponent-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/player-target-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-on-top-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/put-on-bottom-effect.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/conditional-effect.ts
```

Confirmed current LorcanaChamp files:

```text
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_report.md
lorcana_bot/targeting.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/card_logic/resolution_requirements.py
lorcana_bot/effect_types.py
lorcana_bot/effects.py
lorcana_bot/engine.py
lorcana_bot/abilities.py
lorcana_bot/pending_effects.py
tests/test_targeting.py
tests/test_source_projection_policy.py
tests/test_activated_abilities_execution.py
tests/test_bag_resolution.py
tests/test_pending_effects.py
```

---

# 2. Lorcanito mechanics confirmed

## 2.1 Remaining alias expansions

Lorcanito expands these target enums:

```ts
YOUR_EXERTED_CHARACTERS: {
  selector: "all",
  count: "all",
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "exerted" }],
}

UP_TO_2_CHOSEN_CHARACTERS: {
  selector: "chosen",
  count: { upTo: 2 },
  owner: "any",
  zones: ["play"],
  cardTypes: ["character"],
}

CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS: {
  selector: "chosen",
  count: 1,
  owner: "opponent",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "strength-comparison", comparison: "less-or-equal", value: 3 }],
}

OPPONENTS: { selector: "opponent" }
```

## 2.2 Context and previous-target routing

Lorcanito `selection-state.ts` treats selected targets as resolution state:

```text
currentTargets
contextTargets
targets
```

Important behavior:

```text
- currentTargets are the current prompt's selection.
- contextTargets are prior sequence selections.
- { ref: "previous-target" } prefers contextTargets inside a sequence.
- selected-all returns the whole selected-target list.
```

## 2.3 Slotted target input

Lorcanito `move-to-location-effect.ts` uses slotted input:

```ts
resolutionInput.slottedTargets = {
  kind: "move-to-location",
  subject: [...character ids],
  location: [...location ids],
}
```

It resolves the character slot and location slot independently, then moves all character IDs to the selected location.

## 2.4 Opponent-choice chooser transfer

Lorcanito `selection-context.ts` resolves chooser ownership from:

```text
effect.chosenBy
effect.chooser
parent optional/choice chooser
selected player
card owner
```

For `chosenBy: "opponent"`:

```text
chooserId = opponent of effect controller
controller still resolves the effect after opponent supplies input
```

This is the important runtime split:

```text
controller_id = original effect controller
chooser_id = player supplying choice
```

## 2.5 Destination and ordering preservation

Lorcanito preserves:

```text
targets
currentTargets
contextTargets
destinations
```

For `put-on-bottom` with `ordering: "player-choice"`, Lorcanito uses selected target order instead of default candidate order.

---

# 3. Current LorcanaChamp behavior

Already implemented:

```text
TargetDescriptor min/max counts
enumerate_target_selections()
context current_targets in EffectResolutionContext
bag resolution_input targets
slotted target validation helpers
SLOTTED_TARGET_KINDS
SLOTTED_TARGET_SLOT_KEYS
```

Current gaps:

```text
1. Missing high-impact aliases:
   - UP_TO_2_CHOSEN_CHARACTERS
   - CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS
   - YOUR_EXERTED_CHARACTERS
   - OPPONENTS

2. Mapper rejects selector objects with selector: "self", even though runtime can normalize them.

3. Missing target filter:
   - challenged-this-turn

4. move-to-location is known in Lorcanito and card_logic.effect_utils, but not fully mapped through lorcanito_source_mapper / effect_types / EffectResolver.

5. Slotted target input exists as validation helpers but is not generated for play actions, activated abilities, or bag input.

6. opponent_choice exists as a pending requirement kind, but source executability still classifies chosenBy: opponent as unsupported_choice.

7. EffectResolutionContext does not yet carry slotted_targets or destinations, so effects cannot consume role-labeled input.

8. put-on-top / put-on-bottom handlers are currently legacy-choice oriented and should consume selected targets/current target order.
```

---

# 4. Implementation gates

Implement in this order:

```text
Gate A / Microfix 21:
  Remaining target alias/object/filter support.

Gate B / Microfix 22:
  Slotted move-to-location routing and opponent-choice chooser transfer.

Gate C / Microfix 23:
  Destination/order preservation for put-on-top / put-on-bottom and pending destination context.
```

Stop after each gate and run the relevant tests before continuing.

---

# Gate A — Microfix 21 target alias/object/filter expansion

## A1. Edit `lorcana_bot/targeting.py`

### A1.1 Add selector aliases

Inside `SELECTOR_ALIASES`, add these entries.

Place them near the other chosen and character set aliases:

```python
    "up_to_2_chosen_characters": "up_to_2_chosen_characters",
    "chosen_opposing_character_3_strength_or_less": "chosen_opposing_character_3_strength_or_less",
    "your_exerted_characters": "your_exerted_characters",
    "opponents": "opponent",
```

### A1.2 Add descriptors

Inside `_create_descriptor_for_selector()`, add these blocks.

Place `up_to_2_chosen_characters` after `chosen_character`.

```python
    if selector == "up_to_2_chosen_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=2,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )
```

Place `chosen_opposing_character_3_strength_or_less` after `chosen_opposing_character`.

```python
    if selector == "chosen_opposing_character_3_strength_or_less":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
            filters=(
                {"type": "strength-comparison", "comparison": "less-or-equal", "value": 3},
            ),
        )
```

Place `your_exerted_characters` near `your_characters`.

```python
    if selector == "your_exerted_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "exerted"},),
        )
```

### A1.3 Update explicit target detection

Replace `requires_explicit_target_selection()` with:

```python
def requires_explicit_target_selection(selector: str) -> bool:
    """Return True when *selector* requires a player target choice.

    Chosen selectors and enum-expanded chosen aliases require explicit target
    input. Collection aliases like your_exerted_characters do not.
    """
    return (
        selector.startswith("chosen")
        or selector.startswith("your_chosen")
        or selector.startswith("another_chosen")
        or selector.startswith("up_to_")
        or selector == "opposing_character"
    )
```

### A1.4 Add `challenged-this-turn` filter support

Inside `_target_filters_supported()` in the mapper later we will mark this supported. The runtime filter must exist first.

In `targeting.py`, inside `_apply_filter()`, add this block after `filter_type == "ready"` and before `filter_type == "drying"`:

```python
    if filter_type == "challenged-this-turn":
        return bool(getattr(inst, "was_challenged_this_turn", False))
```

Also add `"was_challenged_this_turn"` aliases to `_FILTER_FIELD_ALIASES`:

```python
    "challenged_this_turn": "challenged_this_turn",
    "challengedThisTurn": "challenged_this_turn",
    "was_challenged_this_turn": "challenged_this_turn",
    "wasChallengedThisTurn": "challenged_this_turn",
```

Then add the field-alias style check near the other boolean state filters:

```python
    if "challenged_this_turn" in normalized:
        if bool(normalized["challenged_this_turn"]) != bool(getattr(inst, "was_challenged_this_turn", False)):
            return False
```

---

## A2. Edit `lorcana_bot/importers/lorcanito_source_mapper.py`

### A2.1 Add target aliases

In `TARGET_MAP`, add:

```python
    "OPPONENTS": "opponent",
    "UP_TO_2_CHOSEN_CHARACTERS": "up_to_2_chosen_characters",
    "CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS": "chosen_opposing_character_3_strength_or_less",
    "YOUR_EXERTED_CHARACTERS": "your_exerted_characters",
```

Recommended placement:

```python
    "OPPONENT": "opponent",
    "OPPONENTS": "opponent",
```

```python
    "CHOSEN_CHARACTER": "chosen_character",
    "UP_TO_2_CHOSEN_CHARACTERS": "up_to_2_chosen_characters",
```

```python
    "CHOSEN_OPPOSING_CHARACTER": "opposing_character",
    "CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS": "chosen_opposing_character_3_strength_or_less",
```

```python
    "YOUR_CHARACTERS": "your_characters",
    "YOUR_EXERTED_CHARACTERS": "your_exerted_characters",
```

Add the same raw alias strings to `SUPPORTED_TARGET_ALIASES`.

### A2.2 Add selector object support for context selectors

Add this helper before `_source_target_shape_supported()`:

```python
def _source_context_target_shape_supported(raw: dict[str, Any]) -> bool:
    selector = raw.get("selector") or raw.get("type") or raw.get("kind")
    if selector not in {
        "self",
        "source",
        "trigger-source",
        "trigger-subject",
        "trigger-destination",
        "event-source",
        "event-target",
        "attacker",
        "defender",
        "previous-target",
        "selected-first",
        "selected-all",
    }:
        return False

    zones = tuple(raw.get("zones", (raw.get("zone"),) if raw.get("zone") else ()))
    if any(zone not in {"play", "discard", "hand", "inkwell", "deck"} for zone in zones):
        return False

    card_types = tuple(raw.get("cardTypes", (raw.get("cardType"),) if raw.get("cardType") else ()))
    if any(card_type not in {"card", "character", "item", "location", "action"} for card_type in card_types):
        return False

    count = raw.get("count", 1)
    if count not in {1, "1", None}:
        return False

    return _target_filters_supported(raw)
```

Then inside `_source_target_shape_supported()`, after the `ref` branch and before the `selector == "all"` branch, add:

```python
    if _source_context_target_shape_supported(raw):
        return True
```

This unblocks shapes like:

```json
{"selector": "self", "count": 1, "zones": ["play"], "cardTypes": ["character"]}
```

### A2.3 Add `challenged-this-turn` filter to mapper allowlist

Inside `_target_filters_supported()`, add:

```python
        "challenged-this-turn",
```

to the `supported` set.

---

## A3. Edit `tests/test_targeting.py`

### A3.1 Add alias normalization tests

Add these to the existing parameterized alias test list:

```python
        (
            "up_to_2_chosen_characters",
            {"card_types": (CARD_CHARACTER,), "min_count": 0, "max_count": 2},
        ),
        (
            "chosen_opposing_character_3_strength_or_less",
            {
                "card_types": (CARD_CHARACTER,),
                "controller": "opponent",
                "filters": (
                    {"type": "strength-comparison", "comparison": "less-or-equal", "value": 3},
                ),
            },
        ),
        (
            "your_exerted_characters",
            {
                "card_types": (CARD_CHARACTER,),
                "owner": "you",
                "filters": ({"type": "exerted"},),
                "max_count": None,
            },
        ),
```

### A3.2 Add selector self object test

Add:

```python
def test_normalize_selector_self_object_keeps_lorcanito_constraints():
    descriptor = normalize_target_descriptor({
        "selector": "self",
        "count": 1,
        "owner": "any",
        "zones": [ZONE_PLAY],
        "cardTypes": [CARD_CHARACTER],
    })

    assert descriptor is not None
    assert descriptor.selector == "self"
    assert descriptor.zones == (ZONE_PLAY,)
    assert descriptor.card_types == (CARD_CHARACTER,)
    assert descriptor.owner == "any"
```

### A3.3 Add challenged-this-turn filter test

Add:

```python
def test_challenged_this_turn_filter_matches_runtime_flag(engine, state):
    challenged = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
    unchallenged = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, exclude={challenged})
    state.cards[challenged].was_challenged_this_turn = True

    descriptor = normalize_target_descriptor({
        "selector": "chosen",
        "count": 1,
        "zones": [ZONE_PLAY],
        "cardTypes": [CARD_CHARACTER],
        "filter": [{"type": "challenged-this-turn"}],
    })

    assert descriptor is not None
    context = TargetQueryContext(actor=0)
    assert resolve_candidate_card_ids(state, engine, descriptor, context) == (challenged,)
    assert unchallenged not in resolve_candidate_card_ids(state, engine, descriptor, context)
```

---

## A4. Edit `tests/test_source_projection_policy.py`

Add tests for the new aliases and selector object support.

```python
def test_microfix21_remaining_target_aliases_project():
    for alias in (
        "OPPONENTS",
        "UP_TO_2_CHOSEN_CHARACTERS",
        "CHOSEN_OPPOSING_CHARACTER_3_STRENGTH_OR_LESS",
        "YOUR_EXERTED_CHARACTERS",
    ):
        target = map_raw_target(alias)
        assert target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix21_selector_self_object_is_executable():
    target = map_raw_target({
        "selector": "self",
        "count": 1,
        "owner": "any",
        "zones": ["play"],
        "cardTypes": ["character"],
    })

    assert target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix21_challenged_this_turn_filter_is_supported():
    target = map_raw_target({
        "selector": "chosen",
        "count": 1,
        "owner": "any",
        "zones": ["play"],
        "cardTypes": ["character"],
        "filter": [{"type": "challenged-this-turn"}],
    })

    assert target.execution_status == ExecutionStatus.EXECUTABLE
```

---

# Gate A validation

Run:

```bash
python3 -m py_compile \
  lorcana_bot/targeting.py \
  lorcana_bot/importers/lorcanito_source_mapper.py
```

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
```

Then run the report:

```bash
python3 scripts/report_lorcanito_v2_unsupported.py
```

Expected Gate A movement:

```text
unsupported_targeting should decrease.
target:alias should decrease.
target:selector should decrease.
```

---

# Gate B — Microfix 22 slotted target routing and opponent-choice transfer

Gate B implements concrete runtime routing for:

```text
move-to-location slotted input
chosenBy: opponent chooser transfer
optional/choice explicit chooser propagation
```

This does not attempt arbitrary multi-prompt sequence routing. It implements the concrete Lorcanito forms currently visible in the report and already modeled by LorcanaChamp helpers.

---

## B1. Edit `lorcana_bot/effect_types.py`

### B1.1 Add slotted and destination state to `EffectResolutionContext`

Replace `EffectResolutionContext` with this copy-paste version:

```python
@dataclass(frozen=True, slots=True)
class EffectResolutionContext:
    actor: int
    source: int | None = None
    target: int | None = None
    choice: Any | None = None
    optional_choices: dict[str, bool] = field(default_factory=dict)
    # Trigger context fields for proper effect resolution
    event: Any | None = None
    event_payload: dict[str, Any] = field(default_factory=dict)
    pending_trigger_id: str | None = None
    trigger_source: int | None = None
    trigger_subject: int | None = None
    current_targets: tuple[int, ...] = ()
    context_targets: tuple[int, ...] = ()
    slotted_targets: dict[str, Any] | None = None
    destinations: tuple[dict[str, Any], ...] = ()
    last_effect_performed: bool = False
```

### B1.2 Add `move_to_location` to supported effect kinds

In `SUPPORTED_EFFECT_KINDS`, add:

```python
        "move_to_location",
```

near the other movement effects.

---

## B2. Edit `lorcana_bot/importers/lorcanito_source_mapper.py`

### B2.1 Add `move-to-location` to engine effect map

In `ENGINE_EFFECT_MAP`, add:

```python
    "move-to-location": "move_to_location",
```

near the other movement effects.

### B2.2 Add `for-each-opponent` mapping

In `ENGINE_EFFECT_MAP`, add:

```python
    "for-each-opponent": "for_each_opponent",
```

Do not add the resolver yet unless you complete B6 below. If B6 is not completed, leave this out. If B6 is completed, also add `for_each_opponent` to `SUPPORTED_EFFECT_KINDS`.

### B2.3 Add supported trigger effect kind

In `SUPPORTED_TRIGGER_EFFECT_KINDS`, add:

```python
    "move-to-location",
```

### B2.4 Support opponent-choice requirement

In `lorcana_bot/card_logic/resolution_requirements.py`, update the supported requirement set.

#### Previous code

```python
_ALWAYS_SUPPORTED_REQUIREMENTS = frozenset({
    "optional",
    "choice",
    "target",
})
```

#### Replacement code

```python
_ALWAYS_SUPPORTED_REQUIREMENTS = frozenset({
    "optional",
    "choice",
    "target",
    "opponent_choice",
})
```

This is safe only after B4/B5 implement chooser transfer. Do not make this change before the runtime path exists.

---

## B3. Edit `lorcana_bot/engine.py` — slotted target helpers

Add these helpers near `_targeted_play_actions()`.

```python
    def _effect_source_raw(self, effect: Any) -> dict[str, Any]:
        raw = getattr(effect, "raw", {}) or {}
        if isinstance(raw, dict) and isinstance(raw.get("raw"), dict):
            return raw["raw"]
        return raw if isinstance(raw, dict) else {}

    def _effect_kind_name(self, effect: Any) -> str:
        return str(getattr(effect, "kind", "") or "").replace("_", "-")

    def _move_to_location_slot_specs(self, effects: tuple[Any, ...]) -> tuple[dict[str, Any], ...]:
        specs: list[dict[str, Any]] = []
        for effect in effects:
            if self._effect_kind_name(effect) == "move-to-location":
                raw = self._effect_source_raw(effect)
                character = raw.get("character") or raw.get("subject")
                location = raw.get("location")
                if character is not None and location is not None:
                    specs.append({
                        "kind": "move-to-location",
                        "slots": {
                            "subject": character,
                            "location": location,
                        },
                    })
            child_effects = tuple(getattr(effect, "effects", ()) or ())
            if child_effects:
                specs.extend(self._move_to_location_slot_specs(child_effects))
        return tuple(specs)

    def _effect_requires_slotted_targets(self, effects: tuple[Any, ...]) -> bool:
        return bool(self._move_to_location_slot_specs(effects))

    def _slot_target_selections(
        self,
        state: GameState,
        *,
        actor: int,
        source_id: int | None,
        raw_target: Any,
        event_payload: dict[str, Any] | None = None,
    ) -> tuple[tuple[int, ...], ...]:
        from .targeting import (
            TargetQueryContext,
            apply_target_protections,
            enumerate_target_selections,
            normalize_target_descriptor,
            resolve_candidate_targets,
        )

        descriptor = normalize_target_descriptor(raw_target)
        if descriptor is None:
            return ()

        context = TargetQueryContext(
            actor=actor,
            source_id=source_id,
            event_payload=dict(event_payload or {}),
        )
        candidates = apply_target_protections(
            state,
            self,
            resolve_candidate_targets(state, self, descriptor, context),
            descriptor,
            context,
        )
        return enumerate_target_selections(candidates, descriptor, candidate_kind="card")

    def _enumerate_move_to_location_slotted_targets(
        self,
        state: GameState,
        *,
        actor: int,
        source_id: int | None,
        spec: dict[str, Any],
        event_payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        slots = spec.get("slots", {})
        subject_options = self._slot_target_selections(
            state,
            actor=actor,
            source_id=source_id,
            raw_target=slots.get("subject"),
            event_payload=event_payload,
        )
        location_options = self._slot_target_selections(
            state,
            actor=actor,
            source_id=source_id,
            raw_target=slots.get("location"),
            event_payload=event_payload,
        )

        result: list[dict[str, Any]] = []
        for subjects in subject_options:
            if not subjects:
                continue
            for locations in location_options:
                if len(locations) != 1:
                    continue
                result.append({
                    "kind": "move-to-location",
                    "subject": tuple(subjects),
                    "location": tuple(locations),
                })
        return tuple(result)
```

---

## B4. Edit `lorcana_bot/engine.py` — action-card slotted play actions

### B4.1 Update play-action detection

Inside `legal_actions()`, find:

```python
                if card.card_type == CARD_ACTION and any(self._effect_requires_target(e) for e in card.effects):
                    actions.extend(self._targeted_play_actions(state, player, cid))
                else:
                    actions.append(Action(ACTION_PLAY_CARD, actor=player, card=cid))
```

Replace with:

```python
                if card.card_type == CARD_ACTION and (
                    any(self._effect_requires_target(e) for e in card.effects)
                    or self._effect_requires_slotted_targets(card.effects)
                ):
                    actions.extend(self._targeted_play_actions(state, player, cid))
                else:
                    actions.append(Action(ACTION_PLAY_CARD, actor=player, card=cid))
```

### B4.2 Add slotted actions to `_targeted_play_actions()`

At the top of `_targeted_play_actions()`, after `query_context = TargetQueryContext(actor=player, source_id=source)`, add:

```python
        for spec in self._move_to_location_slot_specs(self.card_def(state, source).effects):
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=player,
                source_id=source,
                spec=spec,
            ):
                subjects = tuple(slotted.get("subject", ()) or ())
                actions.append(Action(
                    ACTION_PLAY_CARD,
                    actor=player,
                    card=source,
                    target=subjects[0] if subjects else None,
                    choice={"slotted_targets": slotted},
                ))
```

Leave the existing flat target enumeration below it.

---

## B5. Edit `lorcana_bot/engine.py` and `lorcana_bot/abilities.py` — activated ability slotted actions

### B5.1 Generate activated slotted actions

Inside `legal_actions()`, in the activated ability loop, before `target_selections = self._activated_ability_target_selections(...)`, add:

```python
            slotted_actions = self._activated_ability_slotted_target_actions(state, ability, player)
            if slotted_actions is not None:
                actions.extend(slotted_actions)
                continue
```

Then add this method near `_activated_ability_target_selections()`:

```python
    def _activated_ability_slotted_target_actions(
        self,
        state: GameState,
        ability: ActivatedAbility,
        player: int,
    ) -> list[Action] | None:
        specs = self._move_to_location_slot_specs(ability.effects)
        if not specs:
            return None

        result: list[Action] = []
        for spec in specs:
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=player,
                source_id=ability.source_instance_id,
                spec=spec,
            ):
                subjects = tuple(slotted.get("subject", ()) or ())
                result.append(Action(
                    ACTION_USE_ABILITY,
                    actor=player,
                    source=ability.source_instance_id,
                    target=subjects[0] if subjects else None,
                    choice={
                        "ability_id": ability.ability_id,
                        "ability_index": ability.ability_index,
                        "slotted_targets": slotted,
                    },
                ))
        return result
```

### B5.2 Apply activated slotted input

Inside `_apply_use_ability()`, after selected_targets extraction, add:

```python
        slotted_targets = None
        if action.choice and isinstance(action.choice, dict):
            slotted_targets = action.choice.get("slotted_targets")
```

Then replace:

```python
        result = use_ability(state, self, ability, selected_targets=selected_targets)
```

with:

```python
        result = use_ability(
            state,
            self,
            ability,
            selected_targets=selected_targets,
            slotted_targets=slotted_targets,
        )
```

### B5.3 Update `lorcana_bot/abilities.py`

Change `execute_ability_effects()` signature:

```python
def execute_ability_effects(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    *,
    selected_targets: tuple[int, ...] = (),
    slotted_targets: dict[str, Any] | None = None,
) -> None:
```

Inside its `EffectResolutionContext(...)`, add:

```python
        slotted_targets=slotted_targets,
```

Change `use_ability()` signature:

```python
def use_ability(
    state: GameState,
    engine: GameEngine,
    ability: ActivatedAbility,
    *,
    selected_targets: tuple[int, ...] = (),
    slotted_targets: dict[str, Any] | None = None,
) -> AbilityUseResult:
```

Replace:

```python
        execute_ability_effects(state, engine, ability, selected_targets=selected_targets)
```

with:

```python
        execute_ability_effects(
            state,
            engine,
            ability,
            selected_targets=selected_targets,
            slotted_targets=slotted_targets,
        )
```

---

## B6. Edit `lorcana_bot/engine.py` — pass slotted/destination context

### B6.1 Update `_apply_play()`

Inside `_apply_play()`, where action card effects are resolved, add:

```python
            slotted_targets = None
            if action.choice and isinstance(action.choice, dict):
                slotted_targets = action.choice.get("slotted_targets")
```

Then update the `_resolve_effects()` call to include:

```python
                slotted_targets=slotted_targets,
```

### B6.2 Update `_resolve_effects()` signature and context

Replace the signature with:

```python
    def _resolve_effects(
        self,
        state: GameState,
        player: int,
        source: int,
        target: int | None,
        *,
        choice: Any = None,
        current_targets: tuple[int, ...] = (),
        slotted_targets: dict[str, Any] | None = None,
        destinations: tuple[dict[str, Any], ...] = (),
    ) -> None:
```

Inside the `EffectResolutionContext(...)`, add:

```python
                slotted_targets=slotted_targets,
                destinations=destinations,
```

### B6.3 Update `_apply_resolve_bag()` context

Inside `_apply_resolve_bag()`, after `selected_targets = ...`, add:

```python
        slotted_targets = entry.resolution_input.get("slotted_targets")
        destinations = tuple(
            dict(destination)
            for destination in entry.resolution_input.get("destinations", ()) or ()
            if isinstance(destination, dict)
        )
```

Inside the bag `EffectResolutionContext(...)`, add:

```python
            slotted_targets=slotted_targets,
            destinations=destinations,
```

### B6.4 Update `_apply_resolve_pending_effect()` context

Inside `_apply_resolve_pending_effect()`, where the final `EffectResolutionContext(...)` is built, add:

```python
                slotted_targets=raw.get("slotted_targets") or raw.get("resolution_input", {}).get("slotted_targets"),
                destinations=tuple(
                    dict(destination)
                    for destination in (
                        raw.get("destinations")
                        or raw.get("resolution_input", {}).get("destinations")
                        or ()
                    )
                    if isinstance(destination, dict)
                ),
```

---

## B7. Edit `lorcana_bot/effects.py` — implement move-to-location effect

### B7.1 Add dispatch

Inside `EffectResolver.resolve()`, after `elif kind == "move_damage":`, add:

```python
        elif kind == "move_to_location":
            self._resolve_move_to_location(state, effect, context)
```

### B7.2 Add resolver method

Add this method near `_resolve_move_damage()`:

```python
    def _resolve_move_to_location(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        raw = self._source_raw(effect)
        slotted = context.slotted_targets if isinstance(context.slotted_targets, dict) else None

        character_ids: tuple[int, ...] = ()
        location_ids: tuple[int, ...] = ()

        if slotted and slotted.get("kind") == "move-to-location":
            character_ids = tuple(int(cid) for cid in slotted.get("subject", ()) or ())
            location_ids = tuple(int(cid) for cid in slotted.get("location", ()) or ())
        else:
            character_target = raw.get("character") or raw.get("subject")
            location_target = raw.get("location")

            if character_target is not None:
                character_effect = EffectDef("select_target", target=character_target, raw={"raw": {"target": character_target}})
                character_ids = tuple(self._target_cards(state, character_effect, context, require_target=False))

            if location_target is not None:
                location_effect = EffectDef("select_target", target=location_target, raw={"raw": {"target": location_target}})
                location_ids = tuple(self._target_cards(state, location_effect, context, require_target=False))

        if raw.get("includeSelf") is True and context.source is not None:
            source_card = self.engine.card_def(state, context.source)
            if source_card.card_type == "character":
                character_ids = tuple(dict.fromkeys((*character_ids, context.source)))

        if len(location_ids) != 1:
            raise EffectResolutionError("move-to-location requires exactly one location target")

        location_id = int(location_ids[0])
        if location_id not in state.cards or self.engine.card_def(state, location_id).card_type != "location":
            raise EffectResolutionError("move-to-location location target must be a location")

        moved_any = False
        for character_id in character_ids:
            if character_id not in state.cards:
                continue
            if self.engine.card_def(state, character_id).card_type != "character":
                continue
            if state.cards[character_id].zone != ZONE_PLAY:
                continue
            previous_location = state.cards[character_id].location_instance_id
            state.cards[character_id].location_instance_id = location_id
            moved_any = True
            self.engine.emit_event(
                state,
                "CARD_MOVED_TO_LOCATION",
                actor=context.actor,
                source=character_id,
                target=location_id,
                payload={
                    "player_id": context.actor,
                    "subject_card_id": character_id,
                    "location_id": location_id,
                    "from_zone": f"location:{previous_location}" if previous_location is not None else ZONE_PLAY,
                    "to_zone": f"location:{location_id}",
                    "source_card_id": context.source,
                    "trigger_source_card_id": context.source,
                },
            )

        if not moved_any and not raw.get("includeSelf"):
            return
```

---

## B8. Edit `lorcana_bot/engine.py` — bag slotted actions

Inside `_bag_resolution_input_actions()`, add this nested helper after `target_actions()`:

```python
        def move_to_location_actions(effect: Any, base_choice: dict[str, Any]) -> list[Action]:
            raw = effect.raw.get("raw") if isinstance(effect.raw.get("raw"), dict) else effect.raw
            if not isinstance(raw, dict):
                return []
            character = raw.get("character") or raw.get("subject")
            location = raw.get("location")
            if character is None or location is None:
                return []

            event_payload = {}
            if entry.event:
                event_payload.update(entry.event.event_snapshot or {})
                event_payload.update(entry.event.payload or {})

            spec = {
                "kind": "move-to-location",
                "slots": {
                    "subject": character,
                    "location": location,
                },
            }
            result: list[Action] = []
            for slotted in self._enumerate_move_to_location_slotted_targets(
                state,
                actor=entry.chooser_id,
                source_id=entry.source_id,
                spec=spec,
                event_payload=event_payload,
            ):
                choice = dict(base_choice)
                choice["slotted_targets"] = slotted
                subjects = tuple(slotted.get("subject", ()) or ())
                result.append(Action(
                    ACTION_RESOLVE_BAG,
                    actor=player,
                    source=entry.source_id,
                    target=subjects[0] if subjects else None,
                    choice=choice,
                ))
            return result
```

Then inside the `if effect.kind == "optional"` child handling, before `move_damage`, add:

```python
                if getattr(child, "kind", None) == "move_to_location":
                    actions.extend(move_to_location_actions(child, {"bag_id": entry.id, "accept": True}))
                    continue
```

Also add a top-level branch in the main loop:

```python
            elif effect.kind == "move_to_location":
                actions.extend(move_to_location_actions(effect, {"bag_id": entry.id, "accept": True}))
```

---

## B9. Opponent-choice chooser transfer

### B9.1 Add chooser helper in `engine.py`

Add:

```python
    def _effect_choice_actor(
        self,
        state: GameState,
        *,
        controller_id: int,
        raw: dict[str, Any],
        parent_chooser_id: int | None = None,
    ) -> int:
        chooser = raw.get("chooser")
        chosen_by = raw.get("chosenBy") or raw.get("chosen_by")

        if parent_chooser_id is not None and chooser is None and chosen_by is None:
            return parent_chooser_id

        normalized = str(chooser or chosen_by or "").replace("_", "-").lower()
        if normalized in {"opponent", "opponents"}:
            return state.opponent(controller_id)
        if normalized in {"controller", "you", "self"}:
            return controller_id
        return controller_id
```

### B9.2 Use chooser helper in bag target actions

In `_bag_resolution_input_actions()`, change target action contexts that currently use:

```python
context = TargetQueryContext(actor=entry.controller_id, source_id=entry.source_id, event_payload=event_payload)
```

to use:

```python
chooser_actor = entry.chooser_id
context = TargetQueryContext(actor=chooser_actor, source_id=entry.source_id, event_payload=event_payload)
```

Do the same in `_bag_target_actions_from_raw()`:

```python
context = TargetQueryContext(actor=entry.chooser_id, source_id=entry.source_id, event_payload={})
```

This is critical: Ward/protection and owner/controller filtering must be evaluated from the chooser’s perspective, while final effect resolution still uses `entry.controller_id`.

### B9.3 Create pending opponent-choice effects from `EffectResolver`

This part is intentionally conservative: only implement for normal card-target effects with `chosenBy: "opponent"`.

In `effects.py`, add this helper:

```python
    def _effect_chosen_by_opponent(self, effect: EffectDef) -> bool:
        raw = self._source_raw(effect)
        return str(raw.get("chosenBy") or raw.get("chosen_by") or "").casefold() == "opponent"
```

At the top of `resolve()`, after `kind = effect.kind`, add:

```python
        if self._effect_chosen_by_opponent(effect) and context.source is not None:
            self._create_opponent_target_pending(state, effect, context)
            return
```

Add this method:

```python
    def _create_opponent_target_pending(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        from .pending_effects import create_pending_effect

        raw = self._source_raw(effect)
        target = raw.get("target") or effect.target
        if target is None:
            raise EffectResolutionError("chosenBy opponent effect requires a target")

        source_card_id = self.engine.card_def(state, context.source).id if context.source else None
        pending_effect = EffectDef(
            kind=effect.kind,
            amount=effect.amount,
            target=effect.target,
            value=effect.value,
            keyword=effect.keyword,
            effects=effect.effects,
            condition=effect.condition,
            optional=effect.optional,
            duration=effect.duration,
            raw=effect.raw,
        )

        create_pending_effect(
            state,
            controller_id=context.actor,
            chooser_id=state.opponent(context.actor),
            source_id=context.source,
            source_card_id=source_card_id,
            effects=(pending_effect,),
            origin="opponent_choice",
            raw={
                "requirement_kind": "opponent_choice",
                "choice_type": "target",
                "target": target,
                "selected_targets": context.current_targets,
                "context_targets": context.context_targets,
            },
        )
```

### B9.4 Ensure pending opponent target candidates use raw target

In `pending_effects.py`, update `get_valid_target_candidates_for_pending()` if it already exists. If it does not, find it first before editing.

The expected behavior:

```python
raw_target = (pe.raw or {}).get("target")
if raw_target is not None:
    descriptor = normalize_target_descriptor(raw_target)
else:
    descriptor = target_descriptor_from_requirement(...)
```

Candidate resolution must use:

```python
TargetQueryContext(actor=chooser_id, source_id=pe.source_id, event_payload=pe.raw.get("event_payload", {}))
```

Do not use `controller_id` as the actor for opponent choice candidate validation.

---

# Gate B validation

Run:

```bash
python3 -m py_compile \
  lorcana_bot/effect_types.py \
  lorcana_bot/targeting.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/card_logic/resolution_requirements.py \
  lorcana_bot/engine.py \
  lorcana_bot/effects.py \
  lorcana_bot/abilities.py \
  lorcana_bot/pending_effects.py
```

Run targeted tests:

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
python3 -m pytest tests/test_activated_abilities_execution.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
```

Add at least one activated move-to-location test:

```python
def test_move_to_location_activated_ability_uses_slotted_targets(...):
    # source: Magic Carpet-style item
    # subject: friendly character in play
    # location: friendly location in play
    # expected legal USE_ABILITY has choice["slotted_targets"]
    # after apply_action, subject.location_instance_id == location
```

Add at least one opponent-choice test:

```python
def test_chosen_by_opponent_creates_pending_for_opponent(...):
    # effect controller is player 0
    # effect raw has chosenBy: opponent and target owner: opponent
    # after resolution, pending_effect.chooser_id == 1
    # legal actions for player 1 include RESOLVE_PENDING_EFFECT
    # selected target resolves under controller_id 0
```

---

# Gate C — Microfix 23 destination/order preservation

Gate C is not full arbitrary destination routing. It implements the destination/order mechanics that are already closest to runtime support:

```text
put-on-top
put-on-bottom
selected target order
destinations carried in context
```

Full general reveal-and-route branching can remain later if tests/report show it still requires separate work.

---

## C1. Edit `effects.py` — use selected targets for put-on-top

Replace `_resolve_put_card_on_top()` with:

```python
    def _resolve_put_card_on_top(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Move selected/resolved cards to the top of their owners' decks.

        Lorcanito uses selected target order when the player supplied ordering.
        The last moved to index 0 becomes the final top card, so reverse selected
        order when placing multiple cards on top.
        """
        targets = tuple(context.current_targets or ())
        if not targets:
            targets = tuple(self._target_cards(state, effect, context, require_target=False))
        if not targets and context.choice is not None:
            targets = (int(context.choice),)

        for card_id in reversed(tuple(int(cid) for cid in targets)):
            if card_id not in state.cards:
                continue
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
                index=0,
            )
```

## C2. Edit `effects.py` — preserve ordering for put-on-bottom

Replace `_resolve_put_card_on_bottom()` with:

```python
    def _resolve_put_card_on_bottom(self, state: GameState, effect: EffectDef, context: EffectResolutionContext) -> None:
        """Move selected/resolved cards to the bottom of their owners' decks.

        For ordering: player-choice, current_targets carries the selected order.
        """
        source_raw = self._source_raw(effect)
        targets = tuple(context.current_targets or ())
        if not targets:
            targets = tuple(self._target_cards(state, effect, context, require_target=False))
        if not targets and context.choice is not None:
            targets = (int(context.choice),)

        # Keep supplied order for bottom movement. state.move_card(..., ZONE_DECK)
        # appends to deck bottom in current engine state movement semantics.
        for card_id in tuple(int(cid) for cid in targets):
            if card_id not in state.cards:
                continue
            self.engine._move_card_eventful(
                state,
                card_id,
                ZONE_DECK,
                actor=context.actor,
                source_id=context.source,
                controller=state.cards[card_id].owner,
            )
```

## C3. Update `resolution_requirements.py`

Update `_SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND`:

```python
_SUPPORTED_REQUIREMENTS_BY_EFFECT_KIND = {
    "scry": frozenset({
        "ordering",
        "destination",
    }),
    "put-on-bottom": frozenset({
        "ordering",
        "target",
    }),
    "put-on-top": frozenset({
        "ordering",
        "target",
    }),
}
```

Only add `destination` to put-on-top/bottom if you implement `context.destinations` movement rules for those exact effects. Otherwise, do not claim destination routing.

---

# Gate C validation

Run:

```bash
python3 -m py_compile \
  lorcana_bot/effects.py \
  lorcana_bot/card_logic/resolution_requirements.py \
  lorcana_bot/effect_types.py \
  lorcana_bot/engine.py
```

Targeted tests:

```bash
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_scry_search_reveal.py -q
python3 -m pytest tests/test_bag_resolution.py -q
```

Add tests:

```python
def test_put_on_bottom_preserves_current_target_order(...):
    # arrange two cards selected in specific order
    # resolve put_card_on_bottom with current_targets=(a,b)
    # assert deck bottom order follows selected order
```

```python
def test_put_on_top_preserves_current_target_order(...):
    # arrange two cards selected in specific order
    # resolve put_card_on_top with current_targets=(a,b)
    # assert final deck top order matches player-selected top order
```

---

# Final validation for the full Multifix

After all gates:

```bash
python3 -m py_compile \
  lorcana_bot/targeting.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/card_logic/resolution_requirements.py \
  lorcana_bot/effect_types.py \
  lorcana_bot/effects.py \
  lorcana_bot/engine.py \
  lorcana_bot/abilities.py \
  lorcana_bot/pending_effects.py
```

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
python3 -m pytest tests/test_activated_abilities_execution.py -q
python3 -m pytest tests/test_effects.py -q
python3 -m pytest tests/test_bag_resolution.py -q
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest tests/test_scry_search_reveal.py -q
python3 -m pytest tests/test_real_deck_runtime_executability.py -q
```

```bash
python3 -m pytest -q
```

Import check:

```bash
python3 - <<'PY'
from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards

db, report = import_lorcanito_source_cards(
    "data/lorcanito_runtime_extracted/cards.normalized.json"
)

print("cards:", len(db))
print("errors:", report.errors)
print("ability records:", report.ability_records_loaded)
print("unsupported:", report.unsupported_by_reason)
print("execution status counts:", report.execution_status_counts)
PY
```

Regenerate unsupported report:

```bash
python3 scripts/report_lorcanito_v2_unsupported.py
```

---

# Expected report movement

Because this is a routing Multifix, expected movement is spread across several buckets.

Expected decreases:

```text
unsupported_targeting
target:alias
target:selector
unsupported_choice for chosenBy: opponent
unsupported_engine_mechanic for move-to-location
```

Possible acceptable shifts:

```text
unsupported_condition may increase if routing unblocks effects that now expose if-you-do.
unsupported_cost may remain unchanged.
mapped_not_executable should remain mostly unchanged.
```

Red flags:

```text
errors must remain []
unsupported_targeting must not increase without clear deeper-blocker movement
unsupported_choice must not be reduced by suppressing chosenBy/opponent requirements
move-to-location must not silently resolve without a location target
opponent-choice must not let the controller choose the opponent's target
```

---

# Acceptance criteria

Accept this Multifix only if:

```text
1. Gate A targeted tests pass.
2. Gate B targeted tests pass.
3. Gate C targeted tests pass.
4. Full pytest passes.
5. Lorcanito import errors remain [].
6. No unsupported records are globally suppressed.
7. Raw Lorcanito source data remains preserved.
8. chosenBy: opponent creates opponent-owned pending input or equivalent opponent legal action.
9. move-to-location uses slotted_targets with subject/location roles.
10. put-on-top / put-on-bottom preserve selected target ordering.
11. unsupported_targeting and/or unsupported_choice decrease, or newly unblocked records clearly move to deeper true blockers.
```

---

# What still remains after this Multifix

Even if all three gates pass, these remain legitimate future workstreams:

```text
if-you-do / effect-result conditions
full arbitrary multi-prompt sequence orchestration
full destination routing for reveal-and-route branches
put-under / move-cards-from-under
cost routing for discardCardType, exertCharacters, banishItem, banishCharacter
full static/replacement executability
boost trigger
```

Do not jump to `if-you-do` until this routing Multifix has been validated, because `if-you-do` depends on reliable knowledge that the previous routed action actually happened.

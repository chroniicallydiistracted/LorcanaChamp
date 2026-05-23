# Microfix 19 — Lorcanito Target Alias and Filter Expansion

This guide starts from the current `main` baseline after Microfix 18.

Microfix 19 is intentionally narrow. It addresses remaining **targeting classification/runtime resolver gaps** that are directly visible in the current unsupported report and directly traceable to Lorcanito target enum expansion.

It does **not** implement multi-target routing, opponent-choice routing, static registry expansion, costs, or new engine mechanics.

---

# 1. Lorcanito source paths inspected

Inspected from the attached Lorcanito source package:

```text
lorcana/lorcana-types/src/abilities/target-types.ts
lorcana/lorcana-types/src/targeting/enum-expansions.ts
lorcana/lorcana-types/src/targeting/normalize.ts
lorcana/lorcana-engine/src/targeting/runtime/target-resolver.ts
lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/player-target-resolver.ts
```

Current LorcanaChamp paths inspected from `main`:

```text
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_summary.json
data/lorcanito_runtime_extracted/reports/unsupported/unsupported_report.md
lorcana_bot/targeting.py
lorcana_bot/importers/lorcanito_source_mapper.py
lorcana_bot/effects.py
tests/test_targeting.py
tests/test_source_projection_policy.py
```

---

# 2. Exact Lorcanito types/functions/mechanics found

## Lorcanito target enum expansion

Lorcanito expands enum aliases in:

```text
lorcana-types/src/targeting/enum-expansions.ts
```

Important exact expansions for this phase:

```ts
YOUR_CHOSEN_CHARACTER: {
  selector: "chosen",
  count: 1,
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
}

YOUR_CHOSEN_DAMAGED_CHARACTER: {
  selector: "chosen",
  count: 1,
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "status", status: "damaged" }],
}

CHOSEN_DAMAGED_OPPOSING_CHARACTER: {
  selector: "chosen",
  count: 1,
  owner: "opponent",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "status", status: "damaged" }],
}

CHOSEN_OPPOSING_DAMAGED_CHARACTER: {
  selector: "chosen",
  count: 1,
  owner: "opponent",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "status", status: "damaged" }],
}

CHOSEN_CHARACTER_OF_YOURS: {
  selector: "chosen",
  count: 1,
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
}

ANOTHER_CHOSEN_CHARACTER_OF_YOURS: {
  selector: "chosen",
  count: 1,
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
  excludeSelf: true,
}

YOUR_OTHER_SEVEN_DWARFS_CHARACTERS: {
  selector: "all",
  count: "all",
  owner: "you",
  zones: ["play"],
  cardTypes: ["character"],
  filters: [{ type: "has-classification", classification: "Seven Dwarfs" }],
  excludeSelf: true,
}

CHOSEN_CARD_IN_DISCARD: {
  selector: "chosen",
  count: 1,
  owner: "any",
  zones: ["discard"],
}

CHOSEN_CARD_FROM_DISCARD: {
  selector: "chosen",
  count: 1,
  owner: "any",
  zones: ["discard"],
}

CHALLENGING_PLAYER: {
  selector: "challenging-player",
}
```

## Lorcanito filter behavior

Lorcanito supports status filters:

```ts
{ type: "status", status: "damaged" }
{ type: "status", status: "exerted" }
{ type: "status", status: "ready" }
```

and uses `cardTypes: ["card"]` as a generic card wildcard for “chosen card from discard” style effects.

## Lorcanito runtime target resolver behavior

Lorcanito runtime resolves normalized descriptors, not just hard-coded aliases. Current Python already has a similar service in `lorcana_bot/targeting.py`; this phase only adds the missing enum expansions and filters that are safe with the existing resolver.

---

# 3. Current LorcanaChamp behavior

Current unsupported report after Microfix 18 shows targeting is the largest non-static runtime bucket:

```text
unsupported_targeting: 477
detailed unsupported_targeting: 668
```

The current top unsupported targeting examples include:

```text
CHALLENGING_PLAYER
YOUR_CHOSEN_CHARACTER
YOUR_OTHER_SEVEN_DWARFS_CHARACTERS
cardTypes: ["card"]
filter: [{ type: "status", status: "damaged" }]
```

Examples from the current report include Flynn Rider / Belle effects targeting `CHALLENGING_PLAYER`, Rapunzel targeting `YOUR_CHOSEN_CHARACTER`, Magic Broom using `cardTypes: ["card"]` in discard, and Stampede using Lorcanito status filters.

Current LorcanaChamp already supports many foundations:

```text
TargetDescriptor
TargetQueryContext
resolve_candidate_card_ids()
resolve_candidate_player_ids()
status-like damaged/exerted/ready filters
classification filters
keyword filters
chosen/all selectors
event payload-based trigger/challenge context
```

But current gaps are:

```text
1. Missing aliases in SOURCE mapper TARGET_MAP / SUPPORTED_TARGET_ALIASES.
2. Missing aliases/descriptors in targeting.SELECTOR_ALIASES / _create_descriptor_for_selector().
3. No player resolver for "challenging_player".
4. No "status" filter dispatch in _apply_filter().
5. "cardTypes": ["card"] is treated as an unsupported card type instead of wildcard.
```

---

# 4. Expected Lorcanito-aligned behavior

After Microfix 19:

```text
CHALLENGING_PLAYER -> challenging_player player selector
YOUR_CHOSEN_CHARACTER -> chosen one of your characters in play
YOUR_CHOSEN_DAMAGED_CHARACTER -> chosen damaged character of yours
CHOSEN_DAMAGED_OPPOSING_CHARACTER -> chosen damaged opposing character
CHOSEN_OPPOSING_DAMAGED_CHARACTER -> same
CHOSEN_CHARACTER_OF_YOURS -> chosen one of your characters
ANOTHER_CHOSEN_CHARACTER_OF_YOURS -> chosen one of your other characters
YOUR_OTHER_SEVEN_DWARFS_CHARACTERS -> all your other Seven Dwarfs characters
CHOSEN_CARD_IN_DISCARD / CHOSEN_CARD_FROM_DISCARD -> chosen card from discard
cardTypes ["card"] -> any card type wildcard
status filter -> damaged/exerted/ready/undamaged handling
```

The report should show a targeting decrease, but this phase intentionally does not solve:

```text
count: 2 chosen multi-target routing
chosenBy: opponent routing
for-each-opponent routing
location movement target slots
static/replacement registry execution
unsupported costs
if-you-do effect-result conditions
```

---

# 5. Files to modify

```text
lorcana_bot/targeting.py
lorcana_bot/importers/lorcanito_source_mapper.py

tests/test_targeting.py
tests/test_source_projection_policy.py
```

Do **not** modify engine runtime files in this phase unless the targeted tests reveal a real issue:

```text
lorcana_bot/engine.py
lorcana_bot/effects.py
lorcana_bot/pending_effects.py
```

---

# 6. Previous code and replacement code

## File 1 — `lorcana_bot/targeting.py`

### Change 1A — replace `SELECTOR_ALIASES`

Find the current `SELECTOR_ALIASES` block and replace it completely.

#### Previous code

```python
SELECTOR_ALIASES: dict[str, str] = {
    # Chosen targets (player selection)
    "chosen": "chosen",
    "chosen_character": "chosen_character",
    "chosen_exerted_character": "chosen_exerted_character",
    "chosen_card": "chosen_card",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    "all": "all",

    # Context-based targets
    "opposing_character": "opposing_character",
    "self": "self",
    "source": "self",
    "event_source": "event_source",
    "event_target": "event_target",
    "trigger_subject": "trigger_subject",
    "trigger_source": "trigger_source",
    "trigger_destination": "trigger_destination",
    "attacker": "attacker",
    "defender": "defender",
    "previous_target": "previous_target",
    "selected_first": "selected_first",
    "selected_all": "selected_all",

    # Character set targets
    "your_characters": "your_characters",
    "your_other_characters": "your_other_characters",
    "opposing_characters": "opposing_characters",
    "all_characters": "all_characters",

    # Character set with conditions
    "damaged_characters": "damaged_characters",
    "opposing_damaged_characters": "opposing_damaged_characters",

    # Player targets
    "chosen_player": "chosen_player",
    "you": "you",
    "controller": "you",
    "actor": "you",
    "opponent": "opponent",
    "each_player": "each_player",
}
```

#### Replacement code

```python
SELECTOR_ALIASES: dict[str, str] = {
    # Chosen targets (player selection)
    "chosen": "chosen",
    "chosen_character": "chosen_character",
    "chosen_exerted_character": "chosen_exerted_character",
    "chosen_card": "chosen_card",
    "chosen_item": "chosen_item",
    "chosen_location": "chosen_location",
    "chosen_opposing_character": "chosen_opposing_character",
    "chosen_damaged_character": "chosen_damaged_character",
    "chosen_opposing_damaged_character": "chosen_opposing_damaged_character",
    "chosen_damaged_opposing_character": "chosen_opposing_damaged_character",
    "chosen_character_in_discard": "chosen_character_in_discard",
    "chosen_card_in_discard": "chosen_card_from_discard",
    "chosen_card_from_discard": "chosen_card_from_discard",
    "chosen_card_from_hand": "chosen_card_from_hand",
    "your_chosen_character": "your_chosen_character",
    "your_chosen_damaged_character": "your_chosen_damaged_character",
    "your_chosen_item": "your_chosen_item",
    "another_chosen_character": "another_chosen_character",
    "another_chosen_character_of_yours": "another_chosen_character_of_yours",
    "all": "all",

    # Context-based targets
    "opposing_character": "opposing_character",
    "self": "self",
    "source": "self",
    "event_source": "event_source",
    "event_target": "event_target",
    "trigger_subject": "trigger_subject",
    "trigger_source": "trigger_source",
    "trigger_destination": "trigger_destination",
    "attacker": "attacker",
    "defender": "defender",
    "previous_target": "previous_target",
    "selected_first": "selected_first",
    "selected_all": "selected_all",

    # Character set targets
    "your_characters": "your_characters",
    "your_other_characters": "your_other_characters",
    "opposing_characters": "opposing_characters",
    "all_characters": "all_characters",
    "seven_dwarfs_characters": "seven_dwarfs_characters",
    "your_other_seven_dwarfs_characters": "your_other_seven_dwarfs_characters",

    # Character set with conditions
    "damaged_characters": "damaged_characters",
    "opposing_damaged_characters": "opposing_damaged_characters",

    # Player targets
    "chosen_player": "chosen_player",
    "you": "you",
    "controller": "you",
    "actor": "you",
    "opponent": "opponent",
    "each_player": "each_player",
    "challenging_player": "challenging_player",
}
```

---

### Change 1B — update `_PLAYER_SELECTORS`

#### Previous code

```python
_PLAYER_SELECTORS = frozenset({
    "chosen_player",
    "you",
    "opponent",
    "each_player",
})
```

#### Replacement code

```python
_PLAYER_SELECTORS = frozenset({
    "chosen_player",
    "you",
    "opponent",
    "each_player",
    "challenging_player",
})
```

---

### Change 1C — update `resolve_candidate_player_ids()`

Find this block:

```python
    if descriptor.selector == "each_player":
        return (0, 1)

    return ()
```

Replace with:

```python
    if descriptor.selector == "each_player":
        return (0, 1)

    if descriptor.selector == "challenging_player":
        player_id = _first_int_payload_value(
            context.event_payload,
            ("player_id", "playerId", "challenging_player", "challengingPlayer"),
        )
        if player_id in (0, 1):
            return (player_id,)

        attacker_id = _first_int_payload_value(
            context.event_payload,
            ("attacker_id", "attackerId", "challenger_id", "challengerId"),
        )
        if attacker_id is not None and attacker_id in state.cards:
            return (state.cards[attacker_id].controller,)

        return ()

    return ()
```

---

### Change 1D — update card type wildcard handling

Inside `is_card_target_candidate()`, find:

```python
    # Check card type restriction (requires engine for card def lookup)
    if descriptor.card_types and engine is not None:
        card_def = engine.card_def(state, card_id)
        if card_def.card_type not in descriptor.card_types:
            return False
```

Replace with:

```python
    # Check card type restriction (requires engine for card def lookup).
    # Lorcanito uses cardTypes: ["card"] as a wildcard for any card type.
    if descriptor.card_types and engine is not None:
        card_def = engine.card_def(state, card_id)
        if "card" not in descriptor.card_types and card_def.card_type not in descriptor.card_types:
            return False
```

---

### Change 1E — add descriptors in `_create_descriptor_for_selector()`

Find this block:

```python
    if selector == "chosen_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            filters=({"type": "damaged", "min": 1},),
        )

    if selector == "chosen_item":
```

Replace with:

```python
    if selector == "chosen_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            filters=({"type": "damaged", "min": 1},),
        )

    if selector == "chosen_opposing_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            controller="opponent",
            filters=({"type": "status", "status": "damaged"},),
        )

    if selector == "your_chosen_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
        )

    if selector == "your_chosen_damaged_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "status", "status": "damaged"},),
        )

    if selector == "another_chosen_character":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
            exclude_self=True,
        )

    if selector == "another_chosen_character_of_yours":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            exclude_self=True,
        )

    if selector == "chosen_character_in_discard":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_DISCARD,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "chosen_card_from_discard":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_DISCARD,),
            owner="any",
        )

    if selector == "chosen_card_from_hand":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_HAND,),
            owner="any",
        )

    if selector == "chosen_item":
```

---

### Change 1F — add `your_chosen_item`

Find:

```python
    if selector == "chosen_item":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_ITEM,),
            owner="any",
        )
```

Replace with:

```python
    if selector == "chosen_item":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_ITEM,),
            owner="any",
        )

    if selector == "your_chosen_item":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            zones=(ZONE_PLAY,),
            card_types=(CARD_ITEM,),
            owner="you",
        )
```

---

### Change 1G — add Seven Dwarfs descriptors

Find this block:

```python
    if selector == "all_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "damaged_characters":
```

Replace with:

```python
    if selector == "all_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="any",
        )

    if selector == "seven_dwarfs_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            filters=({"type": "has-classification", "classification": "Seven Dwarfs"},),
        )

    if selector == "your_other_seven_dwarfs_characters":
        return TargetDescriptor(
            selector=selector,
            min_count=0,
            max_count=_PLURAL_SELECTOR_MAX,
            zones=(ZONE_PLAY,),
            card_types=(CARD_CHARACTER,),
            owner="you",
            exclude_self=True,
            filters=({"type": "has-classification", "classification": "Seven Dwarfs"},),
        )

    if selector == "damaged_characters":
```

---

### Change 1H — add `challenging_player` descriptor

Find:

```python
    if selector == "each_player":
        return TargetDescriptor(
            selector=selector,
            min_count=2,
            max_count=2,
            allow_players=True,
        )

    return None
```

Replace with:

```python
    if selector == "each_player":
        return TargetDescriptor(
            selector=selector,
            min_count=2,
            max_count=2,
            allow_players=True,
        )

    if selector == "challenging_player":
        return TargetDescriptor(
            selector=selector,
            min_count=1,
            max_count=1,
            allow_players=True,
        )

    return None
```

---

### Change 1I — support Lorcanito `status` filters

Inside `_apply_filter()`, find:

```python
    if filter_type == "damaged":
        min_damage = filter_def.get("min", 1)
        return inst.damage >= min_damage

    if filter_type == "exerted":
        return inst.exerted

    if filter_type == "ready":
        return not inst.exerted
```

Replace with:

```python
    if filter_type == "status":
        status = str(filter_def.get("status") or "").replace("_", "-").lower()
        if status == "damaged":
            min_damage = filter_def.get("min", 1)
            return inst.damage >= min_damage
        if status == "undamaged":
            return inst.damage <= 0
        if status == "exerted":
            return inst.exerted
        if status == "ready":
            return not inst.exerted
        return False

    if filter_type == "damaged":
        min_damage = filter_def.get("min", 1)
        return inst.damage >= min_damage

    if filter_type == "undamaged":
        return inst.damage <= 0

    if filter_type == "exerted":
        return inst.exerted

    if filter_type == "ready":
        return not inst.exerted
```

---

### Change 1J — update explicit-target detection

Find:

```python
def requires_explicit_target_selection(selector: str) -> bool:
    """Return True when *selector* requires a player target choice.

    Lorcanito represents these prompts as selector="chosen".  The Python
    migration still carries a small set of legacy singleton aliases; keep that
    mapping centralized so engine and protection behavior do not drift.
    """
    return selector.startswith("chosen") or selector == "opposing_character"
```

Replace with:

```python
def requires_explicit_target_selection(selector: str) -> bool:
    """Return True when *selector* requires a player target choice.

    Lorcanito represents these prompts as selector="chosen".  The Python
    migration still carries enum-expanded aliases such as YOUR_CHOSEN_CHARACTER
    and ANOTHER_CHOSEN_CHARACTER_OF_YOURS; keep that mapping centralized so
    engine and protection behavior do not drift.
    """
    return (
        selector.startswith("chosen")
        or selector.startswith("your_chosen")
        or selector.startswith("another_chosen")
        or selector == "opposing_character"
    )
```

---

## File 2 — `lorcana_bot/importers/lorcanito_source_mapper.py`

### Change 2A — update `TARGET_MAP`

Find the `TARGET_MAP = { ... }` block and add these entries in the existing dictionary.

#### Add after:

```python
    "CHOSEN_CHARACTER": "chosen_character",
```

Add:

```python
    "CHOSEN_CHARACTER_OF_YOURS": "your_chosen_character",
    "YOUR_CHOSEN_CHARACTER": "your_chosen_character",
    "YOUR_CHOSEN_DAMAGED_CHARACTER": "your_chosen_damaged_character",
    "ANOTHER_CHOSEN_CHARACTER": "another_chosen_character",
    "ANOTHER_CHOSEN_CHARACTER_OF_YOURS": "another_chosen_character_of_yours",
```

#### Find:

```python
    "CHOSEN_DAMAGED_CHARACTER": "chosen_character",
```

Replace with:

```python
    "CHOSEN_DAMAGED_CHARACTER": "chosen_damaged_character",
    "CHOSEN_DAMAGED_OPPOSING_CHARACTER": "chosen_opposing_damaged_character",
    "CHOSEN_OPPOSING_DAMAGED_CHARACTER": "chosen_opposing_damaged_character",
```

#### Add after:

```python
    "CHOSEN_CARD_FROM_DISCARD": "chosen_card_from_discard",
```

Add:

```python
    "CHOSEN_CARD_IN_DISCARD": "chosen_card_from_discard",
    "CHOSEN_CHARACTER_IN_DISCARD": "chosen_character_in_discard",
```

#### Add after:

```python
    "CHOSEN_PLAYER": "chosen_player",
```

Add:

```python
    "CHALLENGING_PLAYER": "challenging_player",
```

#### Add after:

```python
    "YOUR_OTHER_EVASIVE_CHARACTERS": "your_other_evasive_characters",
```

Add:

```python
    "SEVEN_DWARFS_CHARACTERS": "seven_dwarfs_characters",
    "YOUR_OTHER_SEVEN_DWARFS_CHARACTERS": "your_other_seven_dwarfs_characters",
    "YOUR_CHOSEN_ITEM": "your_chosen_item",
```

---

### Change 2B — update `SUPPORTED_TARGET_ALIASES`

Inside `SUPPORTED_TARGET_ALIASES`, add the same raw Lorcanito aliases.

#### Add after:

```python
    "CHOSEN_CHARACTER",
```

Add:

```python
    "CHOSEN_CHARACTER_OF_YOURS",
    "YOUR_CHOSEN_CHARACTER",
    "YOUR_CHOSEN_DAMAGED_CHARACTER",
    "ANOTHER_CHOSEN_CHARACTER",
    "ANOTHER_CHOSEN_CHARACTER_OF_YOURS",
```

#### Add after:

```python
    "CHOSEN_DAMAGED_CHARACTER",
```

Add:

```python
    "CHOSEN_DAMAGED_OPPOSING_CHARACTER",
    "CHOSEN_OPPOSING_DAMAGED_CHARACTER",
```

#### Add after:

```python
    "CHOSEN_CARD_FROM_DISCARD",
```

Add:

```python
    "CHOSEN_CARD_IN_DISCARD",
    "CHOSEN_CHARACTER_IN_DISCARD",
```

#### Add after:

```python
    "CHOSEN_PLAYER",
```

Add:

```python
    "CHALLENGING_PLAYER",
```

#### Add after:

```python
    "YOUR_OTHER_EVASIVE_CHARACTERS",
```

Add:

```python
    "SEVEN_DWARFS_CHARACTERS",
    "YOUR_OTHER_SEVEN_DWARFS_CHARACTERS",
    "YOUR_CHOSEN_ITEM",
```

---

### Change 2C — allow Lorcanito wildcard `cardTypes: ["card"]`

Inside `_source_target_shape_supported()`, find this line in the `selector == "all"` branch:

```python
        if any(card_type not in {"character", "item", "location", "action"} for card_type in card_types):
            return False
```

Replace with:

```python
        if any(card_type not in {"card", "character", "item", "location", "action"} for card_type in card_types):
            return False
```

Then find the same line in the `selector == "chosen"` branch:

```python
    if any(card_type not in {"character", "item", "location", "action"} for card_type in card_types):
        return False
```

Replace with:

```python
    if any(card_type not in {"card", "character", "item", "location", "action"} for card_type in card_types):
        return False
```

---

### Change 2D — allow Lorcanito `status` filters

Inside `_target_filters_supported()`, find:

```python
    supported = {
        None,
        "damaged",
        "exerted",
        "ready",
```

Replace with:

```python
    supported = {
        None,
        "status",
        "damaged",
        "undamaged",
        "exerted",
        "ready",
```

---

# 7. Tests to add/update

## File 3 — `tests/test_targeting.py`

### Change 3A — add alias normalization cases

Inside the existing parametrized list in:

```python
test_normalize_target_descriptor_supports_required_aliases
```

Add these entries after the existing `chosen_damaged_character` case and before `opposing_character`:

```python
        (
            "chosen_opposing_damaged_character",
            {
                "card_types": (CARD_CHARACTER,),
                "controller": "opponent",
                "filters": ({"type": "status", "status": "damaged"},),
            },
        ),
        ("your_chosen_character", {"card_types": (CARD_CHARACTER,), "owner": "you"}),
        (
            "your_chosen_damaged_character",
            {
                "card_types": (CARD_CHARACTER,),
                "owner": "you",
                "filters": ({"type": "status", "status": "damaged"},),
            },
        ),
        (
            "another_chosen_character_of_yours",
            {"card_types": (CARD_CHARACTER,), "owner": "you", "exclude_self": True},
        ),
        ("chosen_card_from_discard", {"zones": (ZONE_DISCARD,), "owner": "any"}),
```

Add this entry near the existing player target entries:

```python
        ("challenging_player", {"allow_players": True}),
```

Add this entry near the existing character set target entries:

```python
        (
            "your_other_seven_dwarfs_characters",
            {
                "card_types": (CARD_CHARACTER,),
                "owner": "you",
                "exclude_self": True,
                "filters": ({"type": "has-classification", "classification": "Seven Dwarfs"},),
                "max_count": None,
            },
        ),
```

---

### Change 3B — add resolver tests

Place these tests after:

```python
def test_lorcanito_context_ref_targets_resolve_from_event_context(self, engine, state):
```

and before:

```python
def test_player_selectors_return_no_card_ids(self, engine, state):
```

Add:

```python
    def test_challenging_player_resolves_from_challenge_payload(self, engine, state):
        attacker = put_card(state, engine, 0, "Ruby Charger", ZONE_PLAY)
        desc = normalize_target_descriptor("challenging_player")
        ctx = TargetQueryContext(actor=1, event_payload={"attacker_id": attacker})

        assert resolve_candidate_player_ids(state, desc, ctx) == (0,)

    def test_status_filter_matches_lorcanito_status_damaged(self, engine, state):
        damaged = put_card(state, engine, 0, "Amber Guard", ZONE_PLAY)
        undamaged = put_card(state, engine, 0, "Amber Recruit", ZONE_PLAY, exclude=frozenset({damaged}))
        state.cards[damaged].damage = 2
        state.cards[undamaged].damage = 0

        desc = normalize_target_descriptor({
            "selector": "chosen",
            "count": 1,
            "owner": "you",
            "zones": [ZONE_PLAY],
            "cardTypes": [CARD_CHARACTER],
            "filter": [{"type": "status", "status": "damaged"}],
        })
        ctx = TargetQueryContext(actor=0)

        assert resolve_candidate_card_ids(state, engine, desc, ctx) == (damaged,)

    def test_card_type_card_is_wildcard_for_discard_card_targets(self, engine, state):
        character = put_card(state, engine, 0, "Amber Guard", ZONE_DISCARD)
        item = put_card(state, engine, 0, "Steel Cannon", ZONE_DISCARD, exclude=frozenset({character}))

        desc = normalize_target_descriptor({
            "selector": "chosen",
            "count": 1,
            "owner": "any",
            "zones": [ZONE_DISCARD],
            "cardTypes": ["card"],
        })
        ctx = TargetQueryContext(actor=0)

        assert set(resolve_candidate_card_ids(state, engine, desc, ctx)) == {character, item}
```

---

### Change 3C — update explicit target selection test

Find the test for explicit target selectors. It should contain assertions around `requires_explicit_target_selection`.

Add these assertions to that test:

```python
    assert requires_explicit_target_selection("your_chosen_character")
    assert requires_explicit_target_selection("your_chosen_damaged_character")
    assert requires_explicit_target_selection("another_chosen_character_of_yours")
```

If the file does not currently import `requires_explicit_target_selection`, add it to the import block from `lorcana_bot.targeting`.

#### Previous import fragment

```python
from lorcana_bot.targeting import (
    TargetCandidate,
```

#### Replacement import fragment

```python
from lorcana_bot.targeting import (
    TargetCandidate,
```

No visible change there; inside the same import list add:

```python
    requires_explicit_target_selection,
```

near the other imported functions.

---

## File 4 — `tests/test_source_projection_policy.py`

### Change 4A — add mapper/projection tests

Place these tests at the bottom of the file, after:

```python
def test_lorcanito_scry_destination_action_projects_to_engine_effect():
```

Add:

```python
def test_microfix19_lorcanito_player_target_alias_challenging_player_maps_executable():
    ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "challenged", "on": "SELF", "timing": "whenever"},
        "effect": {
            "type": "discard",
            "target": "CHALLENGING_PLAYER",
            "amount": 1,
            "chosen": True,
            "from": "hand",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE

    card = CardDef(
        "challenging_player_card",
        "Challenging Player Card",
        "emerald",
        2,
        True,
        "character",
        strength=1,
        willpower=3,
        lore=1,
        source_abilities=(ability,),
    )

    assert card.source_abilities[0].effects[0].target.alias == "CHALLENGING_PLAYER"


def test_microfix19_lorcanito_your_chosen_character_alias_projects():
    ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "remove-damage",
            "amount": {"type": "up-to", "value": 3},
            "target": "YOUR_CHOSEN_CHARACTER",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE

    effects = project_action_effects(_card(ability))

    assert len(effects) == 1
    assert effects[0].kind == "remove_damage"
    assert effects[0].target == "your_chosen_character"


def test_microfix19_lorcanito_status_filter_and_card_wildcard_project():
    status_ability = map_raw_ability({
        "type": "action",
        "effect": {
            "type": "deal-damage",
            "amount": 2,
            "target": {
                "selector": "chosen",
                "count": 1,
                "owner": "any",
                "zones": ["play"],
                "cardTypes": ["character"],
                "filter": [{"type": "status", "status": "damaged"}],
            },
        },
    })
    wildcard_ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "play", "on": "SELF", "timing": "when"},
        "effect": {
            "type": "shuffle-into-deck",
            "target": {
                "selector": "chosen",
                "count": 1,
                "owner": "any",
                "zones": ["discard"],
                "cardTypes": ["card"],
            },
        },
    })

    assert status_ability.execution_status == ExecutionStatus.EXECUTABLE
    assert wildcard_ability.execution_status == ExecutionStatus.EXECUTABLE
    assert status_ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE
    assert wildcard_ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE


def test_microfix19_lorcanito_seven_dwarfs_alias_maps_executable():
    ability = map_raw_ability({
        "type": "triggered",
        "trigger": {"event": "banish", "on": "SELF", "timing": "when"},
        "effect": {
            "type": "modify-stat",
            "stat": "strength",
            "modifier": 2,
            "duration": "until-start-of-next-turn",
            "target": "YOUR_OTHER_SEVEN_DWARFS_CHARACTERS",
        },
    })

    assert ability.execution_status == ExecutionStatus.EXECUTABLE
    assert ability.effects[0].target is not None
    assert ability.effects[0].target.execution_status == ExecutionStatus.EXECUTABLE
```

---

# 8. Validation commands

Run targeted compile:

```bash
python3 -m py_compile \
  lorcana_bot/targeting.py \
  lorcana_bot/importers/lorcanito_source_mapper.py \
  lorcana_bot/effects.py \
  lorcana_bot/engine.py
```

Run targeted tests:

```bash
python3 -m pytest tests/test_targeting.py -q
python3 -m pytest tests/test_source_projection_policy.py -q
```

Run nearby safety tests:

```bash
python3 -m pytest tests/test_scry_search_reveal.py -q
python3 -m pytest tests/test_trigger_projection.py -q
python3 -m pytest tests/test_trigger_state.py -q
python3 -m pytest tests/test_effects.py -q
```

Run full suite:

```bash
python3 -m pytest -q
```

Run import check:

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

# 9. Expected unsupported-report delta

Starting Microfix 19 baseline:

```text
unsupported_targeting: 477
detailed unsupported_targeting: 668
target:alias: 83
target:selector: 100
target:object: 8
```

Expected after this phase:

```text
unsupported_targeting should decrease.
CHALLENGING_PLAYER target alias records should disappear or drop sharply.
YOUR_CHOSEN_CHARACTER target alias records should disappear or drop sharply.
YOUR_OTHER_SEVEN_DWARFS_CHARACTERS target alias records should disappear or drop sharply.
cardTypes ["card"] selector records should decrease.
status filter selector records should decrease.
```

Do not expect this phase to solve:

```text
chosenBy: opponent
count: 2 chosen target routing
for-each-opponent
move-to-location
put-under / move-cards-from-under
static mapped_not_executable
if-you-do conditions
selected-object costs
```

Possible acceptable side effects:

```text
unsupported_choice may increase slightly if previously blocked target records now reach opponent-choice routing.
unsupported_condition may increase slightly if previously blocked target records now reach if-you-do/result conditions.
unsupported_engine_mechanic may increase slightly if previously blocked target records now reach unimplemented effects.
```

That is acceptable only if `errors` remains `[]` and `unsupported_targeting` decreases.

---

# 10. Acceptance criteria

Accept Microfix 19 only if:

```text
1. py_compile passes.
2. Targeted tests pass.
3. Nearby safety tests pass.
4. Full pytest passes.
5. v2 import still has errors: [].
6. unsupported_targeting decreases.
7. No runtime engine files are modified unless targeted tests prove they must be.
8. No raw source data is removed or hidden.
9. No broad unsupported categories are suppressed globally.
```

---

# Notes for validation interpretation

This phase expands **known Lorcanito target aliases and filters**. It does not make all target selectors executable. The mapper should still reject ambiguous bare targets like:

```json
{"selector": "chosen"}
```

and should still reject unsupported complex filters not handled by the runtime resolver.

Do not add support for `count: 2` or `{ exactly: 2 }` in this microfix unless you also implement complete multi-target legal-action enumeration and resolution for those effects. That belongs in a later phase.

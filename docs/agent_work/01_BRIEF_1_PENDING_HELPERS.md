# TECHNICAL IMPLEMENTATION BRIEF 1 — Add Missing Pending Requirement Resolvers

Goal:
Add minimal named-card and destination-choice resolvers in `pending_effects.py` so engine dispatch can route every existing `PENDING_REQUIREMENT_KINDS` entry that is currently intended to be resolvable.

Do not modify `engine.py` in this brief.
Do not modify tests in this brief unless import fallout requires it.

---

### 1. Current Incorrect Code

* **File Path:** `lorcana_bot/pending_effects.py`
* **Line Range:** `Lines 880-912`
* **Snippet:**
```python
def resolve_reveal_routing(
    state: GameState,
    pending_id: str,
    destination: str | None = None,
) -> None:
    """Resolve a reveal routing pending effect.

    Args:
        state: Game state
        pending_id: Pending effect ID
        destination: Chosen destination if not fixed

    Raises:
        ValueError: If destination is required but not provided
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    req = pe.raw.get("requirement")
    if not isinstance(req, RevealRoutingRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a reveal routing")

    # Determine final destination
    final_dest = destination if destination else req.destination
    if final_dest is None:
        raise ValueError("Destination required but not provided")

    # Reveal and move cards
    for cid in req.card_ids:
        # Mark as revealed
        state.cards[cid].revealed = True
```

### 2. Expected Code (The Solution)

* **Target State:**
```python
def resolve_reveal_routing(
    state: GameState,
    pending_id: str,
    destination: str | None = None,
) -> None:
    """Resolve a reveal routing pending effect.

    Args:
        state: Game state
        pending_id: Pending effect ID
        destination: Chosen destination if not fixed

    Raises:
        ValueError: If destination is required but not provided
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    req = pe.raw.get("requirement")
    if not isinstance(req, RevealRoutingRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a reveal routing")

    # Determine final destination
    final_dest = destination if destination else req.destination
    if final_dest is None:
        raise ValueError("Destination required but not provided")

    # Reveal and move cards
    for cid in req.card_ids:
        # Mark as revealed
        state.cards[cid].revealed = True

        # Emit reveal event - use GameEvent for consistency
        from lorcana_bot.state import GameEvent
        state.event_log.append(GameEvent(
            event_type="CARD_REVEALED",
            actor=req.chooser_id,
            source=cid,
            target=None,
            payload={
                "card_id": cid,
                "card_def_id": state.cards[cid].card_id,
                "reveal_policy": req.reveal_policy,
            },
        ))

        # Move to destination
        state.move_card(cid, final_dest)


def resolve_named_card(
    state: GameState,
    pending_id: str,
    named_card: str,
) -> None:
    """Resolve a pending name-a-card requirement.

    Stores the named card in pending raw resolution input. Later effects may
    consume this value through event/pending context.
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    requirement_kind = pe.raw.get("requirement_kind")
    req = pe.raw.get("requirement")
    if requirement_kind != "named_card" and not isinstance(req, NamedCardRequirement):
        raise ValueError(f"Pending effect {pending_id} is not a named-card requirement")

    if isinstance(req, NamedCardRequirement) and req.valid_card_def_ids:
        if named_card not in req.valid_card_def_ids:
            raise ValueError(f"Named card {named_card!r} is not valid for pending effect {pending_id}")

    pe.raw["named_card"] = named_card
    pe.raw.setdefault("resolution_input", {})["named_card"] = named_card


def resolve_destination_choice(
    state: GameState,
    pending_id: str,
    destination: str,
) -> None:
    """Resolve a generic destination-choice pending requirement.

    This records the chosen destination. Movement is performed by the effect
    that consumes the pending resolution input unless a more specific helper
    such as resolve_reveal_routing handles movement directly.
    """
    pe = get_pending_effect_by_id(state, pending_id)
    if pe is None:
        raise ValueError(f"Pending effect {pending_id} not found")

    requirement_kind = pe.raw.get("requirement_kind")
    req = pe.raw.get("requirement")
    if requirement_kind != "destination":
        raise ValueError(f"Pending effect {pending_id} is not a destination requirement")

    options = (
        pe.raw.get("destination_options")
        or getattr(req, "destination_options", None)
        or getattr(req, "options", None)
        or ()
    )
    if options and destination not in tuple(options):
        raise ValueError(f"Destination {destination!r} is not valid for pending effect {pending_id}")

    pe.raw["destination"] = destination
    pe.raw.setdefault("resolution_input", {})["destination"] = destination
```

### 3. Fixes Needed

* **Action:** `EXPAND`
* **Delta Description:** Add two resolver functions after `resolve_reveal_routing()`: `resolve_named_card()` and `resolve_destination_choice()`. These functions must validate the pending effect exists, validate the requirement kind, store the selected value in `pe.raw`, and write the value into `pe.raw["resolution_input"]`.

### 4. Lorcanito Source Reference (The Authority)

* **Reference File:** `packages/lorcana/lorcana-engine/src/runtime-moves/resolution/action-effects/pending-action-effects.ts`
* **Line Range:** `Pending action effect input persistence sections`
* **Logic Context:**
```typescript
// Lorcanito stores player-provided resolution input on pending effects and
// resumes effect resolution with that resolution input instead of guessing.
type PendingActionResolutionInput = {
  targets?: unknown;
  choice?: number;
  namedCard?: string;
  destination?: string;
  eventSnapshot?: Record<string, unknown>;
};
```

### 5. Acceptance Check(s)

Run:
```bash
python3 -m pytest tests/test_pending_effects.py -q
python3 -m pytest -q
```

Manual checks:
```bash
grep -n "def resolve_named_card" lorcana_bot/pending_effects.py
grep -n "def resolve_destination_choice" lorcana_bot/pending_effects.py
```

Expected:
- `resolve_named_card()` exists.
- `resolve_destination_choice()` exists.
- Existing pending effect tests pass.
- No engine behavior changes yet.

### 6. Final Response Requirements

The implementation agent must report:
1. Files changed.
2. Whether `resolve_named_card()` was added.
3. Whether `resolve_destination_choice()` was added.
4. Whether both write into `pe.raw["resolution_input"]`.
5. Exact pytest commands run and results.
6. Confirmation that `engine.py` was not modified.

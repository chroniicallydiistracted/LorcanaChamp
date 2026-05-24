# LorcanaChamp v2 Kernel Implementation 3 - Turn-Action Ink Parity, Pending/Bag Blockers, and Lorcanito Card Meta

## Phase name

`V2 Kernel Implementation 3: Lorcanito Turn-Action Ink Parity, Pending/Bag Blockers, and Card Meta Migration`

## Scope decision

This phase is the required larger refactor after Phase 2. The current inkwell move proves a move pipeline, but it still preserves several scaffold-era shortcuts:

```text
CardMeta.exerted / CardMeta.drying
single base inkwell action only
hand-only inking
no pending action effect blocker
no triggered bag blocker
no command state-id validation
```

Lorcanito does not model those concepts this way. This phase replaces the wrong v2 fields and adds the missing Lorcanito turn-action gates before building play-card, quest, challenge, triggers, or unsupported-report movement.

Do not preserve the old card-meta names as public API. They conflict with Lorcanito. Tests that read `meta.exerted` or `meta.drying` must be rewritten to assert `meta.state` and `meta.is_drying`.

---

# 1. Lorcanito source findings

## Files inspected

```text
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.commands.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.validation.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/types.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/core/runtime/zone-operations.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/resources.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-action-ink.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/runtime-card-derived.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/runtime-moves/state/turn-metrics.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/types/runtime-state.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/derived-state.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/rules/static-effect-registry.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/triggered-abilities/index.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-engine/src/flow/runtime-flow-config.ts
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana/lorcana-cards/src/cards/001/characters/142-belle-strange-but-special.ts
```

## Confirmed Lorcanito behavior

### A. Runtime card meta uses Lorcanito fields

`types/runtime-state.ts` defines `LorcanaCardMeta` with:

```text
state?: "ready" | "exerted"
damage?: number
isDrying?: boolean
publicFaceState?: "faceUp" | "faceDown"
atLocationId?: CardInstanceId
cardsUnder?: CardInstanceId[]
stackParentId?: CardInstanceId
playedViaShift?: boolean
playedCostType?: ...
```

The v2 Python field names should be Pythonic but must map to these exact concepts:

```text
state
damage
is_drying
public_face_state
at_location_id
cards_under
stack_parent_id
played_via_shift
played_cost_type
```

### B. Command execution validates before execution

`match-runtime.commands.ts` calls `validateCommand` before move execution. `match-runtime.validation.ts` rejects:

```text
missing input
stale state ID
game already ended
unknown move
server-only move from player
flow-disallowed move
non-priority actor
move-specific validation failure
```

This phase implements the state-id and game-ended checks in the Python move service. Full flow/server-only validation belongs to the next runtime-flow phase.

### C. `putCardIntoInkwell` is blocked by pending effects and bag items

`runtime-moves/moves/core/resources.ts` starts validation with:

```text
validateNoPendingEffects(ctx, { actionLabel: "ink cards" })
```

The same file uses `hasAnyPendingEffects(ctx)` in `available`. Lorcanito also blocks regular turn actions while bag effects are waiting through the same pending-decision model used by play-card and pass-turn.

### D. Turn-action ink limit is not always one

`runtime-moves/state/turn-action-ink.ts` defines:

```text
BASE_TURN_ACTION_INK_LIMIT = 1
limit = 1 + temporary additionalInkwellActions + static additional-inkwell effects
canInkThisTurn = inkedThisTurn.length < limit
```

Belle - Strange but Special (`6qy` / `Mfr`) has a real Lorcanito static effect:

```json
{"type": "additional-inkwell", "amount": 1}
```

That real card must allow two hand-to-inkwell turn actions while it is controlled in play.

### E. Inkwell candidates include hand and discard

`runtime-card-derived.ts` defines:

```text
INKWELL_CANDIDATE_QUERY_DSL = { owner: "you", zones: ["hand", "discard"] }
```

`derived-state.ts` only allows discard inking if a controlled static grants discard inkability. Moana - Curious Explorer (`wRv` / `uQE`) has:

```json
{"type": "grant-discard-inkability"}
```

Without that static source in play, discard cards must still be rejected with Lorcanito's `CARD_NOT_IN_HAND` validation path.

### F. Execution still moves to inkwell ready and face down

`resources.ts` execution:

```text
moveCard(cardId, { zone: "inkwell", playerId })
patchMeta(cardId, { state: "ready", publicFaceState: "faceDown" })
reveal briefly
append G.turnMetadata.inkedThisTurn
record cardsPutIntoInkwellThisTurn metric
emit cardInked trigger and flush to bag
```

This phase updates meta and turn metrics. It does not implement reveal windows or trigger flushing yet. Those are explicitly Phase 5/6 work and must not be claimed in unsupported reports.

---

# 2. Current LorcanaChamp v2 findings

## Files inspected

```text
lorcana_engine_v2/core/commands.py
lorcana_engine_v2/core/context.py
lorcana_engine_v2/core/events.py
lorcana_engine_v2/core/results.py
lorcana_engine_v2/core/runtime.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/core/zones.py
lorcana_engine_v2/moves/available_moves.py
lorcana_engine_v2/moves/ink.py
lorcana_engine_v2/moves/registry.py
lorcana_engine_v2/moves/specs.py
lorcana_engine_v2/registries/static_registry.py
lorcana_engine_v2/resolution/bag.py
lorcana_engine_v2/resolution/pending.py
lorcana_engine_v2/rules/derived_state.py
lorcana_engine_v2/rules/target_resolver.py
tests/v2/helpers.py
tests/v2/test_card_runtime_query_api_v2.py
tests/v2/test_first_real_card_parity_v2.py
tests/v2/test_put_card_into_inkwell_move_v2.py
tests/v2/test_static_registry_v2.py
```

## Current behavior

The current v2 kernel has Phase 1 and Phase 2 foundations:

```text
immutable card catalog
immutable card instance registry
owner-scoped zone state
runtime query API
move registry
putCardIntoInkwell from hand
real-card inkwell tests
```

The current test suite passes:

```text
pytest -q tests/v2
30 passed
```

## Exact mismatch or missing logic

```text
1. CardMeta stores scaffold fields `exerted` and `drying` instead of Lorcanito meta concepts.
2. TurnMetadata only tracks `inked_this_turn`; it lacks cardsPutIntoInkwellThisTurn and additionalInkwellActions.
3. GameState has no pending action effect state and no triggered bag state.
4. resolution/pending.py and resolution/bag.py are empty scaffolds.
5. putCardIntoInkwell only enumerates hand cards.
6. putCardIntoInkwell ignores Belle-style additional inkwell static allowance.
7. putCardIntoInkwell ignores Moana-style discard inkability.
8. putCardIntoInkwell does not reject pending effects or bag items.
9. Command has no optional state_id, so stale-state validation cannot be represented.
10. TransitionResult has no error code, so Lorcanito-style validation codes are lost.
```

## Required larger refactor

This phase must replace the meta model and the inkwell validation path. Do not keep `CardMeta.exerted` or `CardMeta.drying` as public fields. Any compatibility must be isolated in tests or adapters; the v2 kernel should use `state` and `is_drying`.

---

# 3. Required implementation actions

## Files to replace

```text
lorcana_engine_v2/core/commands.py
lorcana_engine_v2/core/context.py
lorcana_engine_v2/core/results.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/core/zones.py
lorcana_engine_v2/moves/available_moves.py
lorcana_engine_v2/moves/ink.py
lorcana_engine_v2/registries/static_registry.py
lorcana_engine_v2/resolution/bag.py
lorcana_engine_v2/resolution/pending.py
lorcana_engine_v2/rules/derived_state.py
lorcana_engine_v2/rules/target_resolver.py
tests/v2/test_card_runtime_query_api_v2.py
tests/v2/test_put_card_into_inkwell_move_v2.py
```

## Files not to touch in this phase

```text
lorcana_engine_v2/moves/play.py
lorcana_engine_v2/moves/quest.py
lorcana_engine_v2/moves/challenge.py
lorcana_engine_v2/effects/*
lorcana_engine_v2/projections/unsupported_report.py
```

Those need later phases. Moving unsupported report counts after this phase would be wrong because trigger flushing, action resolution, play-card, quest, and challenge are still not executable.

---

# 4. Full copy-paste implementation code

## Replace `lorcana_engine_v2/core/zones.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from .ids import InstanceId, PlayerId, ZoneId


@dataclass(frozen=True, slots=True)
class ZoneConfig:
    id: ZoneId
    name: str
    visibility: str
    ordered: bool
    owner_scoped: bool
    face_down: bool = False
    max_size: int | None = None


@dataclass(frozen=True, slots=True)
class PublicZoneSummary:
    revision: int = 0
    count: int = 0
    top_public_card_id: InstanceId | None = None


@dataclass(frozen=True, slots=True)
class ZoneCardIndexEntry:
    zone_key: ZoneId
    index: int | None
    owner_id: PlayerId
    controller_id: PlayerId


@dataclass(frozen=True, slots=True)
class CardMeta:
    """Python mirror of Lorcanito LorcanaCardMeta.

    Do not reintroduce scaffold fields named `exerted` or `drying`.
    Lorcanito stores ready/exerted as `state` and drying as `isDrying`.
    """
    state: str | None = None
    damage: int = 0
    is_drying: bool = False
    public_face_state: str | None = None
    at_location_id: InstanceId | None = None
    stack_parent_id: InstanceId | None = None
    cards_under: tuple[InstanceId, ...] = ()
    played_via_shift: bool | None = None
    played_cost_type: str | None = None
    flags: Mapping[str, object] = field(default_factory=dict)

    def with_updates(self, **updates: object) -> "CardMeta":
        return replace(self, **updates)

    def is_ready(self) -> bool:
        return self.state != "exerted"

    def is_exerted(self) -> bool:
        return self.state == "exerted"


@dataclass(frozen=True, slots=True)
class ZoneRuntimeState:
    zone_cards: Mapping[ZoneId, tuple[InstanceId, ...]]
    card_index: Mapping[InstanceId, ZoneCardIndexEntry]
    card_meta: Mapping[InstanceId, CardMeta]
    zone_summaries: Mapping[ZoneId, PublicZoneSummary]


LORCANA_RUNTIME_ZONES: dict[ZoneId, ZoneConfig] = {
    ZoneId("deck"): ZoneConfig(ZoneId("deck"), "Deck", "secret", ordered=True, owner_scoped=True, face_down=True),
    ZoneId("hand"): ZoneConfig(ZoneId("hand"), "Hand", "private", ordered=False, owner_scoped=True),
    ZoneId("play"): ZoneConfig(ZoneId("play"), "Play", "public", ordered=False, owner_scoped=True),
    ZoneId("discard"): ZoneConfig(ZoneId("discard"), "Discard", "public", ordered=True, owner_scoped=True),
    ZoneId("inkwell"): ZoneConfig(ZoneId("inkwell"), "Inkwell", "public", ordered=False, owner_scoped=True, face_down=True),
    ZoneId("limbo"): ZoneConfig(ZoneId("limbo"), "Limbo", "public", ordered=True, owner_scoped=True),
}


def scoped_zone(base_zone: str | ZoneId, player_id: str | PlayerId) -> ZoneId:
    return ZoneId(f"{base_zone}:{player_id}")


def zone_owner_from_key(zone_key: str | ZoneId) -> PlayerId | None:
    parts = str(zone_key).split(":")
    if len(parts) <= 1:
        return None
    return PlayerId(parts[-1])


def base_zone_from_key(zone_key: str | ZoneId) -> ZoneId:
    return ZoneId(str(zone_key).split(":", 1)[0])


def build_zone_registry(
    zone_definitions: Mapping[ZoneId, ZoneConfig],
    player_ids: tuple[PlayerId, ...],
) -> dict[ZoneId, ZoneConfig]:
    registry: dict[ZoneId, ZoneConfig] = {}
    for zone_id, zone_def in zone_definitions.items():
        registry[zone_id] = zone_def
        if not zone_def.owner_scoped:
            continue
        for player_id in player_ids:
            key = scoped_zone(zone_id, player_id)
            registry[key] = replace(zone_def, id=key)
    return registry


def initialize_zone_state_from_registry(registry: Mapping[ZoneId, ZoneConfig]) -> ZoneRuntimeState:
    return ZoneRuntimeState(
        zone_cards={zone_id: () for zone_id in registry},
        card_index={},
        card_meta={},
        zone_summaries={zone_id: PublicZoneSummary() for zone_id in registry},
    )


def _zone_summary_for_cards(
    existing: PublicZoneSummary | None,
    card_ids: tuple[InstanceId, ...],
) -> PublicZoneSummary:
    revision = (existing.revision if existing else 0) + 1
    top = card_ids[-1] if card_ids else None
    return PublicZoneSummary(revision=revision, count=len(card_ids), top_public_card_id=top)


def _with_reindexed_zone(
    *,
    zone_cards: dict[ZoneId, tuple[InstanceId, ...]],
    card_index: dict[InstanceId, ZoneCardIndexEntry],
    zone_summaries: dict[ZoneId, PublicZoneSummary],
    previous_state: ZoneRuntimeState,
    zone_key: ZoneId,
    owner_id: PlayerId,
    controller_id: PlayerId,
    ordered_index: bool = True,
) -> None:
    cards = tuple(zone_cards.get(zone_key, ()))
    for index, card_id in enumerate(cards):
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=index if ordered_index else None,
            owner_id=owner_id,
            controller_id=controller_id,
        )
    zone_summaries[zone_key] = _zone_summary_for_cards(
        previous_state.zone_summaries.get(zone_key),
        cards,
    )


def remove_card_from_current_zone(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    index_entry = zone_state.card_index.get(cid)
    if index_entry is None:
        return zone_state

    zone_key = index_entry.zone_key
    current_cards = tuple(zone_state.zone_cards.get(zone_key, ()))
    remaining = tuple(item for item in current_cards if item != cid)

    zone_cards = {key: tuple(value) for key, value in zone_state.zone_cards.items()}
    card_index = dict(zone_state.card_index)
    card_meta = dict(zone_state.card_meta)
    zone_summaries = dict(zone_state.zone_summaries)

    zone_cards[zone_key] = remaining
    card_index.pop(cid, None)
    _with_reindexed_zone(
        zone_cards=zone_cards,
        card_index=card_index,
        zone_summaries=zone_summaries,
        previous_state=zone_state,
        zone_key=zone_key,
        owner_id=index_entry.owner_id,
        controller_id=index_entry.controller_id,
    )

    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
    )


def put_cards_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    zone_key: ZoneId,
    card_ids: tuple[InstanceId, ...],
    owner_id: PlayerId,
    controller_id: PlayerId | None = None,
) -> ZoneRuntimeState:
    controller = controller_id if controller_id is not None else owner_id
    zone_cards = {key: tuple(value) for key, value in zone_state.zone_cards.items()}
    card_index = dict(zone_state.card_index)
    card_meta = dict(zone_state.card_meta)
    zone_summaries = dict(zone_state.zone_summaries)

    if zone_key not in zone_cards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {zone_key}")

    current = list(zone_cards.get(zone_key, ()))
    for raw_card_id in card_ids:
        card_id = InstanceId(str(raw_card_id))
        existing = card_index.get(card_id)
        if existing is not None:
            existing_cards = list(zone_cards.get(existing.zone_key, ()))
            existing_cards = [item for item in existing_cards if item != card_id]
            zone_cards[existing.zone_key] = tuple(existing_cards)
            card_index.pop(card_id, None)
            _with_reindexed_zone(
                zone_cards=zone_cards,
                card_index=card_index,
                zone_summaries=zone_summaries,
                previous_state=zone_state,
                zone_key=existing.zone_key,
                owner_id=existing.owner_id,
                controller_id=existing.controller_id,
            )
        current.append(card_id)
        card_index[card_id] = ZoneCardIndexEntry(
            zone_key=zone_key,
            index=len(current) - 1,
            owner_id=owner_id,
            controller_id=controller,
        )
        card_meta.setdefault(card_id, CardMeta())

    zone_cards[zone_key] = tuple(current)
    zone_summaries[zone_key] = _zone_summary_for_cards(
        zone_summaries.get(zone_key),
        tuple(current),
    )
    return ZoneRuntimeState(
        zone_cards=zone_cards,
        card_index=card_index,
        card_meta=card_meta,
        zone_summaries=zone_summaries,
    )


def move_card_to_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    destination_zone_key: ZoneId,
    owner_id: PlayerId | None = None,
    controller_id: PlayerId | None = None,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    if destination_zone_key not in zone_state.zone_cards:
        raise KeyError(f"ZONE_NOT_REGISTERED: {destination_zone_key}")
    previous = zone_state.card_index.get(cid)
    resolved_owner = owner_id or (previous.owner_id if previous else zone_owner_from_key(destination_zone_key))
    if resolved_owner is None:
        raise ValueError(f"ZONE_OWNER_REQUIRED: {destination_zone_key}")
    resolved_controller = controller_id or (previous.controller_id if previous else resolved_owner)
    without = remove_card_from_current_zone(zone_state, cid)
    return put_cards_in_zone(
        without,
        zone_key=destination_zone_key,
        card_ids=(cid,),
        owner_id=resolved_owner,
        controller_id=resolved_controller,
    )


def patch_card_meta(
    zone_state: ZoneRuntimeState,
    card_id: InstanceId | str,
    meta: CardMeta,
) -> ZoneRuntimeState:
    cid = InstanceId(str(card_id))
    card_meta = dict(zone_state.card_meta)
    card_meta[cid] = meta
    return ZoneRuntimeState(
        zone_cards=zone_state.zone_cards,
        card_index=zone_state.card_index,
        card_meta=card_meta,
        zone_summaries=zone_state.zone_summaries,
    )


def card_is_in_zone(
    zone_state: ZoneRuntimeState,
    *,
    card_id: InstanceId | str,
    zone_key: ZoneId,
) -> bool:
    cid = InstanceId(str(card_id))
    return cid in zone_state.zone_cards.get(zone_key, ())
```

## Replace `lorcana_engine_v2/core/state.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .ids import InstanceId, PlayerId
from .zones import LORCANA_RUNTIME_ZONES, ZoneRuntimeState, build_zone_registry, initialize_zone_state_from_registry


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0

    def with_updates(self, **updates: Any) -> "PlayerState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class TurnMetadata:
    """Serializable Lorcana turn metadata.

    Mirrors the Lorcanito fields needed by turn-action inking now. Additional
    phase work should extend this object rather than adding ad hoc fields.
    """
    inked_this_turn: tuple[InstanceId, ...] = ()
    cards_put_into_inkwell_this_turn: tuple[InstanceId, ...] = ()
    additional_inkwell_actions: int = 0
    cards_played_this_turn: tuple[InstanceId, ...] = ()
    characters_questing: tuple[InstanceId, ...] = ()

    def with_updates(self, **updates: Any) -> "TurnMetadata":
        return replace(self, **updates)

    def turn_action_ink_limit(self, *, static_allowance: int = 0) -> int:
        temporary = max(0, int(self.additional_inkwell_actions))
        static = max(0, int(static_allowance))
        return 1 + temporary + static

    def can_record_turn_action_ink(self, *, static_allowance: int = 0) -> bool:
        return len(self.inked_this_turn) < self.turn_action_ink_limit(static_allowance=static_allowance)

    def record_turn_action_ink(self, card_id: InstanceId | str) -> "TurnMetadata":
        cid = InstanceId(str(card_id))
        inked = self.inked_this_turn if cid in self.inked_this_turn else self.inked_this_turn + (cid,)
        put_into_inkwell = (
            self.cards_put_into_inkwell_this_turn
            if cid in self.cards_put_into_inkwell_this_turn
            else self.cards_put_into_inkwell_this_turn + (cid,)
        )
        return replace(self, inked_this_turn=inked, cards_put_into_inkwell_this_turn=put_into_inkwell)

    def record_effect_inkwell_move(self, card_id: InstanceId | str) -> "TurnMetadata":
        cid = InstanceId(str(card_id))
        if cid in self.cards_put_into_inkwell_this_turn:
            return self
        return replace(self, cards_put_into_inkwell_this_turn=self.cards_put_into_inkwell_this_turn + (cid,))

    def reset_for_new_turn(self) -> "TurnMetadata":
        return TurnMetadata()


@dataclass(frozen=True, slots=True)
class PendingActionEffect:
    id: str
    kind: str
    source_id: InstanceId | None = None
    controller_id: PlayerId | None = None
    chooser_id: PlayerId | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BagEffectEntry:
    id: str
    kind: str
    source_id: InstanceId | None = None
    controller_id: PlayerId | None = None
    chooser_id: PlayerId | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BagState:
    next_seq: int = 1
    items: tuple[BagEffectEntry, ...] = ()
    last_resolved_player_id: PlayerId | None = None

    def with_updates(self, **updates: Any) -> "BagState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class TriggeredAbilitiesState:
    pending_events: tuple[object, ...] = ()
    registrations: tuple[object, ...] = ()
    bag: BagState = field(default_factory=BagState)
    usage_ledger: Mapping[str, Any] = field(default_factory=dict)

    def with_updates(self, **updates: Any) -> "TriggeredAbilitiesState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class FrameworkState:
    """Serializable framework-owned match state."""
    player_ids: tuple[PlayerId, PlayerId]
    zones: ZoneRuntimeState
    state_id: int = 0
    active_player: PlayerId = PlayerId("p0")
    turn_number: int = 1
    phase: str = "main"
    seed: str = "v2-default-seed"
    winner: PlayerId | None = None

    def with_updates(self, **updates: Any) -> "FrameworkState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class GameState:
    """Game-owned serializable state."""
    players: Mapping[PlayerId, PlayerState]
    turn_metadata: TurnMetadata = field(default_factory=TurnMetadata)
    triggered_abilities: TriggeredAbilitiesState = field(default_factory=TriggeredAbilitiesState)
    pending_effects: tuple[PendingActionEffect, ...] = ()
    event_log: tuple[Any, ...] = ()
    turn_metrics: Mapping[str, Any] = field(default_factory=dict)
    static_effects_version: int = 0

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.players[PlayerId(str(player))]

    def with_updates(self, **updates: Any) -> "GameState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class MatchState:
    """Authoritative v2 match state envelope.

    Static card identity is deliberately not stored here. Resolve instance IDs
    through MatchStaticResources.instances, then CardCatalog.
    """
    framework: FrameworkState
    game: GameState

    def opponent(self, player: PlayerId | str) -> PlayerId:
        player_id = PlayerId(str(player))
        for candidate in self.framework.player_ids:
            if candidate != player_id:
                return candidate
        raise ValueError(f"Unknown player id: {player}")

    def player(self, player: PlayerId | str) -> PlayerState:
        return self.game.player(player)

    @staticmethod
    def empty(player_ids: tuple[PlayerId, PlayerId] = (PlayerId("p0"), PlayerId("p1"))) -> "MatchState":
        registry = build_zone_registry(LORCANA_RUNTIME_ZONES, player_ids)
        zones = initialize_zone_state_from_registry(registry)
        return MatchState(
            framework=FrameworkState(player_ids=player_ids, zones=zones, active_player=player_ids[0]),
            game=GameState(players={player_id: PlayerState(player_id) for player_id in player_ids}),
        )
```

## Replace `lorcana_engine_v2/core/commands.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class Command:
    """External command submitted to MatchRuntime.

    `state_id` is optional so tests and adapters can omit it, but when present
    it must match MatchState.framework.state_id just like Lorcanito prevStateID.
    """
    kind: str
    actor: PlayerId
    card: InstanceId | None = None
    target: InstanceId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    state_id: int | None = None
```

## Replace `lorcana_engine_v2/core/results.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from .events import GameEvent
from .state import MatchState


@dataclass(frozen=True, slots=True)
class TransitionResult:
    state: MatchState
    events: tuple[GameEvent, ...] = ()
    pending: tuple[object, ...] = ()
    accepted: bool = True
    reason: str | None = None
    code: str | None = None
```

## Replace `lorcana_engine_v2/core/context.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorcana_engine_v2.core.static_resources import MatchStaticResources
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.resolution.bag import BagService
    from lorcana_engine_v2.resolution.pending import PendingService
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.derived_state import DerivedState
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver


@dataclass(frozen=True, slots=True)
class RulesContext:
    """Shared rules context, backed by Lorcanito-style static resources."""
    resources: "MatchStaticResources"
    query: "QueryService"
    targets: "TargetResolver"
    conditions: "ConditionEvaluator"
    amounts: "AmountResolver"
    static: "StaticRegistry"
    derived: "DerivedState"
    pending: "PendingService"
    bag: "BagService"

    @property
    def catalog(self):
        return self.resources.cards


def build_rules_context(resources: "MatchStaticResources") -> RulesContext:
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.resolution.bag import BagService
    from lorcana_engine_v2.resolution.pending import PendingService
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.derived_state import DerivedState
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver

    query = QueryService(resources)
    targets = TargetResolver()
    conditions = ConditionEvaluator()
    amounts = AmountResolver()
    static = StaticRegistry()
    derived = DerivedState()
    pending = PendingService()
    bag = BagService()
    return RulesContext(
        resources=resources,
        query=query,
        targets=targets,
        conditions=conditions,
        amounts=amounts,
        static=static,
        derived=derived,
        pending=pending,
        bag=bag,
    )
```

## Replace `lorcana_engine_v2/resolution/pending.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PendingBlocker:
    reason: str
    code: str


class PendingService:
    """Pending action-effect read service.

    Lorcanito blocks normal turn actions while action effects are waiting for
    choices. This service only reads state; effect creation/resolution belongs
    to a later phase.
    """

    def has_any(self, state) -> bool:
        return bool(state.game.pending_effects)

    def validate_none(self, state, *, action_label: str) -> PendingBlocker | None:
        if not self.has_any(state):
            return None
        return PendingBlocker(
            reason=f"Cannot {action_label} while an action effect is pending",
            code="EFFECT_PENDING",
        )
```

## Replace `lorcana_engine_v2/resolution/bag.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BagBlocker:
    reason: str
    code: str


class BagService:
    """Triggered bag read service.

    Lorcanito keeps triggered ability bag items under G.triggeredAbilities.bag.
    This phase only blocks normal turn actions when the bag is non-empty.
    """

    def has_any(self, state) -> bool:
        return bool(state.game.triggered_abilities.bag.items)

    def validate_empty(self, state, *, action_label: str) -> BagBlocker | None:
        if not self.has_any(state):
            return None
        return BagBlocker(
            reason=f"Cannot {action_label} while bag effects are pending",
            code="BAG_PENDING",
        )
```

## Replace `lorcana_engine_v2/registries/static_registry.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.rules.amount_resolver import AmountContext
from lorcana_engine_v2.rules.condition_evaluator import ConditionContext
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext


@dataclass(frozen=True, slots=True)
class MaterializedStaticEffect:
    source_id: InstanceId
    source_controller: PlayerId
    kind: str
    target_ids: tuple[InstanceId, ...]
    payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class StaticRegistry:
    """Materialize continuous effects from active public source cards."""

    def materialize(self, state, ctx) -> tuple[MaterializedStaticEffect, ...]:
        effects: list[MaterializedStaticEffect] = []
        for source_id in ctx.query.public_in_play_ids(state):
            source_card = ctx.query.card(state, source_id)
            source_controller = ctx.query.controller(state, source_id)
            for ability in source_card.static_abilities():
                condition = ability.raw.get("condition")
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    condition,
                    ConditionContext(actor=str(source_controller), source_id=str(source_id), target_id=str(source_id)),
                ):
                    continue
                for effect in ability.effects:
                    effects.extend(self._materialize_effect(state, ctx, source_id, effect.raw))
        return tuple(effects)

    def additional_inkwell_allowance(self, state, ctx, player: PlayerId | str) -> int:
        player_id = PlayerId(str(player))
        allowance = 0
        for source_id in ctx.query.controlled_public_in_play_ids(state, player_id):
            source_card = ctx.query.card(state, source_id)
            for ability in source_card.static_abilities():
                condition = ability.raw.get("condition")
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    condition,
                    ConditionContext(actor=player_id, source_id=source_id, target_id=source_id),
                ):
                    continue
                effect = ability.raw.get("effect")
                if not isinstance(effect, dict) or effect.get("type") != "additional-inkwell":
                    continue
                amount = ctx.amounts.resolve(
                    state,
                    ctx,
                    effect.get("amount", 1),
                    AmountContext(actor=player_id, source_id=source_id),
                )
                allowance += max(0, int(amount))
        return allowance

    def has_discard_inkability(self, state, ctx, player: PlayerId | str) -> bool:
        player_id = PlayerId(str(player))
        for source_id in ctx.query.controlled_public_in_play_ids(state, player_id):
            source_card = ctx.query.card(state, source_id)
            for ability in source_card.static_abilities():
                condition = ability.raw.get("condition")
                if not ctx.conditions.evaluate(
                    state,
                    ctx,
                    condition,
                    ConditionContext(actor=player_id, source_id=source_id, target_id=source_id),
                ):
                    continue
                effect = ability.raw.get("effect")
                if isinstance(effect, dict) and effect.get("type") == "grant-discard-inkability":
                    return True
        return False

    def _materialize_effect(self, state, ctx, source_id: InstanceId, raw: dict[str, Any]) -> tuple[MaterializedStaticEffect, ...]:
        kind = raw.get("type")
        raw_target = raw.get("target") or "SELF"
        actor = ctx.query.controller(state, source_id)

        if kind == "additional-inkwell":
            amount = ctx.amounts.resolve(
                state,
                ctx,
                raw.get("amount", 1),
                AmountContext(actor=actor, source_id=source_id),
            )
            return (MaterializedStaticEffect(
                source_id=source_id,
                source_controller=actor,
                kind="additional-inkwell",
                target_ids=(),
                payload={"player": actor, "amount": amount},
                raw=dict(raw),
            ),)

        if kind == "grant-discard-inkability":
            return (MaterializedStaticEffect(
                source_id=source_id,
                source_controller=actor,
                kind="grant-discard-inkability",
                target_ids=(),
                payload={"player": actor},
                raw=dict(raw),
            ),)

        target_ids = ctx.targets.resolve(state, ctx, raw_target, TargetQueryContext(actor=actor, source_id=source_id))
        if kind == "modify-stat":
            amount_raw = raw.get("amount") if "amount" in raw else raw.get("modifier")
            amount = ctx.amounts.resolve(state, ctx, amount_raw, AmountContext(actor=actor, source_id=source_id))
            return (MaterializedStaticEffect(
                source_id=source_id,
                source_controller=actor,
                kind="modify-stat",
                target_ids=target_ids,
                payload={"stat": str(raw.get("stat") or raw.get("attribute") or "strength"), "amount": amount},
                raw=dict(raw),
            ),)
        if kind in {"gain-keyword", "gain-keywords"}:
            keywords = raw.get("keywords") if "keywords" in raw else raw.get("keyword")
            values = keywords if isinstance(keywords, list) else [keywords]
            return tuple(
                MaterializedStaticEffect(
                    source_id=source_id,
                    source_controller=actor,
                    kind="gain-keyword",
                    target_ids=target_ids,
                    payload={"keyword": keyword},
                    raw=dict(raw),
                )
                for keyword in values if keyword
            )
        return ()
```

## Replace `lorcana_engine_v2/rules/derived_state.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.enums import Stat
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import base_zone_from_key


@dataclass(frozen=True, slots=True)
class DerivedState:
    """Read-only derived rules queries built from static materialization."""

    def effective_strength(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.strength + self._stat_delta(state, ctx, iid, Stat.STRENGTH.value))

    def effective_willpower(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.willpower + self._stat_delta(state, ctx, iid, Stat.WILLPOWER.value))

    def effective_lore(self, state, ctx, instance_id: InstanceId | str) -> int:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        return max(0, card.lore + self._stat_delta(state, ctx, iid, Stat.LORE.value))

    def keywords(self, state, ctx, instance_id: InstanceId | str) -> frozenset[str]:
        iid = InstanceId(str(instance_id))
        card = ctx.query.card(state, iid)
        base = set()
        for ability in card.abilities:
            if ability.kind == "keyword" and ability.raw.get("keyword"):
                base.add(str(ability.raw["keyword"]).upper().replace(" ", "_"))
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "gain-keyword" and iid in effect.target_ids:
                keyword = effect.payload.get("keyword")
                if keyword:
                    base.add(str(keyword).upper().replace(" ", "_"))
        return frozenset(base)

    def can_be_put_in_inkwell(self, state, ctx, instance_id: InstanceId | str, player: PlayerId | str) -> bool:
        iid = InstanceId(str(instance_id))
        player_id = PlayerId(str(player))
        runtime_card = ctx.query.runtime_card(state, iid)
        if runtime_card.owner_id != player_id:
            return False
        if not runtime_card.definition.inkable:
            return False
        if runtime_card.zone_id is None:
            return False

        base_zone = base_zone_from_key(runtime_card.zone_id)
        if base_zone == ZoneId("hand"):
            zone_allowed = True
        elif base_zone == ZoneId("discard"):
            zone_allowed = ctx.static.has_discard_inkability(state, ctx, player_id)
        else:
            zone_allowed = False

        if not zone_allowed:
            return False

        static_allowance = ctx.static.additional_inkwell_allowance(state, ctx, player_id)
        return state.game.turn_metadata.can_record_turn_action_ink(static_allowance=static_allowance)

    def _stat_delta(self, state, ctx, instance_id: InstanceId, stat: str) -> int:
        total = 0
        for effect in ctx.static.materialize(state, ctx):
            if effect.kind == "modify-stat" and effect.payload.get("stat") == stat and instance_id in effect.target_ids:
                total += int(effect.payload.get("amount", 0))
        return total
```

## Replace `lorcana_engine_v2/rules/target_resolver.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.zones import base_zone_from_key

from .target_specs import TargetSpec, normalize_target_spec


@dataclass(frozen=True, slots=True)
class TargetQueryContext:
    actor: PlayerId | str
    source_id: InstanceId | str | None = None
    event_payload: dict[str, Any] | None = None

    @property
    def actor_id(self) -> PlayerId:
        return PlayerId(str(self.actor))

    @property
    def source_instance_id(self) -> InstanceId | None:
        return InstanceId(str(self.source_id)) if self.source_id is not None else None


class TargetResolver:
    def resolve(self, state, ctx, raw_target: Any, query: TargetQueryContext) -> tuple[InstanceId, ...]:
        spec = normalize_target_spec(raw_target)
        if spec.selector == "self":
            source_id = query.source_instance_id
            return (source_id,) if source_id is not None and self._matches(state, ctx, source_id, spec, query) else ()
        candidates = []
        for instance_id in ctx.query.public_in_play_ids(state):
            if self._matches(state, ctx, instance_id, spec, query):
                candidates.append(instance_id)
        return tuple(candidates)

    def _matches(self, state, ctx, instance_id: InstanceId, spec: TargetSpec, query: TargetQueryContext) -> bool:
        runtime_card = ctx.query.runtime_card(state, instance_id)
        if runtime_card.zone_id is None:
            return False
        if spec.zones and base_zone_from_key(runtime_card.zone_id) not in {ZoneId(str(zone)) for zone in spec.zones}:
            return False
        if runtime_card.meta.stack_parent_id is not None:
            return False
        if spec.exclude_self and query.source_instance_id is not None and instance_id == query.source_instance_id:
            return False
        if spec.controller == "you" and runtime_card.controller_id != query.actor_id:
            return False
        if spec.controller == "opponent" and runtime_card.controller_id == query.actor_id:
            return False
        if spec.owner == "you" and runtime_card.owner_id != query.actor_id:
            return False
        if spec.owner == "opponent" and runtime_card.owner_id == query.actor_id:
            return False
        card = runtime_card.definition
        if spec.card_types and card.card_type not in spec.card_types and "card" not in spec.card_types:
            return False
        for filter_def in spec.filters:
            if not self._filter_matches(state, ctx, instance_id, filter_def, query):
                return False
        return True

    def _filter_matches(self, state, ctx, instance_id: InstanceId, filter_def: dict[str, Any], query: TargetQueryContext) -> bool:
        kind = filter_def.get("type")
        runtime_card = ctx.query.runtime_card(state, instance_id)
        if kind in {"has-classification", "classification"}:
            classification = filter_def.get("classification") or filter_def.get("value")
            return bool(classification and ctx.query.has_classification(state, instance_id, str(classification)))
        if kind == "has-name":
            expected = str(filter_def.get("name") or filter_def.get("value") or "")
            return runtime_card.definition.name == expected or runtime_card.definition.full_name == expected
        if kind == "damaged":
            return runtime_card.meta.damage > 0
        if kind == "ready":
            return runtime_card.meta.state != "exerted"
        if kind == "exerted":
            return runtime_card.meta.state == "exerted"
        return False
```

## Replace `lorcana_engine_v2/moves/available_moves.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.results import TransitionResult
from .ink import PUT_CARD_INTO_INKWELL, PutCardIntoInkwellMove
from .registry import MoveDefinition
from .specs import MoveSpec


def default_move_registry() -> dict[str, MoveDefinition]:
    ink = PutCardIntoInkwellMove()
    return {ink.kind: ink}


@dataclass(slots=True)
class AvailableMoveService:
    """Lorcanito-style move registry/enumeration/application service."""

    registry: dict[str, MoveDefinition] = field(default_factory=default_move_registry)

    def legal_moves(self, state, player: str | PlayerId, ctx) -> tuple[MoveSpec, ...]:
        actor = PlayerId(str(player))
        moves: list[MoveSpec] = []
        for move in self.registry.values():
            moves.extend(move.enumerate(state, actor, ctx))
        return tuple(moves)

    def apply(self, state, command: Command, ctx) -> TransitionResult:
        if command.state_id is not None and command.state_id != state.framework.state_id:
            return TransitionResult(
                state=state,
                accepted=False,
                reason="State ID mismatch - client state is stale",
                code="STALE_STATE",
            )
        if state.framework.winner is not None:
            return TransitionResult(
                state=state,
                accepted=False,
                reason="Game has already ended",
                code="GAME_ENDED",
            )

        move = self.registry.get(command.kind)
        if move is None:
            return TransitionResult(
                state=state,
                accepted=False,
                reason=f"Move '{command.kind}' not found",
                code="MOVE_NOT_FOUND",
            )
        validation = move.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason, code=validation.code)
        return move.execute(state, command, ctx)


__all__ = [
    "AvailableMoveService",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
    "default_move_registry",
]
```

## Replace `lorcana_engine_v2/moves/ink.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.results import TransitionResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import (
    CardMeta,
    base_zone_from_key,
    card_is_in_zone,
    move_card_to_zone,
    patch_card_meta,
    scoped_zone,
)
from .registry import MoveValidationResult, command_card_id
from .specs import MoveSpec


PUT_CARD_INTO_INKWELL = "putCardIntoInkwell"


@dataclass(frozen=True, slots=True)
class PutCardIntoInkwellMove:
    """Lorcanito-aligned implementation of the core inking move."""

    kind: str = PUT_CARD_INTO_INKWELL

    def enumerate(self, state: MatchState, player: PlayerId, ctx) -> tuple[MoveSpec, ...]:
        actor = PlayerId(str(player))
        if actor != state.framework.active_player:
            return ()
        if ctx.pending.has_any(state) or ctx.bag.has_any(state):
            return ()

        static_allowance = ctx.static.additional_inkwell_allowance(state, ctx, actor)
        if not state.game.turn_metadata.can_record_turn_action_ink(static_allowance=static_allowance):
            return ()

        candidate_zones = [scoped_zone("hand", actor)]
        if ctx.static.has_discard_inkability(state, ctx, actor):
            candidate_zones.append(scoped_zone("discard", actor))

        moves: list[MoveSpec] = []
        for zone_key in candidate_zones:
            for card_id in state.framework.zones.zone_cards.get(zone_key, ()):
                try:
                    if not ctx.derived.can_be_put_in_inkwell(state, ctx, card_id, actor):
                        continue
                except KeyError:
                    continue
                moves.append(MoveSpec(kind=self.kind, actor=actor, card=card_id))
        return tuple(moves)

    def validate(self, state: MatchState, command: Command, ctx) -> MoveValidationResult:
        pending_failure = ctx.pending.validate_none(state, action_label="ink cards")
        if pending_failure is not None:
            return MoveValidationResult.fail(pending_failure.reason, pending_failure.code)

        bag_failure = ctx.bag.validate_empty(state, action_label="ink cards")
        if bag_failure is not None:
            return MoveValidationResult.fail(bag_failure.reason, bag_failure.code)

        actor = PlayerId(str(command.actor))
        if actor != state.framework.active_player:
            return MoveValidationResult.fail(
                f"Player '{actor}' does not currently have priority",
                "NOT_PRIORITY_HOLDER",
            )

        static_allowance = ctx.static.additional_inkwell_allowance(state, ctx, actor)
        if not state.game.turn_metadata.can_record_turn_action_ink(static_allowance=static_allowance):
            return MoveValidationResult.fail("Already inked this turn", "ALREADY_INKED")

        raw_card_id = command_card_id(command)
        if raw_card_id is None:
            return MoveValidationResult.fail("Card input was not provided", "MISSING_CARD")
        card_id = InstanceId(raw_card_id)

        hand_zone = scoped_zone("hand", actor)
        discard_zone = scoped_zone("discard", actor)
        in_hand = card_is_in_zone(state.framework.zones, card_id=card_id, zone_key=hand_zone)
        in_discard = card_is_in_zone(state.framework.zones, card_id=card_id, zone_key=discard_zone)
        discard_allowed = ctx.static.has_discard_inkability(state, ctx, actor)
        if not in_hand and not (in_discard and discard_allowed):
            return MoveValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")

        try:
            runtime_card = ctx.query.runtime_card(state, card_id)
        except KeyError:
            return MoveValidationResult.fail("Card definition not found", "CARD_DEFINITION_NOT_FOUND")

        if not runtime_card.definition.inkable:
            return MoveValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        if not ctx.derived.can_be_put_in_inkwell(state, ctx, card_id, actor):
            return MoveValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        return MoveValidationResult.ok()

    def execute(self, state: MatchState, command: Command, ctx) -> TransitionResult:
        validation = self.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason, code=validation.code)

        actor = PlayerId(str(command.actor))
        card_id = InstanceId(command_card_id(command) or "")
        source_zone = state.framework.zones.card_index[card_id].zone_key
        destination_zone = scoped_zone("inkwell", actor)

        zones = move_card_to_zone(
            state.framework.zones,
            card_id=card_id,
            destination_zone_key=destination_zone,
            owner_id=ctx.query.owner(state, card_id),
            controller_id=actor,
        )

        current_meta = zones.card_meta.get(card_id, CardMeta())
        flags = dict(current_meta.flags)
        flags["lastMovedBy"] = self.kind
        zones = patch_card_meta(
            zones,
            card_id,
            current_meta.with_updates(
                state="ready",
                is_drying=False,
                public_face_state="faceDown",
                flags=flags,
            ),
        )

        event = GameEvent(
            kind="card.inked",
            actor=actor,
            source=card_id,
            payload={
                "cardId": str(card_id),
                "fromZone": str(source_zone),
                "fromBaseZone": str(base_zone_from_key(source_zone)),
                "toZone": str(destination_zone),
            },
        )

        next_framework = state.framework.with_updates(
            zones=zones,
            state_id=state.framework.state_id + 1,
        )
        next_game = state.game.with_updates(
            turn_metadata=state.game.turn_metadata.record_turn_action_ink(card_id),
            event_log=state.game.event_log + (event,),
        )
        next_state = MatchState(framework=next_framework, game=next_game)
        return TransitionResult(state=next_state, events=(event,), accepted=True)
```

---

# 5. Full copy-paste test code

## Replace `tests/v2/test_card_runtime_query_api_v2.py`

```python
from lorcana_engine_v2.core.zones import CardMeta, put_cards_in_zone, scoped_zone

from .helpers import context_for, resources_for
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.ids import InstanceId, PlayerId


def test_runtime_card_api_resolves_instance_to_definition_through_static_resources():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.instance_id == "c1"
    assert runtime_card.definition_id == "XGm"
    assert runtime_card.owner_id == "p0"
    assert runtime_card.controller_id == "p0"
    assert runtime_card.definition.full_name == "Chi-Fu - Imperial Advisor"
    assert runtime_card.zone_id == scoped_zone("deck", "p0")
    assert runtime_card.zone_index == 0


def test_runtime_card_api_reads_zone_and_lorcanito_meta_state_without_card_definition_in_state():
    resources = resources_for({"c1": "XGm"})
    ctx = context_for(resources)
    state = initialize_match_state_from_static_resources(resources)
    zones = put_cards_in_zone(
        state.framework.zones,
        zone_key=scoped_zone("play", "p0"),
        card_ids=(InstanceId("c1"),),
        owner_id=PlayerId("p0"),
        controller_id=PlayerId("p0"),
    )
    meta = dict(zones.card_meta)
    meta[InstanceId("c1")] = CardMeta(damage=2, state="exerted")
    zones = type(zones)(
        zone_cards=zones.zone_cards,
        card_index=zones.card_index,
        card_meta=meta,
        zone_summaries=zones.zone_summaries,
    )
    state = type(state)(framework=state.framework.with_updates(zones=zones), game=state.game)

    runtime_card = ctx.query.runtime_card(state, "c1")
    assert runtime_card.zone_id == scoped_zone("play", "p0")
    assert runtime_card.meta.damage == 2
    assert runtime_card.meta.state == "exerted"
    assert runtime_card.meta.is_exerted() is True
    assert ctx.query.public_in_play_ids(state) == ("c1",)
    assert ctx.query.characters_in_play(state, "p0") == ("c1",)
```

## Replace `tests/v2/test_put_card_into_inkwell_move_v2.py`

```python
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import (
    BagEffectEntry,
    BagState,
    MatchState,
    PendingActionEffect,
)
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves import PUT_CARD_INTO_INKWELL, MoveSpec

from .helpers import resources_for


def _state_with_zones(resources, *, p0_hand=(), p1_hand=(), p0_play=(), p0_discard=()) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = state.framework.zones
    for card_id in p0_play:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("play", "p0"),
        )
    for card_id in p0_hand:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p0"),
        )
    for card_id in p1_hand:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p1"),
        )
    for card_id in p0_discard:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("discard", "p0"),
        )
    return MatchState(framework=state.framework.with_updates(zones=zones), game=state.game)


def test_v2_enumerates_real_inkable_hand_card_as_put_card_into_inkwell_move():
    resources = resources_for({"c1": "XGm"})  # Chi-Fu - Imperial Advisor, inkable real card
    state = _state_with_zones(resources, p0_hand=("c1",))
    runtime = MatchRuntime(resources)

    moves = runtime.legal_moves(state, "p0")

    assert moves == (
        MoveSpec(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            card=InstanceId("c1"),
        ),
    )


def test_v2_put_card_into_inkwell_moves_real_card_and_records_lorcanito_turn_metadata():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_zones(resources, p0_hand=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )

    assert result.accepted is True
    assert result.reason is None
    assert result.code is None
    assert len(result.events) == 1
    assert result.events[0].kind == "card.inked"
    assert result.events[0].actor == PlayerId("p0")
    assert result.events[0].source == InstanceId("c1")

    next_state = result.state
    assert InstanceId("c1") not in next_state.framework.zones.zone_cards[scoped_zone("hand", "p0")]
    assert InstanceId("c1") in next_state.framework.zones.zone_cards[scoped_zone("inkwell", "p0")]
    assert next_state.framework.zones.card_index[InstanceId("c1")].zone_key == ZoneId("inkwell:p0")
    assert next_state.framework.state_id == state.framework.state_id + 1
    assert next_state.game.turn_metadata.inked_this_turn == (InstanceId("c1"),)
    assert next_state.game.turn_metadata.cards_put_into_inkwell_this_turn == (InstanceId("c1"),)
    assert next_state.game.event_log == result.events

    meta = next_state.framework.zones.card_meta[InstanceId("c1")]
    assert meta.state == "ready"
    assert meta.is_drying is False
    assert meta.public_face_state == "faceDown"


def test_v2_put_card_into_inkwell_rejects_second_ink_same_turn_without_allowance():
    resources = resources_for({"c1": "XGm", "c2": "Y1z"})
    state = _state_with_zones(resources, p0_hand=("c1", "c2"))
    runtime = MatchRuntime(resources)

    first = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert first.accepted is True

    assert runtime.legal_moves(first.state, "p0") == ()

    second = runtime.apply(
        first.state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c2")),
    )
    assert second.accepted is False
    assert second.reason == "Already inked this turn"
    assert second.code == "ALREADY_INKED"
    assert InstanceId("c2") in second.state.framework.zones.zone_cards[scoped_zone("hand", "p0")]


def test_v2_real_belle_static_allows_second_hand_ink_action():
    resources = resources_for(
        {"belle": "6qy", "c1": "XGm", "c2": "Y1z"},
    )
    state = _state_with_zones(resources, p0_play=("belle",), p0_hand=("c1", "c2"))
    runtime = MatchRuntime(resources)

    assert resources.cards.get("6qy").full_name == "Belle - Strange but Special"
    assert runtime.context().static.additional_inkwell_allowance(state, runtime.context(), "p0") == 1

    first = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert first.accepted is True
    assert runtime.legal_moves(first.state, "p0") == (
        MoveSpec(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c2")),
    )

    second = runtime.apply(
        first.state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c2")),
    )
    assert second.accepted is True
    assert second.state.game.turn_metadata.inked_this_turn == (InstanceId("c1"), InstanceId("c2"))
    assert runtime.legal_moves(second.state, "p0") == ()


def test_v2_real_moana_static_allows_inking_from_discard():
    resources = resources_for({"moana": "wRv", "discard_card": "XGm"})
    state = _state_with_zones(resources, p0_play=("moana",), p0_discard=("discard_card",))
    runtime = MatchRuntime(resources)

    assert resources.cards.get("wRv").full_name == "Moana - Curious Explorer"
    assert runtime.context().static.has_discard_inkability(state, runtime.context(), "p0") is True
    assert runtime.legal_moves(state, "p0") == (
        MoveSpec(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("discard_card")),
    )

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("discard_card")),
    )

    assert result.accepted is True
    assert result.events[0].payload["fromZone"] == "discard:p0"
    assert InstanceId("discard_card") in result.state.framework.zones.zone_cards[scoped_zone("inkwell", "p0")]


def test_v2_discard_card_without_discard_inkability_still_rejects_as_card_not_in_hand():
    resources = resources_for({"discard_card": "XGm"})
    state = _state_with_zones(resources, p0_discard=("discard_card",))
    runtime = MatchRuntime(resources)

    assert runtime.legal_moves(state, "p0") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("discard_card")),
    )
    assert result.accepted is False
    assert result.reason == "Card not in hand"
    assert result.code == "CARD_NOT_IN_HAND"


def test_v2_put_card_into_inkwell_rejects_real_non_inkable_card():
    resources = resources_for({"c1": "5XS"})  # Ariel - Whoseit Collector, non-inkable real card
    state = _state_with_zones(resources, p0_hand=("c1",))
    runtime = MatchRuntime(resources)

    assert resources.cards.get("5XS").inkable is False
    assert runtime.legal_moves(state, "p0") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert result.accepted is False
    assert result.reason == "Card is not inkable"
    assert result.code == "NOT_INKABLE"
    assert InstanceId("c1") in state.framework.zones.zone_cards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_card_not_in_hand():
    resources = resources_for({"c1": "XGm"})
    state = initialize_match_state_from_static_resources(resources)
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert result.accepted is False
    assert result.reason == "Card not in hand"
    assert result.code == "CARD_NOT_IN_HAND"


def test_v2_put_card_into_inkwell_rejects_non_priority_player():
    resources = resources_for(
        {"c1": "XGm", "c2": "Y1z"},
        owners={"p0": ("c1",), "p1": ("c2",)},
    )
    state = _state_with_zones(resources, p1_hand=("c2",))
    runtime = MatchRuntime(resources)

    assert state.framework.active_player == PlayerId("p0")
    assert runtime.legal_moves(state, "p1") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p1"), card=InstanceId("c2")),
    )
    assert result.accepted is False
    assert result.reason == "Player 'p1' does not currently have priority"
    assert result.code == "NOT_PRIORITY_HOLDER"


def test_v2_put_card_into_inkwell_accepts_payload_card_id_for_lorcanito_style_input():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_zones(resources, p0_hand=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            payload={"cardId": "c1"},
        ),
    )

    assert result.accepted is True
    assert InstanceId("c1") in result.state.framework.zones.zone_cards[scoped_zone("inkwell", "p0")]


def test_v2_put_card_into_inkwell_rejects_stale_command_state_id():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_zones(resources, p0_hand=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            card=InstanceId("c1"),
            state_id=state.framework.state_id - 1,
        ),
    )

    assert result.accepted is False
    assert result.reason == "State ID mismatch - client state is stale"
    assert result.code == "STALE_STATE"


def test_v2_put_card_into_inkwell_rejects_pending_action_effect():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_zones(resources, p0_hand=("c1",))
    state = MatchState(
        framework=state.framework,
        game=state.game.with_updates(
            pending_effects=(
                PendingActionEffect(id="pending-1", kind="target-selection", controller_id=PlayerId("p0")),
            ),
        ),
    )
    runtime = MatchRuntime(resources)

    assert runtime.legal_moves(state, "p0") == ()
    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )

    assert result.accepted is False
    assert result.reason == "Cannot ink cards while an action effect is pending"
    assert result.code == "EFFECT_PENDING"


def test_v2_put_card_into_inkwell_rejects_pending_bag_item():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_zones(resources, p0_hand=("c1",))
    triggered = state.game.triggered_abilities.with_updates(
        bag=BagState(
            items=(
                BagEffectEntry(id="bag-1", kind="triggered-ability", controller_id=PlayerId("p0")),
            ),
        )
    )
    state = MatchState(framework=state.framework, game=state.game.with_updates(triggered_abilities=triggered))
    runtime = MatchRuntime(resources)

    assert runtime.legal_moves(state, "p0") == ()
    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )

    assert result.accepted is False
    assert result.reason == "Cannot ink cards while bag effects are pending"
    assert result.code == "BAG_PENDING"
```

---

# 6. Why each fix is required

```text
CardMeta migration:
Required because future cost payment, drying, shift stacks, locations, and action-card limbo all read Lorcanito meta names. Keeping `exerted` and `drying` would force every later port to translate wrong local fields.

TurnMetadata expansion:
Required because Lorcanito's canInkThisTurn depends on inkedThisTurn plus additionalInkwellActions/static allowance, and turn metrics separately track cards put into inkwell by any source.

PendingService and BagService:
Required because Lorcanito blocks normal turn actions while choices/effects are pending. Inking while a pending action effect or bag item exists creates illegal state ordering.

StaticRegistry helper methods:
Required because Belle's additional inkwell action and Moana's discard inkability are static effects that change turn-action legality before play-card exists.

DerivedState.can_be_put_in_inkwell:
Required because Lorcanito's runtime card projection exposes canBePutInInkwell and move enumeration uses that derived legality rather than reimplementing card filters in UI code.

Command.state_id and TransitionResult.code:
Required because Lorcanito validation returns stable error codes and rejects stale state before move execution.
```

---

# 7. How the fix matches Lorcanito

```text
Lorcanito CardMeta.state                       -> Python CardMeta.state
Lorcanito CardMeta.isDrying                    -> Python CardMeta.is_drying
Lorcanito CardMeta.publicFaceState             -> Python CardMeta.public_face_state
Lorcanito G.turnMetadata.inkedThisTurn         -> Python TurnMetadata.inked_this_turn
Lorcanito G.turnMetadata.additionalInkwellActions -> Python TurnMetadata.additional_inkwell_actions
Lorcanito cardsPutIntoInkwellThisTurn metric   -> Python TurnMetadata.cards_put_into_inkwell_this_turn
Lorcanito G.pendingEffects                     -> Python GameState.pending_effects
Lorcanito G.triggeredAbilities.bag.items       -> Python GameState.triggered_abilities.bag.items
Lorcanito canInkThisTurn                       -> Python TurnMetadata.can_record_turn_action_ink
Lorcanito INKWELL_CANDIDATE_QUERY_DSL hand/discard -> Python derived can_be_put_in_inkwell hand/discard path
Lorcanito validateNoPendingEffects             -> Python PendingService.validate_none
Lorcanito STALE_STATE validation               -> Python Command.state_id check
```

---

# 8. Exact test commands and expected results

Run the v2 suite:

```bash
pytest -q tests/v2
```

Expected result after applying this phase:

```text
36 passed
```

Run the focused inkwell parity tests:

```bash
pytest -q tests/v2/test_put_card_into_inkwell_move_v2.py
```

Expected result:

```text
13 passed
```

Run the dependency guard:

```bash
pytest -q tests/v2/test_dependency_rules.py
```

Expected result:

```text
1 passed
```

---

# 9. Parity proof

This phase proves the following with actual Lorcanito-derived cards:

```text
Chi-Fu - Imperial Advisor (XGm):
  real inkable hand card can be put into inkwell.

Ariel - Whoseit Collector (5XS):
  real non-inkable hand card is rejected with NOT_INKABLE.

Belle - Strange but Special (6qy):
  real additional-inkwell static ability increases the turn-action ink limit from 1 to 2.

Moana - Curious Explorer (wRv):
  real grant-discard-inkability static ability allows a real discard card to be inked.
```

This phase also proves the following engine flow:

```text
legal move enumeration reads runtime card state and static effects.
validation rejects pending action effects.
validation rejects pending bag effects.
validation rejects stale state IDs.
execution moves exactly one card from hand/discard to inkwell.
execution writes Lorcanito-aligned meta state ready/faceDown.
execution records inkedThisTurn and cardsPutIntoInkwellThisTurn.
```

---

# 10. Relevant edge cases and risks

```text
1. No reveal window yet.
   Lorcanito briefly reveals inked cards. v2 still records public_face_state but does not implement zone reveal windows. Do not claim full reveal parity.

2. No trigger flush yet.
   Lorcanito emits cardInked and flushes triggered events to bag. This phase only blocks existing bag items; it does not create new bag items.

3. No action/effect put-into-inkwell yet.
   Effect-based inkwell moves should call TurnMetadata.record_effect_inkwell_move, not record_turn_action_ink. That belongs to action-effect resolution.

4. Static conditions are still narrow.
   Belle and Moana work because their inking statics have no complex condition. More static variants need the later static-registry phase.

5. Flow validation is still partial.
   The move service now rejects stale state and game-ended state. It does not yet enforce Lorcanito's full runtime flow validMoves list.

6. CardMeta migration will break any unlisted local tests that still instantiate CardMeta(exerted=...) or read meta.exerted.
   Rewrite those tests. Do not add compatibility fields.
```

---

# 11. Next phases after this one

## Phase 4 - Costs and standard play-card for non-action permanents

Implement:

```text
available ink = ready cards in inkwell
spendInk = exert ready inkwell cards in zone order
validateBasicCost / payBasicCost
playCard standard cost only
character enters play ready + is_drying true
item/location enter play with Lorcanito meta
cardsPlayedThisTurn metric
```

Do not implement action effects, shift, sing, triggers, or unsupported report movement in Phase 4.

## Phase 5 - Action cards, pending effects, and resolveEffect

Implement:

```text
action card enters play first
target analysis
immediate effect execution for supported effect variants
pendingEffects suspension
resolveEffect continuation
action card finalization to discard or limbo
```

## Phase 6 - Triggered abilities and resolveBag

Implement:

```text
trigger registration scan
event buffering
bag item creation
active resolver selection
resolveBag
optional trigger choices
trigger usage ledger
```

## Phase 7 - Turn flow, passTurn, quest, challenge

Implement:

```text
beginning phase ready/set/draw
drying cleanup
passTurn blockers
quest legality and lore gain
challenge declaration, damage, lethal sweep
reckless/bodyguard/evasive/resist rules
```

## Phase 8 - Unsupported report movement

Only after phases 4-7 have real-card parity tests, update unsupported reports. Movement must cite integration tests using actual normalized/Lorcanito-derived card data. Synthetic unit tests can support helpers but cannot justify support status changes.


# LorcanaChamp v2 Kernel Implementation 2 — Move Pipeline + Put Card Into Inkwell

## Phase name

`V2 Kernel Implementation 2: Move Definition Pipeline and Put Card Into Inkwell`

## Scope decision

This phase implements the first real v2 command/move pipeline and the first real Lorcanito-aligned core move:

- `putCardIntoInkwell`

This phase intentionally does **not** implement play-card, quest, challenge, triggers, pending effects, or ability resolution yet.

The goal is to establish the Lorcanito-style move contract before adding complex gameplay:

```text
MatchRuntime.apply(command)
  -> move registry lookup
  -> validation
  -> execution through shared RulesContext
  -> zone mutation
  -> event output
  -> turn metadata mutation
  -> TransitionResult
```

## Development standard applied

This guide prioritizes:

1. Match Lorcanito's game model first.
2. Match Lorcanito's resolution flow second.
3. Preserve LorcanaChamp APIs only when they do not fight parity.
4. Tests prove behavior, not old structure.
5. Unsupported report movement must reflect real engine support.

This phase does **not** claim unsupported report movement. It introduces the v2 move substrate and one core rules move. It does not classify Lorcanito card abilities/effects as newly executable.

---

# 1. Lorcanito source findings

## Files inspected

Lorcanito source path used:

```text
~/LorcanaChamp/references/lorcana-simulator/packages/lorcana
```

Local extracted source inspected from the uploaded Lorcanito package:

```text
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.ts
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.commands.ts
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.validation.ts
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.types.ts
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.utils.ts
packages/lorcana/lorcana-engine/src/core/runtime/match-runtime.apis.ts
packages/lorcana/lorcana-engine/src/core/runtime/zone-operations.ts
packages/lorcana/lorcana-engine/src/core/runtime/zone-registry.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/resources.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/index.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/play-card.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/quest.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/core/challenge.ts
packages/lorcana/lorcana-engine/src/runtime-moves/moves/turn/pass-turn.ts
packages/lorcana/lorcana-engine/src/operations/zones.ts
packages/lorcana/lorcana-engine/src/operations/cards.ts
packages/lorcana/lorcana-engine/src/types/runtime-state.ts
```

## Confirmed Lorcanito behavior

### A. Move definitions are first-class runtime objects

Lorcanito defines moves as `MoveDefinition` records with separate phases:

```ts
export interface MoveDefinition<TInput extends MoveInput = MoveInput, TTargetDSL = unknown> {
  available?: (context: MoveEnumerationContext) => boolean;
  validate?: (context: MoveValidationContext<TInput>) => RuntimeValidationResult;
  execute: (context: MoveExecutionContext<TInput>) => void;
  undoable?: boolean;
  redactInput?: boolean;
  optimistic?: boolean | "auto";
  ignoreStaleStateID?: boolean;
  serverOnly?: boolean;
  ignorePriority?: boolean;
}
```

The important model is:

```text
enumerate/available
validate
execute
```

Move handlers do not directly own global engine state. They receive context APIs:

```text
G
playerId
query
cards
framework
```

### B. Runtime command processing validates before execution

`match-runtime.commands.ts` performs this flow:

```text
executeCommand(command)
  -> validateCommand(...)
  -> get moveDef
  -> build execution context
  -> execute moveDef
  -> update stateID
  -> resolve flow transitions
  -> check game end
  -> return command result + events/logs
```

Validation checks:

```text
missing input
stale state ID
game already ended
move exists
server-only restrictions
flow restrictions
priority holder
move-specific validate()
```

V2 does not need all of these in this phase, but the move pipeline must be shaped so these concepts can be added without rewriting every move.

### C. `putCardIntoInkwell` is the clean first move

Lorcanito implements `putCardIntoInkwell` in:

```text
runtime-moves/moves/core/resources.ts
```

Confirmed validation behavior:

```text
1. Validate no pending effects before inking.
2. Enforce once-per-turn inkwell rule.
3. Card must be in the player's hand, except discard is allowed when a static grants discard inkability.
4. Card definition/runtime card must exist.
5. Runtime card must be inkable/canBePutInInkwell.
```

Confirmed execution behavior:

```text
1. Determine source zone before moving.
2. Move the card to the player's inkwell zone.
3. Patch card meta to ready and face down.
4. Briefly reveal it to all players.
5. Log card inked.
6. Append card ID to turnMetadata.inkedThisTurn.
7. Record put-into-inkwell turn metric.
```

### D. Core moves are exported together

Lorcanito exports core moves from:

```text
runtime-moves/moves/core/index.ts
```

including:

```ts
export { challenge } from "./challenge";
export { playCard } from "./play-card";
export { quest, questWithAll } from "./quest";
export { putCardIntoInkwell } from "./resources";
export { moveCharacterToLocation } from "./move-character-to-location";
```

The v2 move package should mirror that direction: move handlers live as independent modules and are gathered by a registry/service, not hard-coded into `MatchRuntime`.

---

# 2. Current LorcanaChamp v2 findings

## Files inspected

Current v2 scaffold files inspected on `main`:

```text
lorcana_engine_v2/core/runtime.py
lorcana_engine_v2/core/commands.py
lorcana_engine_v2/core/results.py
lorcana_engine_v2/core/events.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/core/zones.py
lorcana_engine_v2/core/static_resources.py
lorcana_engine_v2/core/bootstrap.py
lorcana_engine_v2/core/context.py
lorcana_engine_v2/rules/queries.py
lorcana_engine_v2/moves/available_moves.py
lorcana_engine_v2/moves/specs.py
lorcana_engine_v2/moves/__init__.py
tests/v2/helpers.py
tests/v2/test_kernel_imports.py
tests/v2/test_first_real_card_parity_v2.py
tests/v2/test_static_resources_v2.py
tests/v2/test_zone_bootstrap_v2.py
tests/v2/test_card_runtime_query_api_v2.py
```

## Current behavior

The v2 kernel now correctly has:

```text
MatchStaticResources
CardInstanceRegistry
CardQueryAPI-like QueryService
owner-scoped zones
static/derived-state reads
RulesContext
MatchRuntime shell
```

But `AvailableMoveService` is still only a scaffold:

```python
@dataclass(slots=True)
class AvailableMoveService:
    """Move enumeration/application scaffold."""

    def legal_moves(self, state, player: int, ctx) -> tuple[object, ...]:
        return ()

    def apply(self, state, command, ctx) -> TransitionResult:
        return TransitionResult(state=state, accepted=False, reason="v2_move_application_not_implemented")
```

Current `MoveSpec` still uses integer actor/card fields from the earliest scaffold:

```python
@dataclass(frozen=True, slots=True)
class MoveSpec:
    kind: str
    actor: int
    card: int | None = None
    target: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
```

This conflicts with the v2 phase 1 model where IDs are `PlayerId`/`InstanceId` string NewTypes.

Current zone operations can append cards to a zone, but they do not yet provide Lorcanito-style move/remove/patch operations needed by commands:

```text
put_cards_in_zone exists
move_card_to_zone does not exist
remove_card_from_current_zone does not exist
patch_card_meta does not exist
```

## Exact mismatch

Lorcanito has:

```text
move registry / move definitions
validation context
execution context
zone mutation API
core move handlers
turn metadata for once-per-turn inking
```

Current v2 has:

```text
runtime shell
empty AvailableMoveService
no move definitions
no move registry
no executable move handler
no zone move operation
no turn metadata object
```

The next phase must introduce a real move pipeline. This is a structural refactor, not a small patch.

---

# 3. Required implementation actions

## Files to replace

```text
lorcana_engine_v2/core/zones.py
lorcana_engine_v2/core/state.py
lorcana_engine_v2/moves/specs.py
lorcana_engine_v2/moves/available_moves.py
lorcana_engine_v2/moves/__init__.py
```

## Files to add

```text
lorcana_engine_v2/moves/registry.py
lorcana_engine_v2/moves/ink.py
tests/v2/test_put_card_into_inkwell_move_v2.py
```

No existing v1 `lorcana_bot` runtime code should be imported.

---

# 4. Full replacement code

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
    damage: int = 0
    exerted: bool = False
    drying: bool = False
    location_instance_id: InstanceId | None = None
    stack_parent_id: InstanceId | None = None
    cards_under: tuple[InstanceId, ...] = ()
    flags: Mapping[str, object] = field(default_factory=dict)

    def with_updates(self, **updates: object) -> "CardMeta":
        return replace(self, **updates)


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
        # Ensure a card cannot exist in two zones.  This mirrors Lorcanito's
        # zone operation invariant where a card has one current zone index.
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
from .zones import ZoneRuntimeState, build_zone_registry, initialize_zone_state_from_registry, LORCANA_RUNTIME_ZONES


@dataclass(frozen=True, slots=True)
class PlayerState:
    player_id: PlayerId
    lore: int = 0

    def with_updates(self, **updates: Any) -> "PlayerState":
        return replace(self, **updates)


@dataclass(frozen=True, slots=True)
class TurnMetadata:
    """Serializable turn metadata owned by the Lorcana game layer.

    Lorcanito records cards inked this turn in `G.turnMetadata.inkedThisTurn`.
    v2 keeps the same concept explicit so moves can enforce once-per-turn rules
    without storing transient rule state in card definitions or zone records.
    """
    inked_this_turn: tuple[InstanceId, ...] = ()

    def record_ink(self, card_id: InstanceId | str) -> "TurnMetadata":
        cid = InstanceId(str(card_id))
        if cid in self.inked_this_turn:
            return self
        return replace(self, inked_this_turn=self.inked_this_turn + (cid,))

    def reset_for_new_turn(self) -> "TurnMetadata":
        return TurnMetadata()


@dataclass(frozen=True, slots=True)
class FrameworkState:
    """Serializable framework-owned match state.

    Mirrors Lorcanito's framework/game split at v2 scale: zones, priority-like
    active player, state ID, and phase live here, not in static card definitions.
    """
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
    """Game-owned serializable state.

    Phase 2 adds explicit turn metadata for the first real move. Future phases
    will add bag, pending effects, replacement effects, and floating triggers.
    """
    players: Mapping[PlayerId, PlayerState]
    turn_metadata: TurnMetadata = field(default_factory=TurnMetadata)
    event_log: tuple[Any, ...] = ()
    turn_metrics: Mapping[str, Any] = field(default_factory=dict)

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

## Replace `lorcana_engine_v2/moves/specs.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lorcana_engine_v2.core.ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class MoveSpec:
    """A legal move candidate exposed by v2.

    This is v2's Python analogue to Lorcanito RuntimeLegalMove entries. It uses
    v2 string-branded IDs instead of the scaffold-era integer fields.
    """
    kind: str
    actor: PlayerId
    card: InstanceId | None = None
    target: InstanceId | None = None
    payload: dict[str, Any] = field(default_factory=dict)
```

## Add `lorcana_engine_v2/moves/registry.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.results import TransitionResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.context import RulesContext
from lorcana_engine_v2.core.ids import PlayerId
from .specs import MoveSpec


@dataclass(frozen=True, slots=True)
class MoveValidationResult:
    valid: bool
    reason: str | None = None
    code: str | None = None

    @staticmethod
    def ok() -> "MoveValidationResult":
        return MoveValidationResult(valid=True)

    @staticmethod
    def fail(reason: str, code: str) -> "MoveValidationResult":
        return MoveValidationResult(valid=False, reason=reason, code=code)


class MoveDefinition(Protocol):
    """Protocol for Lorcanito-style v2 move handlers."""

    kind: str

    def enumerate(self, state: MatchState, player: PlayerId, ctx: RulesContext) -> tuple[MoveSpec, ...]:
        ...

    def validate(self, state: MatchState, command: Command, ctx: RulesContext) -> MoveValidationResult:
        ...

    def execute(self, state: MatchState, command: Command, ctx: RulesContext) -> TransitionResult:
        ...


def command_card_id(command: Command) -> str | None:
    if command.card is not None:
        return str(command.card)
    raw = command.payload.get("cardId") or command.payload.get("card_id")
    if raw is None:
        return None
    return str(raw)
```

## Add `lorcana_engine_v2/moves/ink.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.events import GameEvent
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.results import TransitionResult
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import (
    CardMeta,
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
    """Lorcanito-aligned implementation of the core inking move.

    This mirrors the early behavior of Lorcanito's `putCardIntoInkwell` move:
    validate priority/turn/card-zone/inkability, then move the selected card to
    the player's inkwell and record that the player inked this turn.
    """

    kind: str = PUT_CARD_INTO_INKWELL

    def enumerate(self, state: MatchState, player: PlayerId, ctx) -> tuple[MoveSpec, ...]:
        actor = PlayerId(str(player))
        if actor != state.framework.active_player:
            return ()
        if state.game.turn_metadata.inked_this_turn:
            return ()

        hand_zone = scoped_zone("hand", actor)
        moves: list[MoveSpec] = []
        for card_id in state.framework.zones.zone_cards.get(hand_zone, ()):
            try:
                runtime_card = ctx.query.runtime_card(state, card_id)
            except KeyError:
                continue
            if not runtime_card.definition.inkable:
                continue
            moves.append(MoveSpec(kind=self.kind, actor=actor, card=card_id))
        return tuple(moves)

    def validate(self, state: MatchState, command: Command, ctx) -> MoveValidationResult:
        actor = PlayerId(str(command.actor))
        if actor != state.framework.active_player:
            return MoveValidationResult.fail(
                f"Player '{actor}' does not currently have priority",
                "NOT_PRIORITY_HOLDER",
            )

        if state.game.turn_metadata.inked_this_turn:
            return MoveValidationResult.fail("Already inked this turn", "ALREADY_INKED")

        raw_card_id = command_card_id(command)
        if raw_card_id is None:
            return MoveValidationResult.fail("Card input was not provided", "MISSING_CARD")
        card_id = InstanceId(raw_card_id)

        hand_zone = scoped_zone("hand", actor)
        if not card_is_in_zone(state.framework.zones, card_id=card_id, zone_key=hand_zone):
            return MoveValidationResult.fail("Card not in hand", "CARD_NOT_IN_HAND")

        try:
            runtime_card = ctx.query.runtime_card(state, card_id)
        except KeyError:
            return MoveValidationResult.fail("Card definition not found", "CARD_DEFINITION_NOT_FOUND")

        if not runtime_card.definition.inkable:
            return MoveValidationResult.fail("Card is not inkable", "NOT_INKABLE")

        return MoveValidationResult.ok()

    def execute(self, state: MatchState, command: Command, ctx) -> TransitionResult:
        validation = self.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason)

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
        flags["state"] = "ready"
        flags["publicFaceState"] = "faceDown"
        flags["lastMovedBy"] = self.kind
        zones = patch_card_meta(
            zones,
            card_id,
            current_meta.with_updates(exerted=False, drying=False, flags=flags),
        )

        event = GameEvent(
            kind="card.inked",
            actor=actor,
            source=card_id,
            payload={
                "cardId": str(card_id),
                "fromZone": str(source_zone),
                "toZone": str(destination_zone),
            },
        )

        next_framework = state.framework.with_updates(
            zones=zones,
            state_id=state.framework.state_id + 1,
        )
        next_game = state.game.with_updates(
            turn_metadata=state.game.turn_metadata.record_ink(card_id),
            event_log=state.game.event_log + (event,),
        )
        next_state = MatchState(framework=next_framework, game=next_game)
        return TransitionResult(state=next_state, events=(event,), accepted=True)
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
        move = self.registry.get(command.kind)
        if move is None:
            return TransitionResult(
                state=state,
                accepted=False,
                reason=f"Move '{command.kind}' not found",
            )
        validation = move.validate(state, command, ctx)
        if not validation.valid:
            return TransitionResult(state=state, accepted=False, reason=validation.reason)
        return move.execute(state, command, ctx)


__all__ = [
    "AvailableMoveService",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
    "default_move_registry",
]
```

## Replace `lorcana_engine_v2/moves/__init__.py`

```python
from .specs import MoveSpec
from .available_moves import AvailableMoveService
from .ink import PUT_CARD_INTO_INKWELL, PutCardIntoInkwellMove
from .registry import MoveDefinition, MoveValidationResult

__all__ = [
    "AvailableMoveService",
    "MoveDefinition",
    "MoveSpec",
    "MoveValidationResult",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
]
```

---

# 5. New tests

## Add `tests/v2/test_put_card_into_inkwell_move_v2.py`

```python
from lorcana_engine_v2.core.bootstrap import initialize_match_state_from_static_resources
from lorcana_engine_v2.core.commands import Command
from lorcana_engine_v2.core.ids import InstanceId, PlayerId, ZoneId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import move_card_to_zone, scoped_zone
from lorcana_engine_v2.moves import PUT_CARD_INTO_INKWELL, MoveSpec

from .helpers import context_for, resources_for


def _state_with_hand(resources, *, p0=(), p1=()) -> MatchState:
    state = initialize_match_state_from_static_resources(resources)
    zones = state.framework.zones
    for card_id in p0:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p0"),
        )
    for card_id in p1:
        zones = move_card_to_zone(
            zones,
            card_id=InstanceId(str(card_id)),
            destination_zone_key=scoped_zone("hand", "p1"),
        )
    return MatchState(framework=state.framework.with_updates(zones=zones), game=state.game)


def test_v2_enumerates_real_inkable_hand_card_as_put_card_into_inkwell_move():
    resources = resources_for({"c1": "XGm"})  # Chi-Fu - Imperial Advisor, inkable real card
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    moves = runtime.legal_moves(state, "p0")

    assert moves == (
        MoveSpec(
            kind=PUT_CARD_INTO_INKWELL,
            actor=PlayerId("p0"),
            card=InstanceId("c1"),
        ),
    )


def test_v2_put_card_into_inkwell_moves_real_card_and_records_turn_metadata():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )

    assert result.accepted is True
    assert result.reason is None
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
    assert next_state.game.event_log == result.events

    meta = next_state.framework.zones.card_meta[InstanceId("c1")]
    assert meta.exerted is False
    assert meta.drying is False
    assert meta.flags["state"] == "ready"
    assert meta.flags["publicFaceState"] == "faceDown"


def test_v2_put_card_into_inkwell_rejects_second_ink_same_turn():
    resources = resources_for({"c1": "XGm", "c2": "Y1z"})
    state = _state_with_hand(resources, p0=("c1", "c2"))
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
    assert InstanceId("c2") in second.state.framework.zones.zone_cards[scoped_zone("hand", "p0")]


def test_v2_put_card_into_inkwell_rejects_real_non_inkable_card():
    resources = resources_for({"c1": "5XS"})  # Ariel - Whoseit Collector, non-inkable real card
    state = _state_with_hand(resources, p0=("c1",))
    runtime = MatchRuntime(resources)

    assert resources.cards.get("5XS").inkable is False
    assert runtime.legal_moves(state, "p0") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p0"), card=InstanceId("c1")),
    )
    assert result.accepted is False
    assert result.reason == "Card is not inkable"
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


def test_v2_put_card_into_inkwell_rejects_non_priority_player():
    resources = resources_for(
        {"c1": "XGm", "c2": "Y1z"},
        owners={"p0": ("c1",), "p1": ("c2",)},
    )
    state = _state_with_hand(resources, p1=("c2",))
    runtime = MatchRuntime(resources)

    assert state.framework.active_player == PlayerId("p0")
    assert runtime.legal_moves(state, "p1") == ()

    result = runtime.apply(
        state,
        Command(kind=PUT_CARD_INTO_INKWELL, actor=PlayerId("p1"), card=InstanceId("c2")),
    )
    assert result.accepted is False
    assert result.reason == "Player 'p1' does not currently have priority"


def test_v2_put_card_into_inkwell_accepts_payload_card_id_for_lorcanito_style_input():
    resources = resources_for({"c1": "XGm"})
    state = _state_with_hand(resources, p0=("c1",))
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
```

---

# 6. Why each fix is required

## `zones.py`

Required because Lorcanito moves do not mutate arbitrary card objects. They use framework zone operations to move cards between zones and patch card metadata. v2 currently only has `put_cards_in_zone`, which is insufficient for command execution because it cannot safely remove a card from its previous zone, reindex the source zone, patch metadata, or maintain the one-zone-per-card invariant.

## `state.py`

Required because Lorcanito's `putCardIntoInkwell` records `G.turnMetadata.inkedThisTurn`. The once-per-turn rule must live in game-owned turn metadata, not in card definitions or zone state. This guide adds `TurnMetadata` while preserving the existing `turn_metrics` placeholder for later condition/amount work.

## `moves/specs.py`

Required because v2 no longer uses integer instance/player IDs. Keeping integer move specs would be wrong old language. The move API must use the same `PlayerId` and `InstanceId` values used by static resources and zones.

## `moves/registry.py`

Required because Lorcanito treats moves as first-class records with validation and execution. This creates the v2 protocol without forcing all move logic into `MatchRuntime`.

## `moves/ink.py`

Required because `putCardIntoInkwell` is Lorcanito's cleanest first core move. It tests card runtime lookup, zone movement, turn metadata, command validation, and transition output without requiring ability resolution.

## `moves/available_moves.py`

Required because the current service always returns no moves and rejects all commands. This replacement introduces a real registry-backed move service.

---

# 7. How this matches Lorcanito

| Lorcanito | LorcanaChamp v2 after this phase |
|---|---|
| `MoveDefinition.available/validate/execute` | `MoveDefinition.enumerate/validate/execute` protocol |
| `putCardIntoInkwell` move ID | exact v2 constant `putCardIntoInkwell` |
| priority holder validation | active-player validation as the phase-2 priority substitute |
| hand-zone validation | `card_is_in_zone(hand:pX)` |
| runtime card lookup | `ctx.query.runtime_card(state, card_id)` |
| `canBePutInInkwell` | `CardDefinition.inkable` until derived inkability exists |
| `ctx.framework.zones.moveCard` | `move_card_to_zone` |
| `ctx.cards.patchMeta` | `patch_card_meta` |
| `G.turnMetadata.inkedThisTurn` | `GameState.turn_metadata.inked_this_turn` |
| card inked log/event | `GameEvent(kind="card.inked")` |

## Known intentional simplifications

These are intentionally **not** implemented yet:

```text
pending-effect blocking
static discard inkability
derived canBePutInInkwell from static grants
brief reveal window / visibility expiry
full priority window object
flow phase definitions
undo barriers
move logs/projection logs
turn metric condition integration
```

They are not needed to prove the first move pipeline. They must be implemented before claiming full Lorcanito inking parity.

---

# 8. Tests to run

Run focused compile checks:

```bash
python3 -m py_compile \
  lorcana_engine_v2/core/zones.py \
  lorcana_engine_v2/core/state.py \
  lorcana_engine_v2/moves/specs.py \
  lorcana_engine_v2/moves/registry.py \
  lorcana_engine_v2/moves/ink.py \
  lorcana_engine_v2/moves/available_moves.py \
  lorcana_engine_v2/moves/__init__.py \
  tests/v2/test_put_card_into_inkwell_move_v2.py
```

Run the new focused tests:

```bash
python3 -m pytest tests/v2/test_put_card_into_inkwell_move_v2.py -q
```

Expected:

```text
7 passed
```

Run all v2 tests:

```bash
python3 -m pytest tests/v2 -q
```

Expected if Phase 1 currently has 23 tests:

```text
30 passed
```

Run full suite:

```bash
python3 -m pytest -q
```

Expected:

```text
all tests pass
```

---

# 9. Existing tests affected

Existing v2 tests should continue to pass because:

```text
MatchStaticResources stays unchanged.
QueryService still resolves instance -> definition through resources.
StaticRegistry still uses public play zone queries.
Existing helper functions still use put_cards_in_zone, now safer because it removes duplicate zone entries.
```

Possible expected adjustment:

If any existing test asserts a zone summary revision equals `1`, it may need to assert only `count` and card membership. Revision is an internal mutation counter and should not be treated as a Lorcana rules fact.

---

# 10. Unsupported report integration rules

This phase should not move unsupported report counts.

Reason:

```text
The unsupported report is about real Lorcanito card ability/effect runtime support.
This phase implements a core manual game move, not card ability/effect execution.
```

Do **not** mark any new Lorcanito card source effect/ability as executable because of this phase.

Future report movement can happen when:

```text
source abilities/effects map to typed v2 effect specs
runtime handlers execute them
real-card parity tests prove card behavior
```

---

# 11. Parity proof

## Lorcanito does X

In `runtime-moves/moves/core/resources.ts`, Lorcanito implements `putCardIntoInkwell` with:

```text
validate:
  no pending effects
  once per turn
  card in hand/discard with special permission
  runtime card exists
  card can be put in inkwell

execute:
  move card to inkwell
  patch card meta ready/faceDown
  log card inked
  record turnMetadata.inkedThisTurn
```

## LorcanaChamp v2 now does X

In `lorcana_engine_v2/moves/ink.py`, v2 implements:

```text
validate:
  active player check
  once per turn
  card in hand
  runtime card exists
  card definition is inkable

execute:
  move card to inkwell
  patch card meta ready/faceDown
  emit card.inked event
  record GameState.turn_metadata.inked_this_turn
```

## Tests prove it

```text
test_v2_enumerates_real_inkable_hand_card_as_put_card_into_inkwell_move
  proves legal move enumeration from real card data.

test_v2_put_card_into_inkwell_moves_real_card_and_records_turn_metadata
  proves zone movement, meta patch, event output, and turn metadata.

test_v2_put_card_into_inkwell_rejects_second_ink_same_turn
  proves once-per-turn inking.

test_v2_put_card_into_inkwell_rejects_real_non_inkable_card
  proves real-card inkability enforcement.

test_v2_put_card_into_inkwell_rejects_card_not_in_hand
  proves hand-zone validation.

test_v2_put_card_into_inkwell_rejects_non_priority_player
  proves active-player/priority substitute.

test_v2_put_card_into_inkwell_accepts_payload_card_id_for_lorcanito_style_input
  proves command payload compatibility for Lorcanito-style input shapes.
```

---

# 12. Edge cases and risks

## Edge case: static discard inkability

Lorcanito allows discard-zone inking when a static grants discard inkability. v2 does not support that yet. This is intentionally excluded because it requires static property modification/permission support.

Risk: some real cards will eventually need this. Do not mark those cards executable yet.

## Edge case: derived inkability

Lorcanito checks runtime `canBePutInInkwell`, not only printed `inkable`. v2 currently checks `CardDefinition.inkable`. This is acceptable for Phase 2 because no static inkability override is implemented yet.

Risk: when static inkability is added, this move must call `ctx.derived.can_put_in_inkwell(...)` instead of direct `definition.inkable`.

## Edge case: reveal window

Lorcanito briefly reveals inked cards to all players and later expires reveal visibility. v2 records face-down meta but does not implement reveal visibility expiry yet.

Risk: projection/visibility tests should not yet claim reveal parity.

## Edge case: priority model

Lorcanito has a true priority holder and priority window. v2 uses `state.framework.active_player` as the phase-2 priority substitute.

Risk: once pass-turn and bag/pending effects exist, this must become a real `PriorityState` rather than active-player-only validation.

## Edge case: zone summary revision

This phase introduces stronger zone mutation helpers. Zone summary revision counts may change compared with earlier helper-only tests.

Risk: tests should assert rules facts like membership and count, not internal revision numbers.

---

# 13. Commit recommendation

After passing tests, commit as:

```text
V2 Kernel Phase 2 - Move Pipeline and Inkwell Core Move
```

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable


from .commands import MoveInput
from .events import GameEvent
from .turn_owner import resolve_turn_owner_id
from .ids import InstanceId, PlayerId, ZoneId
from .random import RandomAPI, create_random_api_for_ctx
from .results import GameEndResult, LogMessage, LogVisibility, ProjectedLogEntry, RuntimeValidationResult
from .state import CtxPriority, CtxStatus, LorcanaG, MatchState
from .static_resources import MatchStaticResources
from .zones import (
    CardMeta,
    ZoneOperations,
    ZoneRef,
    ZoneRuntimePrivateState,
    ZoneRuntimePublicState,
    ZoneRuntimeState,
    build_zone_registry,
    create_zone_operations,
    patch_card_meta,
)

if TYPE_CHECKING:
    from lorcana_engine_v2.core.runtime_config import MatchRuntimeConfig
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.derived_state import DerivedState
    from lorcana_engine_v2.rules.queries import QueryService, RuntimeCard
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry


RuntimeActorRole = Literal["player", "judge"]


@dataclass(frozen=True, slots=True)
class RulesContext:
    """Static rules helper context.

    This is retained for card/query helper tests.  Mutating runtime moves must
    use ``MoveValidationContext`` / ``MoveExecutionContext`` instead.
    """

    resources: MatchStaticResources
    query: "QueryService"
    targets: "TargetResolver"
    conditions: "ConditionEvaluator"
    amounts: "AmountResolver"
    static: "StaticRegistry"
    derived: "DerivedState"

    @property
    def catalog(self):
        return self.resources.cards


def build_rules_context(resources: MatchStaticResources) -> RulesContext:
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
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
    return RulesContext(
        resources=resources,
        query=query,
        targets=targets,
        conditions=conditions,
        amounts=amounts,
        static=static,
        derived=derived,
    )


@dataclass(frozen=True, slots=True)
class MoveInputView:
    input: MoveInput
    args: Mapping[str, object]
    params: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class FrameworkStateSnapshot:
    priority: CtxPriority
    status: CtxStatus
    _zonesPrivate: ZoneRuntimePrivateState
    _zonesPublic: ZoneRuntimePublicState
    playerIds: tuple[PlayerId, ...]
    turn: int
    phase: str | None
    step: str | None
    gameSegment: str | None
    currentPlayer: PlayerId | None
    stateID: int
    matchID: str
    gameID: str
    gameEnded: bool


def create_framework_state_snapshot(state: MatchState, game_ended: bool = False) -> FrameworkStateSnapshot:
    return FrameworkStateSnapshot(
        priority=state.ctx.priority,
        status=state.ctx.status,
        _zonesPrivate=state.ctx.zones.private,
        _zonesPublic=state.ctx.zones.public,
        playerIds=state.ctx.playerIds,
        turn=state.ctx.status.turn,
        phase=state.ctx.status.phase,
        step=state.ctx.status.step,
        gameSegment=state.ctx.status.gameSegment,
        currentPlayer=resolve_turn_owner_id(state, state.G),
        stateID=state.ctx._stateID,
        matchID=state.ctx.matchID,
        gameID=state.ctx.gameID,
        gameEnded=game_ended or state.ctx.status.gameEnded,
    )


def create_move_input_view(move_input: MoveInput) -> MoveInputView:
    return MoveInputView(input=move_input, args=move_input.args, params=move_input.args)


@dataclass(slots=True)
class StateDraft:
    state: MatchState

    def set_state(self, state: MatchState) -> None:
        self.state = state

    def set_G(self, game_state: LorcanaG) -> None:
        self.state = MatchState(G=game_state, ctx=self.state.ctx)

    def set_zones(self, zones: ZoneRuntimeState) -> None:
        self.state = MatchState(G=self.state.G, ctx=self.state.ctx.with_updates(zones=zones))

    def set_status(self, status: CtxStatus) -> None:
        self.state = MatchState(G=self.state.G, ctx=self.state.ctx.with_updates(status=status))

    def set_priority(self, priority: CtxPriority) -> None:
        self.state = MatchState(G=self.state.G, ctx=self.state.ctx.with_updates(priority=priority))

    def set_random(self, random_api: RandomAPI) -> None:
        self.state = MatchState(G=self.state.G, ctx=self.state.ctx.with_updates(random=random_api.ctx_random))


class CardRuntimeReadAPI:
    def __init__(
        self,
        state_getter: Callable[[], MatchState],
        resources: MatchStaticResources,
        actor_player_id: PlayerId | str | None = None,
    ) -> None:
        from lorcana_engine_v2.rules.queries import QueryService

        self._state_getter = state_getter
        self._query = QueryService(
            resources,
            actorPlayerId=PlayerId(str(actor_player_id)) if actor_player_id is not None else None,
        )

    def require(self, card_id: InstanceId | str) -> "RuntimeCard":
        return self._query.runtime_card(self._state_getter(), card_id)

    def get(self, card_id: InstanceId | str) -> "RuntimeCard | None":
        try:
            return self.require(card_id)
        except KeyError:
            return None

    def runtime_card(self, card_id: InstanceId | str) -> "RuntimeCard":
        return self.require(card_id)

    def getDefinition(self, card_id: InstanceId | str):
        return self.require(card_id).definition

    def get_definition(self, card_id: InstanceId | str):
        return self.getDefinition(card_id)

    def getDefinitionById(self, definition_id: str):
        return self._query.getDefinitionById(definition_id)

    get_definition_by_id = getDefinitionById

    def getMeta(self, card_id: InstanceId | str) -> CardMeta:
        return self.require(card_id).meta

    def get_meta(self, card_id: InstanceId | str) -> CardMeta:
        return self.getMeta(card_id)

    def owner(self, card_id: InstanceId | str) -> PlayerId:
        return self.require(card_id).ownerID

    def controller(self, card_id: InstanceId | str) -> PlayerId:
        return self.require(card_id).controllerID

    def zone(self, card_id: InstanceId | str) -> ZoneId | None:
        return self.require(card_id).zoneID


class CardRuntimeAPI(CardRuntimeReadAPI):
    def __init__(
        self,
        draft: StateDraft,
        resources: MatchStaticResources,
        actor_player_id: PlayerId | str | None = None,
    ) -> None:
        super().__init__(lambda: draft.state, resources, actor_player_id=actor_player_id)
        self._draft = draft

    def setMeta(self, card_id: InstanceId | str, meta: CardMeta) -> CardMeta:
        zones = patch_card_meta(self._draft.state.ctx.zones, card_id, meta)
        self._draft.set_zones(zones)
        return meta

    def patchMeta(self, card_id: InstanceId | str, patch: Mapping[str, object]) -> CardMeta:
        current = self.getMeta(card_id)
        next_meta = current.with_updates(**dict(patch))
        return self.setMeta(card_id, next_meta)

    def clearMeta(self, card_id: InstanceId | str) -> None:
        card_meta = dict(self._draft.state.ctx.zones.private.cardMeta)
        card_meta.pop(InstanceId(str(card_id)), None)
        zones = ZoneRuntimeState(
            public=self._draft.state.ctx.zones.public,
            reveals=self._draft.state.ctx.zones.reveals,
            private=ZoneRuntimePrivateState(
                zoneCards=self._draft.state.ctx.zones.private.zoneCards,
                cardIndex=self._draft.state.ctx.zones.private.cardIndex,
                cardMeta=card_meta,
            ),
        )
        self._draft.set_zones(zones)

    def entriesMeta(self) -> tuple[tuple[InstanceId, CardMeta], ...]:
        return tuple(self._draft.state.ctx.zones.private.cardMeta.items())

    patch_meta = patchMeta
    set_meta = setMeta
    clear_meta = clearMeta
    entries_meta = entriesMeta


class DraftZoneOperations:
    def __init__(self, draft: StateDraft, operations: ZoneOperations) -> None:
        self._draft = draft
        self._operations = operations

    @property
    def zones(self) -> ZoneRuntimeState:
        return self._operations.zones

    def _refresh(self) -> None:
        self._operations.zones = self._draft.state.ctx.zones

    def _sync(self) -> None:
        self._draft.set_zones(self._operations.zones)

    def move_card(self, *args, **kwargs):
        self._refresh()
        result = self._operations.move_card(*args, **kwargs)
        self._sync()
        return result

    moveCard = move_card

    def move_cards(self, *args, **kwargs):
        self._refresh()
        result = self._operations.move_cards(*args, **kwargs)
        self._sync()
        return result

    moveCards = move_cards

    def draw_cards(self, *args, **kwargs):
        self._refresh()
        result = self._operations.draw_cards(*args, **kwargs)
        self._sync()
        return result

    drawCards = draw_cards

    def draw_specific_card(self, *args, **kwargs):
        self._refresh()
        result = self._operations.draw_specific_card(*args, **kwargs)
        self._sync()
        return result

    drawSpecificCard = draw_specific_card

    def mill(self, *args, **kwargs):
        self._refresh()
        result = self._operations.mill(*args, **kwargs)
        self._sync()
        return result

    def shuffle(self, *args, **kwargs):
        self._refresh()
        result = self._operations.shuffle(*args, **kwargs)
        self._sync()
        return result

    def shuffle_bottom(self, *args, **kwargs):
        self._refresh()
        result = self._operations.shuffle_bottom(*args, **kwargs)
        self._sync()
        return result

    shuffleBottom = shuffle_bottom

    def reveal(self, card_ids, visible_to, *, stateID: int | None = None, state_id: int | None = None, **_: object):
        self._refresh()
        result = self._operations.reveal(card_ids, visible_to, state_id=stateID if stateID is not None else state_id)
        self._sync()
        return result

    def reveal_top(self, *args, **kwargs):
        self._refresh()
        result = self._operations.reveal_top(*args, **kwargs)
        self._sync()
        return result

    revealTop = reveal_top

    def clear_reveal(self, *args, **kwargs):
        self._refresh()
        result = self._operations.clear_reveal(*args, **kwargs)
        self._sync()
        return result

    clearReveal = clear_reveal

    def clear_reveals_by_zone(self, *args, **kwargs):
        self._refresh()
        result = self._operations.clear_reveals_by_zone(*args, **kwargs)
        self._sync()
        return result

    clearRevealsByZone = clear_reveals_by_zone

    def get_cards(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_cards(*args, **kwargs)

    getCards = get_cards

    def get_card_count(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_card_count(*args, **kwargs)

    getCardCount = get_card_count

    def get_top_card(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_top_card(*args, **kwargs)

    getTopCard = get_top_card

    def get_bottom_card(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_bottom_card(*args, **kwargs)

    getBottomCard = get_bottom_card

    def get_card_zone(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_card_zone(*args, **kwargs)

    getCardZone = get_card_zone

    def get_card_owner(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_card_owner(*args, **kwargs)

    getCardOwner = get_card_owner

    def get_card_controller(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_card_controller(*args, **kwargs)

    getCardController = get_card_controller

    def is_ordered(self, *args, **kwargs):
        self._refresh()
        return self._operations.is_ordered(*args, **kwargs)

    isOrdered = is_ordered

    def is_owner_scoped(self, *args, **kwargs):
        self._refresh()
        return self._operations.is_owner_scoped(*args, **kwargs)

    isOwnerScoped = is_owner_scoped

    def get_visibility(self, *args, **kwargs):
        self._refresh()
        return self._operations.get_visibility(*args, **kwargs)

    getVisibility = get_visibility


class TimeQueryAPI:
    def __init__(self, state_getter: Callable[[], MatchState]) -> None:
        self._state_getter = state_getter

    def getRemainingTime(self, player_id: PlayerId | str) -> int:
        _ = player_id
        time_state = self._state_getter().ctx.time
        if getattr(time_state, "mode", "none") == "none":
            return 0
        return int(getattr(time_state, "reserveMsRemaining", 0))

    get_remaining_time = getRemainingTime


class EventAPI:
    def __init__(self, emit: Callable[[GameEvent], None], draft: StateDraft) -> None:
        self._emit = emit
        self._draft = draft

    def emit(self, event: GameEvent | Mapping[str, object]) -> None:
        self._emit(event if isinstance(event, GameEvent) else GameEvent.from_mapping(event))

    def endGame(self, result: Mapping[str, object] | GameEndResult) -> None:
        if isinstance(result, GameEndResult):
            winner = result.winner
            reason = result.reason
        else:
            raw_winner = result.get("winner")
            winner = PlayerId(str(raw_winner)) if raw_winner is not None else None
            reason = str(result.get("reason", ""))
        self._draft.set_status(
            self._draft.state.ctx.status.with_updates(
                gameEnded=True,
                winner=winner,
                reason=reason,
            )
        )
        self.emit(GameEvent(kind="GAME_ENDED", winner=winner, reason=reason))

    end_game = endGame


class UndoAPI:
    def __init__(self) -> None:
        self._reasons: list[str] = []

    def markBarrier(self, reason: str) -> None:
        self._reasons.append(reason)

    mark_barrier = markBarrier

    def hasBarrier(self) -> bool:
        return bool(self._reasons)

    has_barrier = hasBarrier

    def getReasons(self) -> tuple[str, ...]:
        return tuple(self._reasons)

    get_reasons = getReasons


class FrameworkStatusAPI:
    def __init__(self, draft: StateDraft) -> None:
        self._draft = draft

    @property
    def snapshot(self) -> CtxStatus:
        return self._draft.state.ctx.status

    def patch(self, patch: Mapping[str, object]) -> None:
        self._draft.set_status(self.snapshot.with_updates(**dict(patch)))

    def setPhase(self, phase: str | None) -> None:
        self.patch({"phase": phase})

    set_phase = setPhase

    def setStep(self, step: str | None) -> None:
        self.patch({"step": step})

    set_step = setStep

    def setGameSegment(self, segment: str | None) -> None:
        self.patch({"gameSegment": segment})

    set_game_segment = setGameSegment

    def incrementTurn(self, by: int = 1) -> int:
        next_turn = self.snapshot.turn + by
        self.patch({"turn": next_turn})
        return next_turn

    increment_turn = incrementTurn


class FrameworkPriorityAPI:
    def __init__(self, draft: StateDraft) -> None:
        self._draft = draft

    @property
    def snapshot(self) -> CtxPriority:
        return self._draft.state.ctx.priority

    def patch(self, patch: Mapping[str, object]) -> None:
        self._draft.set_priority(self.snapshot.with_updates(**dict(patch)))

    def setHolder(self, player_id: PlayerId | str | None) -> None:
        self.patch({"holder": PlayerId(str(player_id)) if player_id is not None else None})

    set_holder = setHolder

    def openWindow(self, holder: PlayerId | str | None = None) -> None:
        player_id = PlayerId(str(holder)) if holder is not None else self.snapshot.holder
        self.patch({"holder": player_id, "windowOpen": True})

    open_window = openWindow

    def closeWindow(self) -> None:
        self.patch({"windowOpen": False})

    close_window = closeWindow

    def resetPasses(self) -> None:
        self.patch({"passSequence": ()})

    reset_passes = resetPasses


@dataclass(slots=True)
class FrameworkReadAPI:
    state: FrameworkStateSnapshot
    zones: ZoneOperations
    time: TimeQueryAPI
    cards: CardRuntimeReadAPI


@dataclass(slots=True)
class FrameworkWriteAPI:
    state: FrameworkStateSnapshot
    zones: DraftZoneOperations
    time: TimeQueryAPI
    random: RandomAPI
    events: EventAPI
    undo: UndoAPI
    status: FrameworkStatusAPI
    priority: FrameworkPriorityAPI
    cards: CardRuntimeAPI
    _log_sink: Callable[[ProjectedLogEntry | Iterable[ProjectedLogEntry]], None]

    def log(self, entry: ProjectedLogEntry | Iterable[ProjectedLogEntry]) -> None:
        self._log_sink(entry)

    def logPublicWithOverrides(self, entry: Mapping[str, object]) -> None:
        default_message = entry.get("defaultMessage")
        if isinstance(default_message, LogMessage):
            message = default_message
        else:
            message = LogMessage(key=str(default_message or ""), values={})
        self.log(
            ProjectedLogEntry(
                category=str(entry.get("category", "action")),
                visibility=LogVisibility(mode="PUBLIC_WITH_OVERRIDES"),
                defaultMessage=message,
            )
        )


@dataclass(slots=True)
class MoveValidationContext:
    input: MoveInput
    args: Mapping[str, object]
    params: Mapping[str, object]
    G: LorcanaG
    playerId: PlayerId
    validationMode: Literal["preflight", "final"]
    query: object
    cards: CardRuntimeReadAPI
    framework: FrameworkReadAPI


@dataclass(slots=True)
class MoveEnumerationContext:
    G: LorcanaG
    playerId: PlayerId
    query: object
    cards: CardRuntimeReadAPI
    framework: FrameworkReadAPI


@dataclass(slots=True)
class RuntimeLifecycleContext:
    G: LorcanaG
    playerId: PlayerId | None
    query: object
    cards: CardRuntimeAPI
    framework: FrameworkWriteAPI
    _draft: StateDraft

    @property
    def state(self) -> MatchState:
        return self._draft.state

    def set_G(self, game_state: LorcanaG) -> None:
        self._draft.set_G(game_state)


@dataclass(slots=True)
class MoveExecutionContext(RuntimeLifecycleContext):
    input: MoveInput
    args: Mapping[str, object]
    params: Mapping[str, object]
    playerId: PlayerId


@runtime_checkable
class MoveDefinition(Protocol):
    serverOnly: bool
    ignorePriority: bool
    ignoreStaleStateID: bool

    def available(self, context: MoveEnumerationContext) -> bool:
        ...

    def validate(self, context: MoveValidationContext) -> RuntimeValidationResult:
        ...

    def execute(self, context: MoveExecutionContext) -> MatchState | None:
        ...


def _empty_query_api() -> object:
    return type(
        "EmptyQueryAPI",
        (),
        {
            "getActionIntents": lambda self: (),
            "getLegalActions": lambda self: (),
            "explainIllegal": lambda self: None,
        },
    )()


def _zone_registry_for(config: "MatchRuntimeConfig", state: MatchState):
    return build_zone_registry(config.zones, state.ctx.playerIds)


def _create_read_framework(
    state: MatchState,
    config: "MatchRuntimeConfig",
    resources: MatchStaticResources,
    game_ended: bool,
    events: list[GameEvent] | None = None,
    actor_player_id: PlayerId | str | None = None,
) -> FrameworkReadAPI:
    emit = events.append if events is not None else None
    cards = CardRuntimeReadAPI(lambda: state, resources, actor_player_id=actor_player_id)
    zones = create_zone_operations(
        state.ctx.zones,
        _zone_registry_for(config, state),
        emit_event=(lambda raw: emit(GameEvent.from_mapping(raw))) if emit is not None else None,
        current_state_id=state.ctx._stateID,
    )
    return FrameworkReadAPI(
        state=create_framework_state_snapshot(state, game_ended),
        zones=zones,
        time=TimeQueryAPI(lambda: state),
        cards=cards,
    )


def build_validation_context(
    *,
    state: MatchState,
    player_id: PlayerId | str,
    input: MoveInput,
    config: "MatchRuntimeConfig",
    static_resources: MatchStaticResources,
    game_ended: bool = False,
    validation_mode: Literal["preflight", "final"] = "final",
) -> MoveValidationContext:
    framework = _create_read_framework(state, config, static_resources, game_ended, actor_player_id=player_id)
    input_view = create_move_input_view(input)
    return MoveValidationContext(
        input=input_view.input,
        args=input_view.args,
        params=input_view.params,
        G=state.G,
        playerId=PlayerId(str(player_id)),
        validationMode=validation_mode,
        query=_empty_query_api(),
        cards=framework.cards,
        framework=framework,
    )


def build_enumeration_context(
    *,
    state: MatchState,
    player_id: PlayerId | str,
    config: "MatchRuntimeConfig",
    static_resources: MatchStaticResources,
    game_ended: bool = False,
) -> MoveEnumerationContext:
    framework = _create_read_framework(state, config, static_resources, game_ended, actor_player_id=player_id)
    return MoveEnumerationContext(
        G=state.G,
        playerId=PlayerId(str(player_id)),
        query=_empty_query_api(),
        cards=framework.cards,
        framework=framework,
    )


def build_lifecycle_context(
    *,
    state: MatchState,
    player_id: PlayerId | str | None,
    config: "MatchRuntimeConfig",
    static_resources: MatchStaticResources,
    game_ended: bool,
    emit: Callable[[GameEvent], None],
    undo: UndoAPI,
    move_log_sink: Callable[[ProjectedLogEntry | Iterable[ProjectedLogEntry]], None],
) -> RuntimeLifecycleContext:
    draft = StateDraft(state)
    random_api = create_random_api_for_ctx(state.ctx.random)
    cards = CardRuntimeAPI(draft, static_resources, actor_player_id=player_id)
    raw_zones = create_zone_operations(
        draft.state.ctx.zones,
        _zone_registry_for(config, draft.state),
        emit_event=lambda raw: emit(GameEvent.from_mapping(raw)),
        random_float=random_api.random,
        current_state_id=draft.state.ctx._stateID,
    )
    framework = FrameworkWriteAPI(
        state=create_framework_state_snapshot(draft.state, game_ended),
        zones=DraftZoneOperations(draft, raw_zones),
        time=TimeQueryAPI(lambda: draft.state),
        random=random_api,
        events=EventAPI(emit, draft),
        undo=undo,
        status=FrameworkStatusAPI(draft),
        priority=FrameworkPriorityAPI(draft),
        cards=cards,
        _log_sink=move_log_sink,
    )
    return RuntimeLifecycleContext(
        G=draft.state.G,
        playerId=PlayerId(str(player_id)) if player_id is not None else None,
        query=_empty_query_api(),
        cards=cards,
        framework=framework,
        _draft=draft,
    )


def build_execution_context(
    *,
    state: MatchState,
    player_id: PlayerId | str,
    input: MoveInput,
    config: "MatchRuntimeConfig",
    static_resources: MatchStaticResources,
    game_ended: bool,
    emit: Callable[[GameEvent], None],
    undo: UndoAPI,
    move_log_sink: Callable[[ProjectedLogEntry | Iterable[ProjectedLogEntry]], None],
) -> MoveExecutionContext:
    lifecycle = build_lifecycle_context(
        state=state,
        player_id=player_id,
        config=config,
        static_resources=static_resources,
        game_ended=game_ended,
        emit=emit,
        undo=undo,
        move_log_sink=move_log_sink,
    )
    input_view = create_move_input_view(input)
    return MoveExecutionContext(
        G=lifecycle.G,
        playerId=PlayerId(str(player_id)),
        query=lifecycle.query,
        cards=lifecycle.cards,
        framework=lifecycle.framework,
        _draft=lifecycle._draft,
        input=input_view.input,
        args=input_view.args,
        params=input_view.params,
    )

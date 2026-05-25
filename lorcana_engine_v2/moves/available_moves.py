from __future__ import annotations

from dataclasses import dataclass, field

from lorcana_engine_v2.core.commands import CommandEnvelope
from lorcana_engine_v2.core.context import build_enumeration_context
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.results import CommandResult
from lorcana_engine_v2.core.validation import can_player_take_actions
from lorcana_engine_v2.flow.runtime_flow import is_move_allowed_by_flow

from .ink import PUT_CARD_INTO_INKWELL, PutCardIntoInkwellMove
from .setup import ALTER_HAND, CHOOSE_WHO_GOES_FIRST, AlterHandMove, ChooseWhoGoesFirstMove


def default_move_registry() -> dict[str, object]:
    return {
        CHOOSE_WHO_GOES_FIRST: ChooseWhoGoesFirstMove(),
        ALTER_HAND: AlterHandMove(),
        PUT_CARD_INTO_INKWELL: PutCardIntoInkwellMove(),
    }


@dataclass(slots=True)
class AvailableMoveService:
    """Compatibility service over Lorcanito-style move definitions.

    The authoritative runtime path is ``MatchRuntime.enumerate_moves_for_player``
    and ``MatchRuntime.process_command``.  This adapter remains isolated for
    helper code that still asks a standalone move registry for candidate IDs.
    """

    registry: dict[str, object] = field(default_factory=default_move_registry)

    def legal_moves(self, state, player: str | PlayerId, ctx) -> tuple[str, ...]:
        actor = PlayerId(str(player))
        runtime_config = getattr(ctx, "runtime_config", None)
        if runtime_config is None:
            from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

            runtime_config = lorcana_runtime_config
        context = build_enumeration_context(
            state=state,
            player_id=actor,
            config=runtime_config,
            static_resources=ctx.resources,
        )
        moves: list[str] = []
        for move_id, move_def in self.registry.items():
            if not is_move_allowed_by_flow(
                runtime_config.flow,
                state.ctx.status.phase,
                move_id,
                state.ctx.status.gameSegment,
            ):
                continue
            if not getattr(move_def, "ignorePriority", False) and not can_player_take_actions(state, actor):
                continue
            available = getattr(move_def, "available", None)
            if available is not None and not available(context):
                continue
            moves.append(move_id)
        return tuple(moves)

    def apply(self, state, command: CommandEnvelope, ctx) -> CommandResult:
        runtime_config = getattr(ctx, "runtime_config", None)
        if runtime_config is None:
            from lorcana_engine_v2.runtime_game.definition import lorcana_runtime_config

            runtime_config = lorcana_runtime_config
        player_id = state.ctx.priority.holder or (state.ctx.playerIds[0] if state.ctx.playerIds else PlayerId("p0"))
        runtime = MatchRuntime(ctx.resources, config=runtime_config)
        runtime.load_state(state)
        return runtime.process_command(command, player_id, prev_state_id=state.ctx._stateID, actor_role="player")


__all__ = [
    "AvailableMoveService",
    "ALTER_HAND",
    "CHOOSE_WHO_GOES_FIRST",
    "AlterHandMove",
    "ChooseWhoGoesFirstMove",
    "PUT_CARD_INTO_INKWELL",
    "PutCardIntoInkwellMove",
    "default_move_registry",
]

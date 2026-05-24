from __future__ import annotations

from dataclasses import dataclass

from .commands import Command
from .context import RulesContext, build_rules_context
from .results import TransitionResult
from .state import MatchState
from lorcana_engine_v2.cards.catalog import CardCatalog


@dataclass(slots=True)
class MatchRuntime:
    """Central deterministic runtime shell for v2.

    The scaffold intentionally keeps action application small.  Future move
    modules will register move handlers here without adding card-specific logic
    to this class.
    """
    catalog: CardCatalog

    def context(self) -> RulesContext:
        return build_rules_context(self.catalog)

    def legal_moves(self, state: MatchState, player: int):
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        return AvailableMoveService().legal_moves(state, player, self.context())

    def apply(self, state: MatchState, command: Command) -> TransitionResult:
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        service = AvailableMoveService()
        return service.apply(state, command, self.context())

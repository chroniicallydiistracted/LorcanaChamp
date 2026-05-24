from __future__ import annotations

from dataclasses import dataclass

from .commands import Command
from .context import RulesContext, build_rules_context
from .results import TransitionResult
from .state import MatchState
from .static_resources import MatchStaticResources


@dataclass(slots=True)
class MatchRuntime:
    """Central deterministic runtime shell for v2.

    Runtime is created from immutable MatchStaticResources, not directly from a
    mutable card dictionary.  Future move modules will continue to receive a
    RulesContext rather than importing card catalogs or legacy v1 runtime code.
    """
    resources: MatchStaticResources

    def context(self) -> RulesContext:
        return build_rules_context(self.resources)

    def legal_moves(self, state: MatchState, player: str):
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        return AvailableMoveService().legal_moves(state, player, self.context())

    def apply(self, state: MatchState, command: Command) -> TransitionResult:
        from lorcana_engine_v2.moves.available_moves import AvailableMoveService
        service = AvailableMoveService()
        return service.apply(state, command, self.context())

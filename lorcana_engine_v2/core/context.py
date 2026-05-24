from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorcana_engine_v2.core.static_resources import MatchStaticResources
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState


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

    @property
    def catalog(self):
        return self.resources.cards


def build_rules_context(resources: "MatchStaticResources") -> RulesContext:
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState

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

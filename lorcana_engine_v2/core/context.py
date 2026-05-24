from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorcana_engine_v2.cards.catalog import CardCatalog
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState


@dataclass(frozen=True, slots=True)
class RulesContext:
    """Shared rules context.

    All v2 subsystems receive this context rather than importing each other or
    the legacy v1 runtime.  This mirrors Lorcanito's centralized query/context
    model.
    """
    catalog: "CardCatalog"
    query: "QueryService"
    targets: "TargetResolver"
    conditions: "ConditionEvaluator"
    amounts: "AmountResolver"
    static: "StaticRegistry"
    derived: "DerivedState"


def build_rules_context(catalog: "CardCatalog") -> RulesContext:
    from lorcana_engine_v2.rules.queries import QueryService
    from lorcana_engine_v2.rules.target_resolver import TargetResolver
    from lorcana_engine_v2.rules.condition_evaluator import ConditionEvaluator
    from lorcana_engine_v2.rules.amount_resolver import AmountResolver
    from lorcana_engine_v2.registries.static_registry import StaticRegistry
    from lorcana_engine_v2.rules.derived_state import DerivedState

    query = QueryService(catalog)
    targets = TargetResolver()
    conditions = ConditionEvaluator()
    amounts = AmountResolver()
    static = StaticRegistry()
    derived = DerivedState()
    return RulesContext(
        catalog=catalog,
        query=query,
        targets=targets,
        conditions=conditions,
        amounts=amounts,
        static=static,
        derived=derived,
    )

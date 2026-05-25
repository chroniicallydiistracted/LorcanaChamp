from __future__ import annotations

from lorcana_engine_v2.rules.play_card_rules import (
    BasicCost,
    ExertCostCard,
    PayBasicCostResult,
    get_available_ink,
    pay_basic_cost,
    spend_ink,
    validate_basic_cost,
    validate_exert_cost,
)


class CostsService:
    get_available_ink = staticmethod(get_available_ink)
    spend_ink = staticmethod(spend_ink)
    validate_basic_cost = staticmethod(validate_basic_cost)
    pay_basic_cost = staticmethod(pay_basic_cost)
    validate_exert_cost = staticmethod(validate_exert_cost)


__all__ = [
    "BasicCost",
    "CostsService",
    "ExertCostCard",
    "PayBasicCostResult",
    "get_available_ink",
    "pay_basic_cost",
    "spend_ink",
    "validate_basic_cost",
    "validate_exert_cost",
]

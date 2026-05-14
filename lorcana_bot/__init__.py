"""Lorcana Core Constructed bot engine scaffold."""

from .cards import CardDatabase, CardDef, EffectDef, FormatRules, load_card_database, load_demo_database, load_official_database
from .effects import EffectResolver
from .effect_types import EffectResolutionContext
from .engine import GameEngine, GameRunner
from .bots import RandomLegalBot, GreedyLoreBot, HeuristicBot, LinearPolicyBot

__all__ = [
    "CardDatabase",
    "CardDef",
    "EffectDef",
    "FormatRules",
    "load_demo_database",
    "load_official_database",
    "load_card_database",
    "EffectResolver",
    "EffectResolutionContext",
    "GameEngine",
    "GameRunner",
    "RandomLegalBot",
    "GreedyLoreBot",
    "HeuristicBot",
    "LinearPolicyBot",
]

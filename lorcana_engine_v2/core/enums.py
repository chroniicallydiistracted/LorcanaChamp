from __future__ import annotations

from enum import StrEnum

class Zone(StrEnum):
    DECK = "deck"
    HAND = "hand"
    PLAY = "play"
    DISCARD = "discard"
    INKWELL = "inkwell"
    LIMBO = "limbo"
    UNDER = "under"

class CardType(StrEnum):
    CHARACTER = "character"
    ACTION = "action"
    ITEM = "item"
    LOCATION = "location"

class Stat(StrEnum):
    STRENGTH = "strength"
    WILLPOWER = "willpower"
    LORE = "lore"

class Keyword(StrEnum):
    BODYGUARD = "BODYGUARD"
    EVASIVE = "EVASIVE"
    RECKLESS = "RECKLESS"
    RESIST = "RESIST"
    RUSH = "RUSH"
    WARD = "WARD"
    SUPPORT = "SUPPORT"
    CHALLENGER = "CHALLENGER"
    SINGER = "SINGER"
    SHIFT = "SHIFT"

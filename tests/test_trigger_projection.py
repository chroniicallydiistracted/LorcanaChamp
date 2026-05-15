"""Tests for source trigger projection in lorcanito_source_mapper.py"""

import pytest
from lorcana_bot.cards import CardDef
from lorcana_bot.importers.lorcanito_source_mapper import (
    project_triggers,
    SUPPORTED_TRIGGER_EVENTS,
    SUPPORTED_TRIGGER_EFFECT_KINDS,
)


def _make_source_ability(kind, trigger_event=None, effect_kind="draw", optional=True, is_static=False):
    """Helper to create SourceAbilityDef for tests."""
    from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus
    
    trigger = None
    if trigger_event:
        trigger = SourceTriggerDef(
            event=trigger_event,
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
    
    effect = SourceEffectDef(
        kind=effect_kind,
        raw={},
        mapping_status="structurally_mapped",
        execution_status=ExecutionStatus.EXECUTABLE,
    )
    
    return SourceAbilityDef(
        id=f"{kind}_ability",
        kind=kind if not is_static else "static",
        name=f"Test {kind}",
        effects=(effect,),
        trigger=trigger,
        costs=(),
        condition=None,
        restrictions=(),
        source_zones=(),
        raw={"type": kind},
        mapping_status="structurally_mapped",
        execution_status=ExecutionStatus.EXECUTABLE if not trigger else ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        auto_resolve=None if optional else True,
    )


class TestProjectTriggers:
    """Tests for project_triggers() function."""

    def test_empty_source_abilities_returns_empty(self):
        """Cards with no source abilities return empty tuple."""
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        assert project_triggers(card) == ()

    def test_action_ability_not_projected_as_trigger(self):
        """Action abilities should not be projected as triggers."""
        card = CardDef(
            id="test_action",
            full_name="Test Action Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="action",
        )
        ability = _make_source_ability("action")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert result == ()

    def test_supported_trigger_event_projects(self):
        """Triggers with supported events should be projected."""
        card = CardDef(
            id="test_trigger",
            full_name="Test Trigger Card",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        
        ability = _make_source_ability("triggered", trigger_event="play", effect_kind="draw")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1
        assert result[0].event == "play"

    def test_unsupported_trigger_event_not_projected(self):
        """Triggers with unsupported events should not be projected."""
        card = CardDef(
            id="test_unsupported",
            full_name="Test Unsupported Trigger Card",
            ink="amethyst",
            cost=4,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=3,
            lore=2,
        )
        
        # sing event is not supported
        ability = _make_source_ability("triggered", trigger_event="sing", effect_kind="draw")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert result == ()

    def test_unsupported_effect_not_projected(self):
        """Triggers with unsupported effects should not be projected."""
        card = CardDef(
            id="test_scry",
            full_name="Test Scry Trigger Card",
            ink="sapphire",
            cost=2,
            inkable=True,
            card_type="character",
            strength=1,
            willpower=2,
            lore=1,
        )
        
        # shift effect is not supported for trigger projection
        ability = _make_source_ability("triggered", trigger_event="play", effect_kind="shift")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert result == ()

    def test_quest_trigger_with_gain_lore_projects(self):
        """Quest triggers with gain_lore should project."""
        card = CardDef(
            id="quest_trigger_card",
            full_name="Quest Trigger Card",
            ink="ruby",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=2,
        )
        
        ability = _make_source_ability("triggered", trigger_event="quest", effect_kind="gain-lore")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1
        assert result[0].event == "quest"

    def test_static_ability_not_projected_as_trigger(self):
        """Static abilities should not be projected as triggers."""
        card = CardDef(
            id="static_card",
            full_name="Static Card",
            ink="emerald",
            cost=4,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=3,
            lore=1,
        )
        
        ability = _make_source_ability("static", is_static=True)
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert result == ()


class TestSupportedTriggerEvents:
    """Tests for supported trigger event constants."""

    def test_play_is_supported(self):
        assert "play" in SUPPORTED_TRIGGER_EVENTS

    def test_quest_is_supported(self):
        assert "quest" in SUPPORTED_TRIGGER_EVENTS

    def test_challenge_is_supported(self):
        assert "challenge" in SUPPORTED_TRIGGER_EVENTS

    def test_sing_not_supported(self):
        """Singer/Songs triggers are not supported in B2."""
        assert "sing" not in SUPPORTED_TRIGGER_EVENTS

    def test_shift_not_supported(self):
        """Shift triggers are not supported in B2."""
        assert "shift" not in SUPPORTED_TRIGGER_EVENTS


class TestSupportedTriggerEffectKinds:
    """Tests for supported trigger effect kinds."""

    def test_draw_supported(self):
        assert "draw" in SUPPORTED_TRIGGER_EFFECT_KINDS

    def test_gain_lore_supported(self):
        assert "gain-lore" in SUPPORTED_TRIGGER_EFFECT_KINDS

    def test_deal_damage_supported(self):
        assert "deal-damage" in SUPPORTED_TRIGGER_EFFECT_KINDS

    def test_scry_not_supported(self):
        """Scry effect is not supported in B2."""
        assert "scry" not in SUPPORTED_TRIGGER_EFFECT_KINDS

    def test_search_deck_not_supported(self):
        """Search deck effect is not supported in B2."""
        assert "search-deck" not in SUPPORTED_TRIGGER_EFFECT_KINDS


class TestEventDerivedTargetProjection:
    """Tests for event-derived target projection in trigger projection."""

    def _make_trigger_with_target(self, effect_kind, target_alias):
        """Create a triggered ability with a specific target alias."""
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTargetDef, SourceTriggerDef, ExecutionStatus
        
        trigger = SourceTriggerDef(
            event="challenge",
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
        
        target = SourceTargetDef(
            kind="alias",
            alias=target_alias,
            raw={"value": target_alias},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        effect = SourceEffectDef(
            kind=effect_kind,
            target=target,
            raw={"type": effect_kind, "target": target_alias},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        return SourceAbilityDef(
            id=f"triggered_with_{target_alias}",
            kind="triggered",
            name=f"Test {target_alias}",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "effect": {"type": effect_kind, "target": target_alias}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

    def test_event_source_target_projects(self):
        """EVENT_SOURCE target should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "EVENT_SOURCE")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1

    def test_event_target_target_projects(self):
        """EVENT_TARGET target should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "EVENT_TARGET")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1

    def test_trigger_subject_target_projects(self):
        """TRIGGER_SUBJECT target should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "TRIGGER_SUBJECT")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1

    def test_your_other_characters_target_projects(self):
        """YOUR_OTHER_CHARACTERS target should project correctly."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "YOUR_OTHER_CHARACTERS")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1

    def test_all_opposing_characters_target_projects(self):
        """ALL_OPPOSING_CHARACTERS target should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "ALL_OPPOSING_CHARACTERS")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        result = project_triggers(card)
        assert len(result) == 1

    def test_chosen_character_target_now_projects(self):
        """CHOSEN_CHARACTER target now projects via pending effect layer (B3)."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        
        card = CardDef(
            id="test_card",
            full_name="Test Card",
            ink="amber",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        ability = self._make_trigger_with_target("deal-damage", "CHOSEN_CHARACTER")
        object.__setattr__(card, 'source_abilities', (ability,))
        
        # B3: CHOSEN_CHARACTER now projects because pending effect layer
        # handles target prompts at runtime
        result = project_triggers(card)
        assert len(result) == 1
        assert result[0].effects[0].target == "chosen_character"


class TestQuestTriggerGainLore:
    """Tests for quest trigger gaining lore for controller."""

    def test_quest_trigger_with_controller_target(self):
        """Quest trigger with gain-lore should project for controller."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTargetDef, SourceTriggerDef, ExecutionStatus
        
        card = CardDef(
            id="quest_lore_card",
            full_name="Quest Lore Card",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        
        trigger = SourceTriggerDef(
            event="quest",
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
        
        target = SourceTargetDef(
            kind="alias",
            alias="CONTROLLER",
            raw={"value": "CONTROLLER"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        effect = SourceEffectDef(
            kind="gain-lore",
            target=target,
            amount=1,
            raw={"type": "gain-lore", "target": "CONTROLLER", "amount": 1},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        ability = SourceAbilityDef(
            id="quest_gain_lore",
            kind="triggered",
            name="Quest Gain Lore",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "quest"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )
        
        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)
        
        assert len(result) == 1
        assert result[0].event == "quest"
        assert result[0].effects[0].target == "controller"


class TestChallengeTriggerDamagesEventTarget:
    """Tests for challenge trigger damaging event target."""

    def test_challenge_trigger_with_event_target(self):
        """Challenge trigger with deal-damage to event_target should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTargetDef, SourceTriggerDef, ExecutionStatus
        
        card = CardDef(
            id="challenge_damage_card",
            full_name="Challenge Damage Card",
            ink="ruby",
            cost=3,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=2,
            lore=1,
        )
        
        trigger = SourceTriggerDef(
            event="challenge",
            on="SELF",
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
        
        target = SourceTargetDef(
            kind="alias",
            alias="EVENT_TARGET",
            raw={"value": "EVENT_TARGET"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        effect = SourceEffectDef(
            kind="deal-damage",
            target=target,
            amount=2,
            raw={"type": "deal-damage", "target": "EVENT_TARGET", "amount": 2},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        ability = SourceAbilityDef(
            id="challenge_deal_damage",
            kind="triggered",
            name="Challenge Deal Damage",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "challenge", "on": "SELF"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )
        
        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)
        
        assert len(result) == 1
        assert result[0].event == "challenge"
        assert result[0].effects[0].target == "event_target"


class TestBanishTriggerDrawsForController:
    """Tests for banish trigger drawing for controller."""

    def test_banish_trigger_draws_for_controller(self):
        """Banish trigger with draw for controller should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTargetDef, SourceTriggerDef, ExecutionStatus
        
        card = CardDef(
            id="banish_draw_card",
            full_name="Banish Draw Card",
            ink="sapphire",
            cost=2,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )
        
        trigger = SourceTriggerDef(
            event="banish",
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
        
        effect = SourceEffectDef(
            kind="draw",
            amount=1,
            raw={"type": "draw", "amount": 1},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        
        ability = SourceAbilityDef(
            id="banish_draw",
            kind="triggered",
            name="Banish Draw",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "banish"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )
        
        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)
        
        assert len(result) == 1
        assert result[0].event == "banish"
        assert result[0].effects[0].kind == "draw"

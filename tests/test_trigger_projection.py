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

    def test_microfix_11_events_are_supported(self):
        assert "banish-in-challenge" in SUPPORTED_TRIGGER_EVENTS
        assert "put-card-under" in SUPPORTED_TRIGGER_EVENTS
        assert "draw" in SUPPORTED_TRIGGER_EVENTS
        assert "leave-play" in SUPPORTED_TRIGGER_EVENTS

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

    def test_scry_supported(self):
        """Scry effects are supported by the current engine projection layer."""
        assert "scry" in SUPPORTED_TRIGGER_EFFECT_KINDS

    def test_search_deck_supported(self):
        """Search deck effects are supported by the current engine projection layer."""
        assert "search-deck" in SUPPORTED_TRIGGER_EFFECT_KINDS


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
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

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


class TestMicrofix11TriggerProjections:
    """Tests for microfix 11 trigger event projections."""

    def test_banish_in_challenge_trigger_projects(self):
        """Banish-in-challenge trigger should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="banish_in_challenge_card",
            full_name="Banish In Challenge Card",
            ink="amber",
            cost=3,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=2,
            lore=1,
        )

        trigger = SourceTriggerDef(
            event="banish-in-challenge",
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        effect = SourceEffectDef(
            kind="gain-lore",
            amount=1,
            raw={"type": "gain-lore", "amount": 1},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="banish_in_challenge_gain_lore",
            kind="triggered",
            name="Banish In Challenge Gain Lore",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "banish-in-challenge"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        assert len(result) == 1
        assert result[0].event == "banish-in-challenge"
        assert result[0].effects[0].kind == "gain_lore"

    def test_put_card_under_trigger_projects(self):
        """Put-card-under trigger should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="put_card_under_card",
            full_name="Put Card Under Card",
            ink="emerald",
            cost=4,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=3,
            lore=2,
        )

        trigger = SourceTriggerDef(
            event="put-card-under",
            on=None,
            timing=None,
            subject=None,
            raw={},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        effect = SourceEffectDef(
            kind="draw",
            amount=2,
            raw={"type": "draw", "amount": 2},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="put_card_under_draw",
            kind="triggered",
            name="Put Card Under Draw",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "put-card-under"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        assert len(result) == 1
        assert result[0].event == "put-card-under"
        assert result[0].effects[0].kind == "draw"

    def test_leave_play_trigger_projects(self):
        """Leave-play trigger should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="leave_play_card",
            full_name="Leave Play Card",
            ink="ruby",
            cost=2,
            inkable=True,
            card_type="character",
            strength=1,
            willpower=2,
            lore=1,
        )

        trigger = SourceTriggerDef(
            event="leave-play",
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
            id="leave_play_draw",
            kind="triggered",
            name="Leave Play Draw",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "leave-play"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        assert len(result) == 1
        assert result[0].event == "leave-play"
        assert result[0].effects[0].kind == "draw"


class TestMicrofix2CTriggerOnProjections:
    """Tests for microfix 2C trigger on filter projections."""

    def test_trigger_with_characters_here_projects(self):
        """Trigger with CHARACTERS_HERE on value should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, SUPPORTED_TRIGGER_ON_VALUES
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # 2C: Verify CHARACTERS_HERE is supported
        assert "CHARACTERS_HERE" in SUPPORTED_TRIGGER_ON_VALUES

        card = CardDef(
            id="characters_here_card",
            full_name="Characters Here Card",
            ink="amber",
            cost=4,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=3,
            lore=2,
        )

        trigger = SourceTriggerDef(
            event="banish",
            on="CHARACTERS_HERE",  # 2C: Now supported string filter
            timing=None,
            subject=None,
            raw={"event": "banish", "on": "CHARACTERS_HERE"},
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
            id="characters_here_banish_draw",
            kind="triggered",
            name="Characters Here Banish Draw",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "banish", "on": "CHARACTERS_HERE"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 2C: Should project because CHARACTERS_HERE is now supported
        assert len(result) == 1
        assert result[0].event == "banish"
        assert result[0].on == "CHARACTERS_HERE"
        assert result[0].effects[0].kind == "draw"

    def test_trigger_with_object_filter_ink_type_projects(self):
        """Trigger with ink-type object filter should project (Pluto style)."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, SUPPORTED_TRIGGER_ON_VALUES
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # 2C: Verify the keys/types are supported
        from lorcana_bot.decks.trigger_blocker_report import SUPPORTED_FILTER_KEYS, SUPPORTED_FILTER_TYPES
        assert "filters" in SUPPORTED_FILTER_KEYS
        assert "ink-type" in SUPPORTED_FILTER_TYPES

        card = CardDef(
            id="pluto_style_card",
            full_name="Pluto Style Card",
            ink="steel",
            cost=5,
            inkable=True,
            card_type="character",
            strength=4,
            willpower=4,
            lore=3,
        )

        # Pluto-style trigger with ink-type filter
        trigger = SourceTriggerDef(
            event="banish-in-challenge",
            on={
                "cardType": "character",
                "controller": "you",
                "excludeSelf": True,
                "filters": [{"type": "ink-type", "inkType": "steel"}],
            },
            timing=None,
            subject=None,
            raw={
                "event": "banish-in-challenge",
                "on": {
                    "cardType": "character",
                    "controller": "you",
                    "excludeSelf": True,
                    "filters": [{"type": "ink-type", "inkType": "steel"}],
                },
            },
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        effect = SourceEffectDef(
            kind="gain-lore",
            amount=2,
            raw={"type": "gain-lore", "amount": 2},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="pluto_style_trigger",
            kind="triggered",
            name="Pluto Style Trigger",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={
                "type": "triggered",
                "trigger": {
                    "event": "banish-in-challenge",
                    "on": {
                        "cardType": "character",
                        "controller": "you",
                        "excludeSelf": True,
                        "filters": [{"type": "ink-type", "inkType": "steel"}],
                    },
                },
            },
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 2C: Should project because ink-type filter is now supported
        assert len(result) == 1
        assert result[0].event == "banish-in-challenge"
        assert isinstance(result[0].on, dict)
        assert result[0].on["cardType"] == "character"
        assert result[0].on["controller"] == "you"
        assert result[0].on["excludeSelf"] == True
        assert result[0].effects[0].kind == "gain_lore"


class TestMicrofix3CConditionProjection:
    """Tests for microfix 3C condition projection."""

    def test_trigger_with_has_card_under_condition_projects(self):
        """Trigger with has-card-under condition should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, SUPPORTED_CONDITION_KINDS
        from lorcana_bot.card_logic import SourceAbilityDef, SourceConditionDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # 3C: Verify has-card-under is supported
        assert "has-card-under" in SUPPORTED_CONDITION_KINDS

        card = CardDef(
            id="has_card_under_card",
            full_name="Has Card Under Card",
            ink="emerald",
            cost=4,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=3,
            lore=2,
        )

        trigger = SourceTriggerDef(
            event="put-card-under",
            on=None,
            timing=None,
            subject=None,
            raw={"event": "put-card-under"},
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

        condition = SourceConditionDef(
            kind="has-card-under",
            operands=(),
            subject=None,
            comparison=None,
            value=None,
            raw={"type": "has-card-under"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="has_card_under_draw",
            kind="triggered",
            name="Has Card Under Draw",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=condition,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "put-card-under"}, "condition": {"type": "has-card-under"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 3C: Should project because has-card-under is now supported
        assert len(result) == 1
        assert result[0].event == "put-card-under"
        assert result[0].condition["kind"] == "has-card-under"
        assert result[0].effects[0].kind == "draw"

    def test_trigger_with_turn_metric_condition_projects(self):
        """Trigger with turn-metric condition should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, SUPPORTED_CONDITION_KINDS
        from lorcana_bot.card_logic import SourceAbilityDef, SourceConditionDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # 3C: Verify turn-metric is supported
        assert "turn-metric" in SUPPORTED_CONDITION_KINDS

        card = CardDef(
            id="turn_metric_card",
            full_name="Turn Metric Card",
            ink="sapphire",
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
            raw={"event": "quest"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        effect = SourceEffectDef(
            kind="gain-lore",
            amount=2,
            raw={"type": "gain-lore", "amount": 2},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        condition = SourceConditionDef(
            kind="turn-metric",
            operands=(),
            subject=None,
            comparison={"operator": "gte", "value": 3},
            value=3,
            raw={
                "type": "turn-metric",
                "metric": "banished-characters",
                "ownerScope": "you",
                "classification": "Toy",
                "comparison": {"operator": "gte", "value": 3},
            },
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="turn_metric_gain_lore",
            kind="triggered",
            name="Turn Metric Gain Lore",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=condition,
            restrictions=(),
            source_zones=(),
            raw={
                "type": "triggered",
                "trigger": {"event": "quest"},
                "condition": {
                    "type": "turn-metric",
                    "metric": "banished-characters",
                    "ownerScope": "you",
                    "classification": "Toy",
                    "comparison": {"operator": "gte", "value": 3},
                },
            },
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 3C: Should project because turn-metric is now supported
        assert len(result) == 1
        assert result[0].event == "quest"
        assert result[0].condition["kind"] == "turn-metric"
        assert result[0].condition["metric"] == "banished-characters"
        assert result[0].condition["ownerScope"] == "you"
        assert result[0].condition["classification"] == "Toy"
        assert result[0].condition["comparison"] == {"operator": "gte", "value": 3}
        assert result[0].effects[0].kind == "gain_lore"

    def test_trigger_with_used_shift_condition_projects(self):
        """Trigger with used-shift condition should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, SUPPORTED_CONDITION_KINDS
        from lorcana_bot.card_logic import SourceAbilityDef, SourceConditionDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        assert "used-shift" in SUPPORTED_CONDITION_KINDS

        card = CardDef(
            id="used_shift_card",
            full_name="Used Shift Card",
            ink="steel",
            cost=4,
            inkable=True,
            card_type="character",
            strength=4,
            willpower=4,
            lore=1,
        )
        trigger = SourceTriggerDef(
            event="play",
            on="SELF",
            timing="when",
            subject=None,
            raw={"event": "play", "on": "SELF"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )
        effect = SourceEffectDef(
            kind="gain-lore",
            amount=1,
            raw={"type": "gain-lore", "amount": 1},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        condition = SourceConditionDef(
            kind="used-shift",
            raw={"type": "used-shift"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        ability = SourceAbilityDef(
            id="used_shift_trigger",
            kind="triggered",
            name="Used Shift Trigger",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=condition,
            restrictions=(),
            source_zones=(),
            raw={
                "type": "triggered",
                "trigger": {"event": "play", "on": "SELF"},
                "condition": {"type": "used-shift"},
            },
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, "source_abilities", (ability,))
        result = project_triggers(card)

        assert len(result) == 1
        assert result[0].event == "play"
        assert result[0].on == "SELF"
        assert result[0].condition["kind"] == "used-shift"
        assert result[0].condition["type"] == "used-shift"


class TestMicrofix4CAmountProjection:
    """Tests for microfix 4C amount shape projection."""

    def test_dynamic_amount_shape_supported_by_runtime_projects(self):
        """Trigger effect with supported amount shape should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, _get_amount_shape
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # Verify supported amount shapes are recognized
        assert _get_amount_shape(2) == "static_integer"
        assert _get_amount_shape("3") == "numeric_string"
        assert _get_amount_shape({"type": "static", "amount": 1}) == "static_object"
        assert _get_amount_shape({"type": "event-snapshot", "key": "drawnCount"}) == "event_snapshot_drawn_count"
        assert _get_amount_shape({"type": "event-snapshot", "key": "cardsUnderCountBeforeBanish"}) == "event_snapshot_cards_under_count"

        card = CardDef(
            id="amount_shape_card",
            full_name="Amount Shape Card",
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
            raw={"event": "quest"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        # Test with static integer amount
        effect = SourceEffectDef(
            kind="gain-lore",
            amount=2,
            raw={"type": "gain-lore", "amount": 2},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="static_amount_quest",
            kind="triggered",
            name="Static Amount Quest",
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

        # 4C: Should project because static_integer amount shape is supported
        assert len(result) == 1
        assert result[0].event == "quest"
        assert result[0].effects[0].kind == "gain_lore"
        assert result[0].effects[0].amount == 2

    def test_event_snapshot_amount_shape_projects(self):
        """Trigger effect with event-snapshot amount shape should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="event_snapshot_card",
            full_name="Event Snapshot Card",
            ink="sapphire",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )

        trigger = SourceTriggerDef(
            event="draw",
            on=None,
            timing=None,
            subject=None,
            raw={"event": "draw"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        # Event-snapshot amount shape (drawnCount)
        effect = SourceEffectDef(
            kind="gain-lore",
            amount=None,
            raw={"type": "gain-lore", "amount": {"type": "event-snapshot", "key": "drawnCount"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="event_snapshot_gain_lore",
            kind="triggered",
            name="Event Snapshot Gain Lore",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "draw"}, "effect": {"type": "gain-lore", "amount": {"type": "event-snapshot", "key": "drawnCount"}}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 4C: Should project because event_snapshot_drawn_count is supported
        assert len(result) == 1
        assert result[0].event == "draw"
        assert result[0].effects[0].kind == "gain_lore"

    def test_unsupported_amount_shape_does_not_project(self):
        """Trigger effect with unsupported amount shape should not project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers, _get_amount_shape
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        # Verify unsupported shapes return None
        assert _get_amount_shape({"type": "dynamic", "key": "unknown"}) is None
        assert _get_amount_shape({"type": "event-snapshot", "key": "unknownKey"}) is None
        assert _get_amount_shape([1, 2, 3]) is None

        card = CardDef(
            id="unsupported_amount_card",
            full_name="Unsupported Amount Card",
            ink="ruby",
            cost=4,
            inkable=True,
            card_type="character",
            strength=3,
            willpower=3,
            lore=2,
        )

        trigger = SourceTriggerDef(
            event="challenge",
            on=None,
            timing=None,
            subject=None,
            raw={"event": "challenge"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        # Unsupported amount shape - complex dynamic expression
        effect = SourceEffectDef(
            kind="deal-damage",
            amount=None,
            raw={"type": "deal-damage", "amount": {"type": "dynamic", "key": "opponentCharacterCount"}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="unsupported_dynamic_amount",
            kind="triggered",
            name="Unsupported Dynamic Amount",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "challenge"}, "effect": {"type": "deal-damage", "amount": {"type": "dynamic", "key": "opponentCharacterCount"}}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 4C: Should NOT project because unsupported amount shape causes _project_trigger_effect to return None
        assert len(result) == 0

    def test_unsupported_amount_shape_in_source_amount_does_not_project(self):
        """Unsupported SourceEffectDef.amount shapes must not project when raw lacks amount."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="unsupported_source_amount_card",
            full_name="Unsupported Source Amount Card",
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
        effect = SourceEffectDef(
            kind="gain-lore",
            amount={"type": "dynamic", "key": "unknown"},
            raw={"type": "gain-lore"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )
        ability = SourceAbilityDef(
            id="unsupported_source_amount",
            kind="triggered",
            name="Unsupported Source Amount",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, "source_abilities", (ability,))

        assert project_triggers(card) == ()

    def test_static_object_amount_shape_projects(self):
        """Trigger effect with static object amount shape should project."""
        from lorcana_bot.importers.lorcanito_source_mapper import project_triggers
        from lorcana_bot.card_logic import SourceAbilityDef, SourceEffectDef, SourceTriggerDef, ExecutionStatus

        card = CardDef(
            id="static_object_card",
            full_name="Static Object Card",
            ink="emerald",
            cost=3,
            inkable=True,
            card_type="character",
            strength=2,
            willpower=2,
            lore=1,
        )

        trigger = SourceTriggerDef(
            event="gain-lore",
            on=None,
            timing=None,
            subject=None,
            raw={"event": "gain-lore"},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
        )

        # Static object amount shape
        effect = SourceEffectDef(
            kind="gain-lore",
            amount=None,
            raw={"type": "gain-lore", "amount": {"type": "static", "amount": 3}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.EXECUTABLE,
        )

        ability = SourceAbilityDef(
            id="static_object_gain_lore",
            kind="triggered",
            name="Static Object Gain Lore",
            effects=(effect,),
            trigger=trigger,
            costs=(),
            condition=None,
            restrictions=(),
            source_zones=(),
            raw={"type": "triggered", "trigger": {"event": "gain-lore"}, "effect": {"type": "gain-lore", "amount": {"type": "static", "amount": 3}}},
            mapping_status="structurally_mapped",
            execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
            auto_resolve=None,
        )

        object.__setattr__(card, 'source_abilities', (ability,))
        result = project_triggers(card)

        # 4C: Should project because static_object amount shape is supported
        assert len(result) == 1
        assert result[0].event == "gain-lore"
        assert result[0].effects[0].kind == "gain_lore"

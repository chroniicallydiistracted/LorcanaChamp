from lorcana_bot.card_logic import (
    ExecutionStatus,
    MappingStatus,
    SourceAbilityDef,
    SourceConditionDef,
    SourceCostDef,
    SourceEffectDef,
    SourceStaticEffectDef,
    SourceTargetDef,
    SourceTriggerDef,
)
from lorcana_bot.cards import CardDef, KeywordDef
from lorcana_bot.decks.deck_mapping_report import build_suite_mapping_report
from lorcana_bot.decks.deck_schema import ResolvedDeck, ResolvedDeckCard
from lorcana_bot.decks.runtime_executability import classify_card_runtime_support, classify_deck_runtime_support


def _card(card_id="a", **overrides):
    values = {
        "id": card_id,
        "full_name": card_id.upper(),
        "ink": "amber",
        "cost": 2,
        "inkable": True,
        "card_type": "character",
        "strength": 1,
        "willpower": 2,
        "lore": 1,
        "source_execution_status": "executable",
    }
    values.update(overrides)
    return CardDef(**values)


def _resolved_card(card_id="a", blockers=()):
    return ResolvedDeckCard(
        raw_name=card_id.upper(),
        count=4,
        raw_type="character",
        resolved=True,
        resolution_status="resolved",
        card_id=card_id,
        full_name=card_id.upper(),
        colors=("amber",),
        card_type="character",
        source_execution_status="mapped_not_executable" if blockers else "executable",
        unsupported_blockers=tuple(blockers),
    )


def _deck(cards):
    total = sum(card.count for card in cards)
    return ResolvedDeck(
        schema_version=1,
        id="deck",
        name="Deck",
        format="core_constructed",
        source_site=None,
        source_deck_id=None,
        player=None,
        placement=None,
        event=None,
        event_date=None,
        raw_ink_colors=("amber",),
        resolved_ink_colors=("amber",),
        archetype=None,
        purpose=(),
        deck_total_declared=total,
        deck_total_resolved=total,
        cards=tuple(cards),
        playable_decklist_ids=tuple(card.card_id for card in cards for _ in range(card.count) if card.card_id),
        validation={"valid": True, "unresolved_cards": [], "ambiguous_cards": [], "banned_cards": []},
        mapping_summary={},
        playability="source_only",
    )


def test_stale_shift_blocker_is_ignored_when_current_shift_runtime_is_supported():
    card_def = _card("shift", full_name="Shift Hero", keywords=("SHIFT(2)",))
    resolved = _resolved_card("shift", blockers=("keyword:SHIFT",))

    result = classify_card_runtime_support(card_def, resolved)

    assert result.status == "executable"
    assert result.blockers == ()
    assert result.stale_blockers_ignored == ("keyword:SHIFT",)
    assert "legal_actions:PLAY_SHIFTED" in result.runtime_paths_verified
    assert "apply_action:PLAY_SHIFTED" in result.runtime_paths_verified


def test_supported_static_effect_does_not_emit_broad_static_blocker():
    static = SourceStaticEffectDef(
        kind="cost-reduction",
        effect=SourceEffectDef(kind="cost-reduction", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED, execution_status=ExecutionStatus.UNSUPPORTED_STATIC_EFFECT),
    )
    card_def = _card("static", source_static_abilities=(static,), source_execution_status=ExecutionStatus.UNSUPPORTED_STATIC_EFFECT)

    result = classify_card_runtime_support(card_def, _resolved_card("static", blockers=("unsupported_static_effect",)))

    assert result.status == "executable"
    assert "unsupported_static_effect" not in result.blockers
    assert result.stale_blockers_ignored == ("unsupported_static_effect",)
    assert "static_registry" in result.runtime_paths_verified
    assert "leave_play_cleanup" in result.runtime_paths_verified


def test_stale_trigger_blocker_is_replaced_by_fresh_trigger_projection():
    trigger = SourceTriggerDef(
        event="play",
        on="SELF",
        raw={"event": "play", "on": "SELF"},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
    )
    ability = SourceAbilityDef(
        id="draw-on-play",
        kind="triggered",
        effects=(
            SourceEffectDef(
                kind="draw",
                amount=1,
                mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                execution_status=ExecutionStatus.EXECUTABLE,
            ),
        ),
        trigger=trigger,
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
    )
    card_def = _card("trigger", source_abilities=(ability,), source_execution_status=ExecutionStatus.UNSUPPORTED_TRIGGER)

    result = classify_card_runtime_support(card_def, _resolved_card("trigger", blockers=("unsupported_trigger",)))

    assert result.status == "executable"
    assert result.blockers == ()
    assert result.stale_blockers_ignored == ("unsupported_trigger",)
    assert "trigger_projection:projected" in result.evidence
    assert "bag_resolution" in result.runtime_paths_verified


def test_unsupported_effect_fails_with_exact_fresh_blocker():
    ability = SourceAbilityDef(
        id="unsupported-action",
        kind="action",
        effects=(
            SourceEffectDef(
                kind="create-replacement-effect",
                mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                execution_status=ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC,
            ),
        ),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC,
    )
    card_def = _card("unsupported", source_abilities=(ability,), source_execution_status=ExecutionStatus.UNSUPPORTED_ENGINE_MECHANIC)
    deck = _deck((_resolved_card("unsupported"),))

    card_result = classify_card_runtime_support(card_def)
    deck_result = classify_deck_runtime_support(deck, {"unsupported": card_def})

    assert card_result.status == "unsupported"
    assert card_result.blockers == ("unsupported_effect:create-replacement-effect",)
    assert deck_result.playability != "fully_executable"
    assert deck_result.blockers_by_copies == {"unsupported_effect:create-replacement-effect": 4}


def test_source_scry_destination_and_ordering_requirements_are_currently_executable():
    scry = SourceEffectDef(
        kind="scry",
        amount=2,
        raw={
            "type": "scry",
            "amount": 2,
            "destinations": [
                {"zone": "hand", "min": 1, "max": 1},
                {"zone": "deck-bottom", "remainder": True, "ordering": "player-choice"},
            ],
        },
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.UNSUPPORTED_CHOICE,
    )
    card_def = _card("scry", card_type="action", source_effects=(scry,), effects=())

    result = classify_card_runtime_support(
        card_def,
        _resolved_card("scry", blockers=("unsupported_resolution_requirement:destination", "unsupported_resolution_requirement:ordering")),
    )

    assert result.status == "executable"
    assert "unsupported_resolution_requirement:destination" not in result.blockers
    assert "unsupported_resolution_requirement:ordering" not in result.blockers
    assert "pending:scry_destinations" in result.runtime_paths_verified
    assert "automation:RESOLVE_EFFECT" in result.runtime_paths_verified


def test_supported_lorcanito_chosen_target_shape_no_longer_blocks():
    target = SourceTargetDef(
        kind="selector",
        selector="chosen",
        raw={
            "selector": "chosen",
            "count": 1,
            "owner": "any",
            "zones": ["play"],
            "cardTypes": ["character"],
            "filter": [{"type": "strength-comparison", "comparison": "greater-or-equal", "value": 5}],
        },
        execution_status=ExecutionStatus.UNSUPPORTED_TARGETING,
    )
    effect = SourceEffectDef(
        kind="banish",
        target=target,
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.MAPPED_NOT_EXECUTABLE,
    )
    card_def = _card("chosen", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def, _resolved_card("chosen", blockers=("unsupported_target:selector:chosen",)))

    assert result.status == "executable"
    assert "unsupported_target:selector:chosen" not in result.blockers
    assert result.stale_blockers_ignored == ("unsupported_target:selector:chosen",)
    assert "targeting:chosen_selector" in result.runtime_paths_verified


def test_supported_discard_chosen_cost_shape_no_longer_blocks():
    ability = SourceAbilityDef(
        id="discard",
        kind="activated",
        costs=(
            SourceCostDef(kind="discardCards", amount=1),
            SourceCostDef(kind="discardChosen", amount=1),
        ),
        effects=(SourceEffectDef(kind="draw", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED),),
    )
    card_def = _card("discard-cost", source_abilities=(ability,))

    result = classify_card_runtime_support(
        card_def,
        _resolved_card("discard-cost", blockers=("unsupported_cost:discardCards", "unsupported_cost:discardChosen")),
    )

    assert result.status == "executable"
    assert result.blockers == ()
    assert "unsupported_cost:discardCards" in result.stale_blockers_ignored
    assert "unsupported_cost:discardChosen" in result.stale_blockers_ignored


def test_discard_chosen_marker_without_discard_amount_stays_blocked():
    ability = SourceAbilityDef(
        id="bad-discard",
        kind="activated",
        costs=(SourceCostDef(kind="discardChosen", amount=1),),
        effects=(SourceEffectDef(kind="draw", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED),),
    )
    card_def = _card("bad-discard", source_abilities=(ability,))

    result = classify_card_runtime_support(card_def)

    assert result.status == "unsupported"
    assert result.blockers == ("unsupported_cost:discardChosen",)


def test_supported_selector_all_shape_no_longer_blocks():
    target = SourceTargetDef(
        kind="selector",
        selector="all",
        raw={
            "selector": "all",
            "count": "all",
            "owner": "opponent",
            "zones": ["play"],
            "cardTypes": ["character"],
            "filter": [{"type": "strength-comparison", "comparison": "less-or-equal", "value": 2}],
        },
        execution_status=ExecutionStatus.UNSUPPORTED_TARGETING,
    )
    effect = SourceEffectDef(kind="put-on-bottom", target=target, mapping_status=MappingStatus.STRUCTURALLY_MAPPED)
    card_def = _card("all-target", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def, _resolved_card("all-target", blockers=("unsupported_target:selector:all",)))

    assert result.status == "executable"
    assert "unsupported_target:selector:all" not in result.blockers
    assert "targeting:selector_all" in result.runtime_paths_verified


def test_selector_all_under_zone_stays_blocked():
    target = SourceTargetDef(
        kind="selector",
        selector="all",
        raw={"selector": "all", "count": "all", "zones": ["under"], "cardTypes": ["character"]},
        execution_status=ExecutionStatus.UNSUPPORTED_TARGETING,
    )
    effect = SourceEffectDef(kind="banish", target=target, mapping_status=MappingStatus.STRUCTURALLY_MAPPED)
    card_def = _card("bad-all", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def)

    assert result.status == "projected_but_requires_pending_input"
    assert result.blockers == ("unsupported_target:selector:all",)


def test_supported_sing_together_shape_no_longer_blocks():
    card_def = _card(
        "sing-together",
        card_type="action",
        strength=None,
        willpower=None,
        lore=None,
        keywords=("SING_TOGETHER",),
        keyword_defs=(KeywordDef(keyword="SING_TOGETHER", value=8),),
        source_effects=(SourceEffectDef(kind="draw", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED),),
    )

    result = classify_card_runtime_support(card_def, _resolved_card("sing-together", blockers=("keyword:SING_TOGETHER",)))

    assert result.status == "executable"
    assert "keyword:SING_TOGETHER" in result.stale_blockers_ignored
    assert "legal_actions:SING_TOGETHER" in result.runtime_paths_verified


def test_sing_together_without_numeric_keyword_value_stays_blocked():
    card_def = _card(
        "bad-sing-together",
        card_type="action",
        strength=None,
        willpower=None,
        lore=None,
        keywords=("SING_TOGETHER",),
        source_effects=(SourceEffectDef(kind="draw", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED),),
    )

    result = classify_card_runtime_support(card_def)

    assert result.status == "unsupported"
    assert result.blockers == ("unsupported_sing_together:shape",)


def test_unsupported_chosen_target_shape_stays_blocked():
    target = SourceTargetDef(
        kind="selector",
        selector="chosen",
        raw={
            "selector": "chosen",
            "zones": ["hand"],
            "cardTypes": ["character"],
        },
        execution_status=ExecutionStatus.UNSUPPORTED_TARGETING,
    )
    effect = SourceEffectDef(kind="banish", target=target, mapping_status=MappingStatus.STRUCTURALLY_MAPPED)
    card_def = _card("bad-chosen", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def)

    assert result.status == "projected_but_requires_pending_input"
    assert result.blockers == ("unsupported_target:selector:chosen",)


def test_supported_put_into_inkwell_shape_no_longer_blocks():
    target = SourceTargetDef(
        kind="alias",
        alias="CHOSEN_EXERTED_CHARACTER",
        execution_status=ExecutionStatus.UNSUPPORTED_TARGETING,
    )
    effect = SourceEffectDef(
        kind="put-into-inkwell",
        target=target,
        raw={"type": "put-into-inkwell", "target": "CHOSEN_EXERTED_CHARACTER", "source": "chosen-character", "facedown": True, "exerted": True},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
    )
    card_def = _card("inkwell", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def, _resolved_card("inkwell", blockers=("unsupported_effect:put-into-inkwell",)))

    assert result.status == "executable"
    assert "unsupported_effect:put-into-inkwell" not in result.blockers
    assert "unsupported_effect:put-into-inkwell" in result.stale_blockers_ignored


def test_unsupported_put_into_inkwell_shape_stays_blocked():
    effect = SourceEffectDef(
        kind="put-into-inkwell",
        raw={"type": "put-into-inkwell", "source": "deck"},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
    )
    card_def = _card("bad-inkwell", card_type="action", strength=None, willpower=None, lore=None, source_effects=(effect,))

    result = classify_card_runtime_support(card_def)

    assert result.status == "unsupported"
    assert result.blockers == ("unsupported_effect:put-into-inkwell",)


def test_parse_preserved_unknown_ability_reports_exact_source_shape():
    ability = SourceAbilityDef(
        id="unknown",
        kind="unknown",
        raw={
            "rawExpression": '{ type: "static", effect: { type: "grant-abilities-while-here" } }',
        },
    )
    card_def = _card("unknown", source_abilities=(ability,))

    result = classify_card_runtime_support(card_def)

    assert result.status == "unsupported"
    assert result.blockers == ("unsupported_ability_parse:grant-abilities-while-here",)


def test_actual_opponent_choice_requirement_is_supported_but_unrelated_choices_are_not_tagged():
    opponent_choice = SourceEffectDef(
        kind="choice",
        raw={"type": "choice", "chosenBy": "opponent", "options": [{"type": "draw", "amount": 1}]},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
    )
    normal_choice = SourceEffectDef(
        kind="choice",
        raw={"type": "choice", "optionLabels": ["Chosen opponent draws"], "options": [{"type": "draw", "amount": 1}]},
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
    )

    supported = classify_card_runtime_support(
        _card("opp-choice", card_type="action", strength=None, willpower=None, lore=None, source_effects=(opponent_choice,)),
        _resolved_card("opp-choice", blockers=("unsupported_resolution_requirement:opponent_choice",)),
    )
    normal = classify_card_runtime_support(
        _card("normal-choice", card_type="action", strength=None, willpower=None, lore=None, source_effects=(normal_choice,))
    )

    assert "unsupported_resolution_requirement:opponent_choice" not in supported.blockers
    assert "pending:opponent_choice" in supported.runtime_paths_verified
    assert "unsupported_resolution_requirement:opponent_choice" not in normal.blockers


def test_if_you_do_condition_is_supported_by_runtime_executability():
    effect = SourceEffectDef(
        kind="conditional",
        condition=SourceConditionDef(
            kind="if-you-do",
            raw={"type": "if-you-do"},
            mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
            execution_status=ExecutionStatus.EXECUTABLE,
        ),
        raw={
            "type": "conditional",
            "condition": {"type": "if-you-do"},
            "ifTrue": {"type": "draw", "amount": 1, "target": "CONTROLLER"},
        },
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.EXECUTABLE,
    )

    result = classify_card_runtime_support(
        _card(
            "if-you-do",
            card_type="action",
            strength=None,
            willpower=None,
            lore=None,
            source_effects=(effect,),
        )
    )

    assert "unsupported_condition:if-you-do" not in result.blockers


def test_phase1_static_runtime_executability_accepts_supported_static_shapes():
    static = SourceAbilityDef(
        id="static-ward",
        kind="static",
        effects=(
            SourceEffectDef(
                kind="gain-keyword",
                raw={
                    "type": "gain-keyword",
                    "keyword": "Ward",
                    "target": {
                        "selector": "all",
                        "owner": "you",
                        "zones": ["play"],
                        "cardTypes": ["character"],
                        "excludeSelf": True,
                    },
                },
                mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                execution_status=ExecutionStatus.EXECUTABLE,
            ),
        ),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.EXECUTABLE,
        raw={
            "id": "static-ward",
            "type": "static",
            "effect": {
                "type": "gain-keyword",
                "keyword": "Ward",
                "target": {
                    "selector": "all",
                    "owner": "you",
                    "zones": ["play"],
                    "cardTypes": ["character"],
                    "excludeSelf": True,
                },
            },
        },
    )

    result = classify_card_runtime_support(
        _card("static-ward", source_abilities=(static,))
    )

    assert result.status == "executable"
    assert not any(blocker.startswith("unsupported_static_effect") for blocker in result.blockers)


def test_suite_report_uses_fresh_blockers_and_keeps_stale_fields_separate():
    static = SourceStaticEffectDef(
        kind="cost-reduction",
        effect=SourceEffectDef(kind="cost-reduction", amount=1, mapping_status=MappingStatus.STRUCTURALLY_MAPPED),
    )
    supported = _card("supported", source_static_abilities=(static,))
    unsupported = _card(
        "unsupported",
        source_abilities=(
            SourceAbilityDef(
                id="bad",
                kind="action",
                effects=(SourceEffectDef(kind="create-replacement-effect", mapping_status=MappingStatus.STRUCTURALLY_MAPPED),),
            ),
        ),
    )
    deck = _deck((_resolved_card("supported", blockers=("unsupported_static_effect",)), _resolved_card("unsupported")))

    report = build_suite_mapping_report([deck], {"supported": supported, "unsupported": unsupported})

    assert report["fully_executable_decks"] == 0
    assert report["top_blockers_by_copies"][0]["blocker"] == "unsupported_effect:create-replacement-effect"
    summary = report["decks"][0]
    assert summary["stored_resolved_deck_blockers"][0]["blocker"] == "unsupported_static_effect"
    assert summary["stale_blockers_ignored"][0]["blocker"] == "unsupported_static_effect"
    assert summary["fresh_runtime_blockers"][0]["blocker"] == "unsupported_effect:create-replacement-effect"

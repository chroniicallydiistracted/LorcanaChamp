from lorcana_bot.card_logic import ExecutionStatus, MappingStatus, SourceAbilityDef, SourceEffectDef, SourceStaticEffectDef, SourceTriggerDef
from lorcana_bot.cards import CardDef
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

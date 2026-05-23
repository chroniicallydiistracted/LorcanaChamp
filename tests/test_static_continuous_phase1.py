from lorcana_bot.actions import Action
from lorcana_bot.card_logic import ExecutionStatus, MappingStatus, SourceAbilityDef, SourceEffectDef
from lorcana_bot.cards import CardDatabase, CardDef
from lorcana_bot.constants import ACTION_CHALLENGE, ACTION_INK_CARD, ACTION_QUEST, KEYWORD_EVASIVE, KEYWORD_WARD, ZONE_HAND, ZONE_PLAY
from lorcana_bot.engine import GameEngine
from lorcana_bot.state import CardInstance, GameState, PlayerState
from lorcana_bot.static_effects import static_additional_inkwell_allowance


def _static_ability(effect: SourceEffectDef, *, condition=None, source_zones=("play",), name="STATIC"):
    return SourceAbilityDef(
        id=name.lower().replace(" ", "-"),
        kind="static",
        name=name,
        effects=(effect,),
        condition=condition,
        source_zones=tuple(source_zones),
        mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
        execution_status=ExecutionStatus.EXECUTABLE,
        raw={
            "type": "static",
            "name": name,
            "sourceZones": list(source_zones),
            "effect": effect.raw,
        },
    )


def _state_with_play(engine, entries):
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    for instance_id, owner, name in entries:
        card = engine.db.get(name)
        state.cards[instance_id] = CardInstance(
            instance_id=instance_id,
            card_id=card.id,
            owner=owner,
            controller=owner,
            zone=ZONE_PLAY,
        )
        state.players[owner].play.append(instance_id)
    return state


def test_static_gain_keyword_materializes_for_your_other_characters_only():
    ward_source = CardDef(
        "aurora",
        "Aurora",
        "sapphire",
        5,
        True,
        "character",
        3,
        5,
        2,
        source_abilities=(
            _static_ability(
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
                name="PROTECTIVE EMBRACE",
            ),
        ),
    )
    ally = CardDef("ally", "Ally", "amber", 2, True, "character", 1, 2, 1)
    enemy = CardDef("enemy", "Enemy", "ruby", 2, True, "character", 1, 2, 1)
    engine = GameEngine(CardDatabase([ward_source, ally, enemy]))
    state = _state_with_play(engine, [(1, 0, "Aurora"), (2, 0, "Ally"), (3, 1, "Enemy")])

    assert not engine.has_keyword(state, 1, KEYWORD_WARD)
    assert engine.has_keyword(state, 2, KEYWORD_WARD)
    assert not engine.has_keyword(state, 3, KEYWORD_WARD)


def test_static_modify_stat_uses_dynamic_classification_character_count():
    hades = CardDef(
        "hades",
        "Hades",
        "amber",
        8,
        True,
        "character",
        3,
        6,
        1,
        subtypes=("Villain",),
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="modify-stat",
                    raw={
                        "type": "modify-stat",
                        "stat": "lore",
                        "target": "SELF",
                        "modifier": {
                            "type": "classification-character-count",
                            "classification": "Villain",
                            "controller": "you",
                            "excludeSelf": True,
                        },
                    },
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="SINISTER PLOT",
            ),
        ),
    )
    villain = CardDef("villain", "Villain Ally", "amber", 2, True, "character", 1, 2, 1, subtypes=("Villain",))
    hero = CardDef("hero", "Hero Ally", "amber", 2, True, "character", 1, 2, 1, subtypes=("Hero",))
    engine = GameEngine(CardDatabase([hades, villain, hero]))
    state = _state_with_play(engine, [(1, 0, "Hades"), (2, 0, "Villain Ally"), (3, 0, "Hero Ally")])

    assert engine.effective_lore(state, 1) == 2


def test_static_condition_has_another_character_controls_self_keyword():
    pascal = CardDef(
        "pascal",
        "Pascal",
        "emerald",
        1,
        True,
        "character",
        1,
        1,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="gain-keyword",
                    raw={"type": "gain-keyword", "keyword": "Evasive", "target": "SELF"},
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                condition={"type": "has-another-character"},
                name="CAMOUFLAGE",
            ),
        ),
    )
    ally = CardDef("ally", "Ally", "amber", 2, True, "character", 1, 2, 1)
    engine = GameEngine(CardDatabase([pascal, ally]))
    state = _state_with_play(engine, [(1, 0, "Pascal")])
    assert not engine.has_keyword(state, 1, KEYWORD_EVASIVE)

    state.cards[2] = CardInstance(2, "ally", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(2)
    assert engine.has_keyword(state, 1, KEYWORD_EVASIVE)


def test_static_cant_be_challenged_with_challenger_cost_filter_blocks_only_matching_attackers():
    defender = CardDef(
        "hook",
        "Captain Hook",
        "steel",
        5,
        True,
        "character",
        3,
        4,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="restriction",
                    raw={
                        "type": "restriction",
                        "restriction": "cant-be-challenged",
                        "target": "SELF",
                        "challengerFilter": {"type": "cost-comparison", "operator": "lte", "value": 3},
                    },
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="STOLEN DUST",
            ),
        ),
    )
    cheap = CardDef("cheap", "Cheap", "ruby", 3, True, "character", 2, 2, 1)
    expensive = CardDef("expensive", "Expensive", "ruby", 4, True, "character", 2, 2, 1)
    engine = GameEngine(CardDatabase([defender, cheap, expensive]))
    state = _state_with_play(engine, [(1, 0, "Captain Hook"), (2, 1, "Cheap"), (3, 1, "Expensive")])
    state.active_player = 1
    state.cards[1].exerted = True

    assert 1 not in engine.challenge_targets(state, 2)
    assert 1 in engine.challenge_targets(state, 3)


def test_static_additional_inkwell_allows_exactly_one_extra_ink_per_turn():
    belle = CardDef(
        "belle",
        "Belle",
        "sapphire",
        4,
        True,
        "character",
        2,
        4,
        1,
        source_abilities=(
            _static_ability(
                SourceEffectDef(
                    kind="additional-inkwell",
                    raw={"type": "additional-inkwell", "amount": 1},
                    mapping_status=MappingStatus.STRUCTURALLY_MAPPED,
                    execution_status=ExecutionStatus.EXECUTABLE,
                ),
                name="READ A BOOK",
            ),
        ),
    )
    inkable = CardDef("inkable", "Inkable", "amber", 1, True, "character", 1, 1, 1)
    engine = GameEngine(CardDatabase([belle, inkable]))
    state = GameState(players=[PlayerState(), PlayerState()], cards={})
    state.active_player = 0
    state.cards[1] = CardInstance(1, "belle", owner=0, controller=0, zone=ZONE_PLAY)
    state.players[0].play.append(1)
    for cid in (2, 3, 4):
        state.cards[cid] = CardInstance(cid, "inkable", owner=0, controller=0, zone=ZONE_HAND)
        state.players[0].hand.append(cid)

    assert static_additional_inkwell_allowance(state, 0, engine) == 1
    state = engine.apply_action(state, Action(ACTION_INK_CARD, actor=0, card=2))
    state = engine.apply_action(state, Action(ACTION_INK_CARD, actor=0, card=3))

    remaining_ink_actions = [action for action in engine.legal_actions(state, 0) if action.kind == ACTION_INK_CARD]
    assert remaining_ink_actions == []
from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import InstanceId, PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.core.zones import CardMeta, move_card_to_zone, patch_card_meta, scoped_zone
from lorcana_engine_v2.moves.play import PLAY_CARD
from lorcana_engine_v2.rules.move_registry_cache import (
    clear_move_registry_cache,
    get_move_registry_cache_stats,
    get_or_build_move_registry,
)

from .helpers import resources_for
from .test_play_card_lorcanito_v2 import _main_state


def _play_command(card_id, **args):
    return CommandEnvelope(
        commandID=f"cmd-play-dependency-{card_id}",
        move=PLAY_CARD,
        input=MoveInput(args={"cardId": card_id, **args}),
    )


def test_play_card_rejects_pending_choice_priority_holder_who_is_not_turn_owner():
    resources = resources_for({"p0_card": "XGm", "p1_card": "XGm", "ink": "Y1z"})
    state = _main_state(resources, hand=("p0_card",), inkwell=("ink",))
    zones = move_card_to_zone(state.ctx.zones, card_id="p1_card", destination_zone_key=scoped_zone("hand", "p1"))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            zones=zones,
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(_play_command("p1_card"), "p1", actor_role="player")

    assert result.success is False
    assert result.errorCode == "NOT_CURRENT_PLAYER"


def test_play_card_uses_turn_owner_when_priority_is_temporarily_assigned():
    resources = resources_for({"card": "XGm", "ink1": "Y1z", "ink2": "Y1z", "ink3": "Y1z"})
    state = _main_state(resources, hand=("card",), inkwell=("ink1", "ink2", "ink3"))
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            priority=state.ctx.priority.with_updates(holder=PlayerId("p1"), windowOpen=True),
        ),
    )
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(_play_command("card"), "p0", actor_role="player")

    assert result.success is True
    assert InstanceId("card") in result.state.ctx.zones.private.zoneCards[scoped_zone("play", "p0")]


def test_move_registry_cache_reuses_same_state_and_rebuilds_on_static_version_change():
    resources = resources_for({"tiana": "ivr", "action": "X1Y"}, owners={"p0": ("action",), "p1": ("tiana",)})
    state = _main_state(resources, hand=("action",))
    zones = move_card_to_zone(state.ctx.zones, card_id="tiana", destination_zone_key=scoped_zone("play", "p1"))
    zones = patch_card_meta(zones, "tiana", CardMeta(state="exerted", isDrying=False, damage=0))
    state = MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)
    context = runtime.context()
    context.query.actorPlayerId = PlayerId("p0")
    read_context = type("RegistryContext", (), {"state": state, "cards": type("Cards", (), {"_query": context.query})()})()

    clear_move_registry_cache()
    first = get_or_build_move_registry(read_context)
    second = get_or_build_move_registry(read_context)
    changed_state = MatchState(G=state.G.with_updates(staticEffectsVersion=state.G.staticEffectsVersion + 1), ctx=state.ctx)
    changed_context = type("RegistryContext", (), {"state": changed_state, "cards": type("Cards", (), {"_query": context.query})()})()
    third = get_or_build_move_registry(changed_context)

    stats = get_move_registry_cache_stats()
    assert first is second
    assert third is not first
    assert stats.hits == 1
    assert stats.misses == 2


def test_action_target_invalid_is_rejected_before_ink_is_paid():
    resources = resources_for(
        {"freeze": "D1e", "target": "Y1z", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("freeze", "target", "i1", "i2"), "p1": ()},
    )
    state = _main_state(resources, hand=("freeze",), play=("target",), inkwell=("i1", "i2"))
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(_play_command("freeze", targets=["target"]), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "INVALID_ACTION_TARGET"
    assert runtime.get_state().ctx.zones.private.cardMeta[InstanceId("i1")].state == "ready"
    assert runtime.get_state().ctx.zones.private.cardMeta[InstanceId("i2")].state == "ready"


def test_action_target_duplicate_is_rejected_for_single_chosen_descriptor():
    resources = resources_for(
        {"freeze": "D1e", "target": "Y1z", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("freeze", "i1", "i2"), "p1": ("target",)},
    )
    state = _main_state(resources, hand=("freeze",), inkwell=("i1", "i2"))
    zones = move_card_to_zone(state.ctx.zones, card_id="target", destination_zone_key=scoped_zone("play", "p1"))
    zones = patch_card_meta(zones, "target", CardMeta(state="ready", isDrying=False, damage=0))
    runtime = MatchRuntime(resources)
    runtime.load_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))

    result = runtime.process_command(_play_command("freeze", targets=["target", "target"]), "p0", actor_role="player")

    assert result.success is False
    assert result.errorCode == "DUPLICATE_TARGETS"


def test_real_be_chosen_trigger_enters_bag_for_opponent_action_target():
    resources = resources_for(
        {"freeze": "D1e", "archimedes": "8Al", "i1": "Y1z", "i2": "Y1z"},
        owners={"p0": ("freeze", "i1", "i2"), "p1": ("archimedes",)},
    )
    state = _main_state(resources, hand=("freeze",), inkwell=("i1", "i2"))
    zones = move_card_to_zone(state.ctx.zones, card_id="archimedes", destination_zone_key=scoped_zone("play", "p1"))
    zones = patch_card_meta(zones, "archimedes", CardMeta(state="ready", isDrying=False, damage=0))
    runtime = MatchRuntime(resources)
    runtime.load_state(MatchState(G=state.G, ctx=state.ctx.with_updates(zones=zones)))

    result = runtime.process_command(_play_command("freeze", targets=["archimedes"]), "p0", actor_role="player")

    assert result.success is True
    assert len(result.state.G.triggeredAbilities.bag.items) == 1
    bag_item = result.state.G.triggeredAbilities.bag.items[0]
    assert bag_item.sourceId == InstanceId("archimedes")
    assert bag_item.controllerId == PlayerId("p1")
    assert bag_item.abilityName == "MORE TO LEARN"
    assert bag_item.trigger["event"] == "be-chosen"
    assert bag_item.resolutionInput.eventSnapshot["subjectCardId"] == InstanceId("archimedes")
    assert bag_item.resolutionInput.eventSnapshot["triggerSourceCardId"] == InstanceId("freeze")

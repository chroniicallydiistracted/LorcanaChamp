from lorcana_engine_v2.core.commands import CommandEnvelope, MoveInput
from lorcana_engine_v2.core.ids import PlayerId
from lorcana_engine_v2.core.runtime import MatchRuntime
from lorcana_engine_v2.core.state import MatchState
from lorcana_engine_v2.moves.resolve_bag import RESOLVE_BAG

from .helpers import resources_for
from .test_resolve_bag_lorcanito_v2 import _state_with_aladdin_bag


def test_resolve_bag_command_executes_through_match_runtime_process_command():
    resources = resources_for({"aladdin": "ZTM"})
    state = _state_with_aladdin_bag(resources)
    state = MatchState(
        G=state.G,
        ctx=state.ctx.with_updates(
            status=state.ctx.status.with_updates(
                gameSegment="mainGame",
                phase="main",
                turnOwnerId=PlayerId("p0"),
            ),
            priority=state.ctx.priority.with_updates(holder=PlayerId("p0"), windowOpen=True),
        ),
    )
    bag_item = state.G.triggeredAbilities.bag.items[0]
    runtime = MatchRuntime(resources)
    runtime.load_state(state)

    result = runtime.process_command(
        CommandEnvelope(
            commandID="resolve-bag-command",
            move=RESOLVE_BAG,
            input=MoveInput(args={"bagId": bag_item.id, "params": {}}),
        ),
        "p0",
        actor_role="player",
    )

    assert result.success is True
    assert result.state.G.lore[PlayerId("p1")] == 2
    assert result.state.G.triggeredAbilities.bag.items == ()

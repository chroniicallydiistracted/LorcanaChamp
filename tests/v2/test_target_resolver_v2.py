from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.state import CardInstance, MatchState, PlayerState
from lorcana_engine_v2.rules.target_resolver import TargetQueryContext


def test_your_hero_characters_alias_resolves_real_hero_card():
    catalog = CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))
    ctx = build_rules_context(catalog)
    state = MatchState(
        players=(PlayerState(PlayerId(0), play=(InstanceId(1), InstanceId(2))), PlayerState(PlayerId(1))),
        cards={
            InstanceId(1): CardInstance(InstanceId(1), CardId("HyV"), PlayerId(0), PlayerId(0), "play"),
            InstanceId(2): CardInstance(InstanceId(2), CardId("Y1z"), PlayerId(0), PlayerId(0), "play"),
        },
    )
    result = ctx.targets.resolve(state, ctx, "YOUR_HERO_CHARACTERS", TargetQueryContext(actor=0, source_id=1))
    assert result == (2,)

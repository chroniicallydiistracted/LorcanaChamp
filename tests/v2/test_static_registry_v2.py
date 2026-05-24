from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.state import CardInstance, MatchState, PlayerState


def test_static_registry_materializes_real_chi_fu_static():
    catalog = CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))
    ctx = build_rules_context(catalog)
    state = MatchState(
        players=(PlayerState(PlayerId(0), play=(InstanceId(1),)), PlayerState(PlayerId(1))),
        cards={InstanceId(1): CardInstance(InstanceId(1), CardId("XGm"), PlayerId(0), PlayerId(0), "play")},
    )
    effects = ctx.static.materialize(state, ctx)
    assert len(effects) == 1
    assert effects[0].kind == "modify-stat"
    assert effects[0].target_ids == (1,)
    assert effects[0].payload == {"stat": "lore", "amount": 2}

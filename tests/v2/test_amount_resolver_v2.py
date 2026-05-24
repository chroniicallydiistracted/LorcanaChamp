from pathlib import Path

from lorcana_engine_v2.cards import CardCatalog
from lorcana_engine_v2.core.context import build_rules_context
from lorcana_engine_v2.core.ids import CardId, InstanceId, PlayerId
from lorcana_engine_v2.core.state import CardInstance, MatchState, PlayerState
from lorcana_engine_v2.rules.amount_resolver import AmountContext


def test_items_in_play_amount_provider_counts_real_items():
    catalog = CardCatalog.from_lorcanito_normalized_json(Path("data/lorcanito_runtime_extracted/cards.normalized.json"))
    ctx = build_rules_context(catalog)
    state = MatchState(
        players=(PlayerState(PlayerId(0), play=(InstanceId(1), InstanceId(2))), PlayerState(PlayerId(1))),
        cards={
            InstanceId(1): CardInstance(InstanceId(1), CardId("Z2D"), PlayerId(0), PlayerId(0), "play"),
            InstanceId(2): CardInstance(InstanceId(2), CardId("Bf0"), PlayerId(0), PlayerId(0), "play"),
        },
    )
    assert catalog.get("Bf0").card_type == "item"
    assert ctx.amounts.resolve(state, ctx, {"type": "items-in-play", "controller": "you"}, AmountContext(actor=0, source_id=1)) == 1

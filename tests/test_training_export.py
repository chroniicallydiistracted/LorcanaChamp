import json

from lorcana_bot.automation.ml.training_export import trace_to_training_row
from lorcana_bot.automation.candidates import (
    AutomatedActionCandidate,
    AutomatedActionCandidateSummary,
    AutomatedActionFamily,
)
from lorcana_bot.automation.decision_trace import AutomatedDecisionTrace, redact_private_trace_payload
from lorcana_bot.automation.planner import take_automated_action
from lorcana_bot.automation.strategy_registry import get_strategy


def test_training_row_schema(engine, state):
    _, trace = take_automated_action(state, engine, get_strategy("deck-aware-lore-race"))
    row = trace_to_training_row(trace)
    assert row["schema_version"] == 1
    assert row["selected_stable_key"] in {candidate["stable_key"] for candidate in row["candidates"]}
    assert json.dumps(row)


def test_fair_trace_redacts_private_search_and_scry_candidate_ids():
    payload = {
        "stable_key": "raw-private-key",
        "selected_card_id": 101,
        "top_cards": [201, 202],
        "bottom_cards": [203],
        "candidate": {
            "stable_key": "nested-private-key",
            "card_candidate_ids": (101, 102),
            "target_candidate_ids": (301,),
            "destinations": {"top": (201,), "bottom": (202, 203)},
        },
    }

    redacted = redact_private_trace_payload(payload, "fair")

    assert redacted["selected_card_id"] == "<private>"
    assert redacted["top_cards"] == ["<private>", "<private>"]
    assert redacted["bottom_cards"] == ["<private>"]
    assert redacted["candidate"]["card_candidate_ids"] == ["<private>", "<private>"]
    assert redacted["candidate"]["target_candidate_ids"] == ["<private>"]
    assert redacted["stable_key"].startswith("fair:")
    assert redacted["candidate"]["stable_key"] == redacted["stable_key"]
    assert "101" not in json.dumps(redacted)
    assert "201" not in json.dumps(redacted)


def test_training_export_uses_redacted_stable_keys_for_private_candidates():
    candidate = AutomatedActionCandidate(
        family=AutomatedActionFamily.RESOLVE_EFFECT,
        actor=0,
        stable_key="raw-private-key",
        pending_effect_id="pe_1",
        metadata={"card_candidate_ids": (101, 102)},
    )
    summary = AutomatedActionCandidateSummary(
        candidate=candidate,
        family=str(AutomatedActionFamily.RESOLVE_EFFECT),
        stable_key="raw-private-key",
        score=1.0,
        family_order=2.0,
        contributors=(),
        information_policy="fair",
    )
    raw = {
        "candidate": {
            "family": str(AutomatedActionFamily.RESOLVE_EFFECT),
            "actor": 0,
            "stable_key": "raw-private-key",
            "pending_effect_id": "pe_1",
            "metadata": {"card_candidate_ids": (101, 102)},
        },
        "family": str(AutomatedActionFamily.RESOLVE_EFFECT),
        "stable_key": "raw-private-key",
        "score": 1.0,
        "rank": 0,
        "family_order": 2.0,
        "contributors": [],
        "information_policy": "fair",
    }
    redacted = redact_private_trace_payload(raw, "fair")
    trace = AutomatedDecisionTrace(
        schema_version=1,
        trace_id="trace",
        actor=0,
        actor_resolution={},
        strategy_name="test",
        information_policy="fair",
        turn_number=1,
        phase="MAIN",
        state_fingerprint="fp",
        board_snapshot={},
        candidate_count=1,
        ordered_candidates=[redacted],
        validation_rejections=[],
        unsupported_skips=[],
        execution_attempts=[],
        selected_candidate=redacted,
        selected_action=None,
        fallback_taken=None,
        result="executed",
    )

    row = trace_to_training_row(trace)

    assert row["selected_stable_key"] == row["candidates"][0]["stable_key"]
    assert row["selected_stable_key"].startswith("fair:")
    assert "101" not in json.dumps(row)
    assert summary.information_policy == "fair"

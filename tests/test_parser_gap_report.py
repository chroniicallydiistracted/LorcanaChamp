from scripts.extract_lorcanito_source_cards import _parser_gap, _parser_gap_report


def test_parser_gap_report_has_schema_and_summaries():
    report = _parser_gap_report(
        [
            _parser_gap(
                source_file="cards/a.ts",
                card_id="a",
                card_name="A",
                gap_type="spread_unresolved",
                snippet="...base",
                impact="lost_ability",
                recommended_fix="Resolve spread.",
                confidence="high",
            ),
            _parser_gap(
                source_file="cards/b.ts",
                card_id="b",
                card_name="B",
                gap_type="helper_unresolved",
                snippet="mysteryHelper",
                impact="lost_ability",
                recommended_fix="Map helper.",
                confidence="medium",
            ),
        ]
    )

    assert report["schema_version"] == 1
    assert report["summary"]["by_gap_type"]["spread_unresolved"] == 1
    assert report["summary"]["by_gap_type"]["helper_unresolved"] == 1
    assert report["summary"]["source_files_with_gaps"] == 2

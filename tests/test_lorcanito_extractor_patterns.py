from scripts.audit_unknown_lorcanito_abilities import classify_unknown_ability
from scripts.extract_lorcanito_source_cards import _extract_ability_snippets, _fallback_card_fields, _normalize_abilities, _parse_fallback_ts_value, _parse_object


def test_keyword_helper_calls_normalize_to_keyword_records():
    raw = _parse_object('{ abilities: [singer(5), resist(2), challenger(3), shift(3), shift("Ariel", 3), singTogether(10), boost(1)] }')
    abilities = _normalize_abilities(raw["abilities"])

    assert [ability["type"] for ability in abilities] == ["keyword"] * 7
    assert abilities[0]["helper"] == "singer"
    assert abilities[0]["value"] == 5
    assert abilities[1]["keyword"] == "Resist"
    assert abilities[2]["keyword"] == "Challenger"
    assert abilities[3]["cost"] == {"ink": 3}
    assert abilities[4]["target_name"] == "Ariel"
    assert abilities[5]["keyword"] == "Sing Together"
    assert abilities[6]["keyword"] == "Boost"


def test_bare_keyword_identifier_normalizes_to_keyword_record():
    abilities = _normalize_abilities(["rush", "evasive"])

    assert abilities[0]["type"] == "keyword"
    assert abilities[0]["helper"] == "rush"
    assert abilities[1]["keyword"] == "Evasive"


def test_unresolved_helper_preserves_raw_expression():
    abilities = _normalize_abilities(["mysteryHelper"])

    assert abilities[0]["type"] == "unknown"
    assert abilities[0]["helper"] == "mysteryHelper"
    assert abilities[0]["rawExpression"] == "mysteryHelper"


def test_unknown_shape_classification_rules():
    assert classify_unknown_ability({"trigger": {}, "effect": {}})[0] == "triggered"
    assert classify_unknown_ability({"cost": {}, "effect": {}})[0] == "activated"
    assert classify_unknown_ability({"replaces": "draw", "replacement": {}})[0] == "replacement"


def test_fallback_preserves_quoted_string_with_commas():
    snippet = '''
    {
      id: "Rc1",
      name: "Malicious, Mean, and Scary",
      text: "Put 1 damage counter on each opposing character.",
      cardType: "action",
    }
    '''
    raw = _fallback_card_fields(snippet)
    assert raw["name"] == "Malicious, Mean, and Scary"
    assert raw["text"] == "Put 1 damage counter on each opposing character."
    assert raw["cardType"] == "action"


def test_fallback_abilities_preserve_nested_action_effect():
    snippet = '''
    {
      abilities: [
        {
          effect: {
            amount: 1,
            target: "ALL_OPPOSING_CHARACTERS",
            type: "put-damage",
          },
          type: "action",
        },
      ],
    }
    '''
    abilities = _extract_ability_snippets(snippet)
    assert len(abilities) == 1
    assert abilities[0]["type"] == "action"
    assert abilities[0]["effect"]["type"] == "put-damage"
    assert abilities[0]["effect"]["amount"] == 1
    assert abilities[0]["effect"]["target"] == "ALL_OPPOSING_CHARACTERS"


def test_parse_object_or_fallback_for_malicious_mean_and_scary_shape():
    snippet = '''{
      id: "Rc1",
      name: "Malicious, Mean, and Scary",
      text: "Put 1 damage counter on each opposing character.",
      cardType: "action",
      actionSubtype: "song",
      abilities: [
        {
          effect: {
            amount: 1,
            target: "ALL_OPPOSING_CHARACTERS",
            type: "put-damage",
          },
          type: "action",
        },
      ],
    }'''
    raw = _fallback_card_fields(snippet)
    raw["abilities"] = _normalize_abilities(raw.get("abilities", []))
    assert raw["name"] == "Malicious, Mean, and Scary"
    assert raw["actionSubtype"] == "song"
    assert len(raw["abilities"]) == 1
    assert raw["abilities"][0]["type"] == "action"
    assert raw["abilities"][0]["effect"]["type"] == "put-damage"


def test_parse_fallback_ts_value_handles_strings_arrays():
    assert _parse_fallback_ts_value('"Malicious, Mean, and Scary"') == "Malicious, Mean, and Scary"
    assert _parse_fallback_ts_value('"simple"') == "simple"
    assert _parse_fallback_ts_value("3") == 3
    assert _parse_fallback_ts_value("true") is True
    assert _parse_fallback_ts_value("false") is False
    assert _parse_fallback_ts_value("null") is None
    assert _parse_fallback_ts_value('["amber", "ruby"]') == ["amber", "ruby"]
    assert _parse_fallback_ts_value('[1, 2, 3]') == [1, 2, 3]

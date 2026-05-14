from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

KNOWN_KEYWORD_HELPERS = {
    "rush",
    "ward",
    "evasive",
    "bodyguard",
    "support",
    "reckless",
    "vanish",
    "alert",
    "resist",
    "challenger",
    "singer",
    "singTogether",
    "shift",
    "boost",
}
TRIGGER_HELPERS = {"wheneverQuests", "whenPlayed", "whenBanishes", "whenChallenged"}
STATIC_HELPERS = {"duringYourTurn", "whileHere", "gainAbility"}
METADATA_KEYS = {"id", "name", "version", "cardType", "inkType", "cost", "inkable", "set", "cardNumber", "rarity"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit unknown Lorcanito source ability records.")
    parser.add_argument("--source-json", type=Path, default=Path("data/lorcanito_extracted/cards.normalized.json"))
    parser.add_argument("--source-root", type=Path, default=Path("/home/andre/LorcanaChamp/lorcanito-full-src-code"))
    parser.add_argument("--out", type=Path, default=Path("data/lorcanito_extracted/unknown_ability_audit.json"))
    parser.add_argument("--patterns-out", type=Path, default=Path("data/lorcanito_extracted/unknown_ability_patterns.json"))
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_unknown_ability_audit(args.source_json, args.source_root)
    patterns = build_unknown_ability_patterns(audit)
    _write_json(args.out, audit)
    _write_json(args.patterns_out, patterns)
    if args.print_summary:
        print(f"unknown ability records: {audit['summary']['total_unknowns']}")
        for pattern, count in sorted(audit["summary"]["by_pattern_fingerprint"].items(), key=lambda item: (-item[1], item[0]))[:10]:
            print(f"{count:4d} {pattern}")


def build_unknown_ability_audit(source_json: str | Path, source_root: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(source_json).read_text(encoding="utf-8"))
    cards = payload.get("cards", payload if isinstance(payload, list) else [])
    unknowns: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        for index, ability in enumerate(card.get("abilities", [])):
            if not _is_unknown_ability(ability):
                continue
            raw = dict(ability) if isinstance(ability, dict) else {"value": ability}
            source_file = str(card.get("sourceFile") or raw.get("sourceFile") or "")
            raw_snippet = _raw_snippet(raw, source_file, source_root)
            helper_calls = _detected_helper_calls(raw, raw_snippet)
            keys = sorted(str(key) for key in raw)
            literals = _detected_string_literals(raw)
            category, action, confidence, notes = classify_unknown_ability(raw, raw_snippet)
            fingerprint = pattern_fingerprint(raw, raw_snippet, str(card.get("cardType") or ""), helper_calls)
            unknowns.append(
                {
                    "card_id": str(card.get("id") or card.get("canonicalId") or ""),
                    "card_name": str(card.get("name") or ""),
                    "version": str(card.get("version") or ""),
                    "card_type": str(card.get("cardType") or ""),
                    "set": str(card.get("set") or ""),
                    "source_file": source_file,
                    "ability_index": index,
                    "raw": raw,
                    "raw_snippet": raw_snippet,
                    "detected_helper_calls": helper_calls,
                    "detected_object_keys": keys,
                    "detected_string_literals": literals,
                    "current_reason": str(raw.get("_unsupported_reason") or raw.get("type") or "unknown"),
                    "pattern_fingerprint": fingerprint,
                    "inferred_category": category,
                    "confidence": confidence,
                    "recommended_action": action,
                    "notes": notes,
                }
            )
    unknowns.sort(key=lambda item: (item["card_id"], item["source_file"], item["ability_index"]))
    return {"schema_version": SCHEMA_VERSION, "unknowns": unknowns, "summary": _summary(unknowns)}


def build_unknown_ability_patterns(audit: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in audit.get("unknowns", []):
        grouped[str(item.get("pattern_fingerprint") or "unknown")].append(item)
    patterns: list[dict[str, Any]] = []
    for fingerprint in sorted(grouped):
        items = grouped[fingerprint]
        helper_calls = sorted({helper for item in items for helper in item.get("detected_helper_calls", [])})
        keys = sorted({key for item in items for key in item.get("detected_object_keys", [])})
        patterns.append(
            {
                "pattern_fingerprint": fingerprint,
                "count": len(items),
                "example_cards": sorted({item.get("card_id") or item.get("card_name") for item in items if item.get("card_id") or item.get("card_name")})[:10],
                "example_source_files": sorted({item.get("source_file") for item in items if item.get("source_file")})[:10],
                "detected_helper_calls": helper_calls,
                "detected_keys": keys,
                "inferred_category": _majority(items, "inferred_category"),
                "recommended_action": _majority(items, "recommended_action"),
                "confidence": _majority(items, "confidence"),
                "notes": _majority(items, "notes"),
            }
        )
    patterns.sort(key=lambda item: (-item["count"], item["pattern_fingerprint"]))
    return {"schema_version": SCHEMA_VERSION, "patterns": patterns}


def classify_unknown_ability(raw: dict[str, Any], raw_snippet: str = "") -> tuple[str, str, str, str]:
    helper = str(raw.get("helper") or raw.get("rawReference") or "")
    expression = str(raw.get("rawExpression") or raw.get("rawReference") or raw_snippet or "")
    keys = set(raw)
    if helper in KNOWN_KEYWORD_HELPERS or re.match(r"^(singer|resist|challenger|shift|singTogether|boost)\s*\(", expression):
        return "keyword", "mapper_fix", "high", "known Lorcanito keyword helper"
    if helper in TRIGGER_HELPERS or re.match(r"^(wheneverQuests|whenPlayed|whenBanishes|whenChallenged)\s*\(", expression):
        return "triggered", "mapper_fix", "high", "known Lorcanito triggered helper"
    if helper in STATIC_HELPERS or {"staticEffect", "duration"} & keys:
        return "static", "mapper_fix", "medium", "static-like source object"
    if {"trigger", "effect"} <= keys:
        return "triggered", "mapper_fix", "medium", "object has trigger/effect shape without a recognized type"
    if ({"cost", "effect"} <= keys) or ({"costs", "effect"} <= keys):
        return "activated", "mapper_fix", "medium", "object has cost/effect shape without a recognized type"
    if {"replaces", "replacement"} & keys:
        return "replacement", "mapper_fix", "high", "replacement-like source object"
    if keys and keys <= METADATA_KEYS:
        return "metadata", "ignore_metadata", "high", "card metadata was captured as an ability"
    if "..." in raw_snippet or str(raw.get("rawReference") or "").startswith("..."):
        return "spread_unresolved", "scanner_fix", "high", "unresolved object spread"
    if helper:
        return "helper_unresolved", "scanner_fix", "medium", "helper reference is preserved but not structurally mapped"
    if raw.get("_parseWarning"):
        return "parser_gap", "scanner_fix", "medium", "raw object required fallback parsing"
    return "unknown", "manual_review", "low", "rare or malformed source shape"


def pattern_fingerprint(raw: dict[str, Any], raw_snippet: str = "", card_type: str = "", helper_calls: list[str] | None = None) -> str:
    helper_calls = helper_calls or _detected_helper_calls(raw, raw_snippet)
    if helper_calls:
        return "helper:" + "+".join(sorted(helper_calls))
    keys = sorted(key for key in raw if not key.startswith("_source"))
    if {"trigger", "effect"} <= set(keys) and "type" not in keys:
        return "trigger_object_without_type"
    if ({"cost", "effect"} <= set(keys) or {"costs", "effect"} <= set(keys)) and "type" not in keys:
        return "activated_cost_object_without_type"
    if {"replaces", "replacement"} & set(keys):
        return "replacement_object"
    if keys and set(keys) <= METADATA_KEYS:
        return "non_ability_metadata_misclassified"
    if "..." in raw_snippet:
        return "spread_only_reprint"
    if keys:
        suffix = ",type_missing" if "type" not in keys else ""
        return f"object_keys:{','.join(keys)}{suffix}:card_type:{card_type or 'unknown'}"
    shape = re.sub(r"[A-Za-z_$][\w$]*", "id", raw_snippet)
    shape = re.sub(r"\d+", "n", shape)
    shape = re.sub(r"\s+", " ", shape).strip()[:80]
    return f"snippet:{shape or 'unknown'}"


def _is_unknown_ability(ability: Any) -> bool:
    if not isinstance(ability, dict):
        return True
    ability_type = ability.get("type") or ability.get("kind")
    if ability_type in {None, "unknown"}:
        return True
    reason = str(ability.get("_unsupported_reason") or "")
    return "unknown" in reason.lower()


def _raw_snippet(raw: dict[str, Any], source_file: str, source_root: str | Path) -> str:
    expression = raw.get("rawExpression") or raw.get("rawHelper")
    if expression:
        return str(expression)
    nested_raw = raw.get("raw")
    if isinstance(nested_raw, dict) and nested_raw.get("tsObject"):
        return str(nested_raw["tsObject"])
    if source_file and raw.get("rawReference"):
        path = Path(source_root) / source_file
        if path.exists():
            needle = str(raw["rawReference"])
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if re.search(rf"\b{re.escape(needle)}\b", line):
                    return " ".join(line.strip().split())
    return ""


def _detected_helper_calls(raw: dict[str, Any], raw_snippet: str) -> list[str]:
    helpers: set[str] = set()
    for key in ("helper", "rawReference"):
        value = raw.get(key)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z_$][\w$]*", value):
            helpers.add(value)
    for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", raw_snippet):
        helpers.add(name)
    return sorted(helpers)


def _detected_string_literals(value: Any) -> list[str]:
    literals: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            if isinstance(item, str):
                literals.add(item)
            elif isinstance(item, (dict, list)):
                literals.update(_detected_string_literals(item))
    elif isinstance(value, list):
        for item in value:
            literals.update(_detected_string_literals(item))
    return sorted(literals)[:20]


def _summary(unknowns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_unknowns": len(unknowns),
        "by_inferred_category": _counter_dict(item["inferred_category"] for item in unknowns),
        "by_recommended_action": _counter_dict(item["recommended_action"] for item in unknowns),
        "by_source_file": _counter_dict(item["source_file"] for item in unknowns if item["source_file"]),
        "by_helper_call": _counter_dict(helper for item in unknowns for helper in item["detected_helper_calls"]),
        "by_pattern_fingerprint": _counter_dict(item["pattern_fingerprint"] for item in unknowns),
    }


def _counter_dict(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _majority(items: list[dict[str, Any]], key: str) -> str:
    counter = Counter(str(item.get(key) or "") for item in items)
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0] if counter else ""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_SOURCE_ROOT = Path("/home/andre/LorcanaChamp/lorcanito-full-src-code")

CARD_FIELDS = [
    "id",
    "canonicalId",
    "reprints",
    "cardType",
    "name",
    "version",
    "inkType",
    "franchise",
    "set",
    "cardNumber",
    "rarity",
    "cost",
    "inkable",
    "strength",
    "willpower",
    "lore",
    "moveCost",
    "classifications",
    "actionSubtype",
    "text",
    "abilities",
    "i18n",
]

KNOWN_KEYWORD_HELPERS = {
    "rush": "Rush",
    "ward": "Ward",
    "evasive": "Evasive",
    "bodyguard": "Bodyguard",
    "support": "Support",
    "reckless": "Reckless",
    "vanish": "Vanish",
    "alert": "Alert",
    "resist": "Resist",
    "challenger": "Challenger",
    "singer": "Singer",
    "singTogether": "Sing Together",
    "shift": "Shift",
    "boost": "Boost",
}

KNOWN_TRIGGER_HELPERS = {
    "wheneverQuests",
    "whenPlayed",
    "whenBanishes",
    "whenChallenged",
}

KNOWN_STATIC_HELPERS = {
    "duringYourTurn",
    "whileHere",
    "gainAbility",
}

KNOWN_TARGET_HELPERS = {
    "chosenCharacter",
    "chosenOpposingCharacter",
    "chosenItem",
    "chosenLocation",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Lorcanito TS card source into Python-runtime JSON artifacts.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out-dir", type=Path, default=Path("data/lorcanito_extracted"))
    args = parser.parse_args()
    extract(args.source_root, args.out_dir)


def extract(source_root: Path, out_dir: Path) -> dict[str, Any]:
    source_root = Path(source_root)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = _source_paths(source_root)
    inventories = _new_inventories()
    source_index: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    parser_gaps: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    helper_definitions = _extract_helper_definitions(paths["helpers"], source_root)

    for category, files in paths.items():
        for file in files:
            rel = _rel(file, source_root)
            text = file.read_text(encoding="utf-8", errors="replace")
            source_index.append(
                {
                    "path": rel,
                    "category": category,
                    "bytes": len(text.encode("utf-8")),
                    "extracted": _file_extraction_summary(text, category),
                }
            )
            _scan_text_inventory(text, rel, inventories)

    test_stems = {file.with_suffix("").with_suffix("").name if file.name.endswith(".test.ts") else file.stem for file in paths["card_tests"]}
    for file in paths["card_sources"]:
        text = file.read_text(encoding="utf-8", errors="replace")
        parsed_cards = _extract_cards_from_file(text, file, source_root, test_stems, helper_definitions, parser_gaps)
        if not parsed_cards and "export const" in text and "cardType" in text:
            warnings.append(f"no_card_object_extracted:{_rel(file, source_root)}")
        for card in parsed_cards:
            cards.append(card)
            _scan_card_inventory(card, inventories)

    cards = _resolve_spread_cards(cards, parser_gaps)
    cards.sort(key=lambda item: (str(item.get("set") or ""), int(item.get("cardNumber") or 0), str(item.get("id") or item.get("sourceFile"))))
    source_mtime = max((file.stat().st_mtime for files in paths.values() for file in files), default=0)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_root": str(source_root.resolve()) + "/",
        "generated_at": datetime.fromtimestamp(source_mtime, timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/extract_lorcanito_source_cards.py",
        "cards_source_path": str((source_root / "packages/lorcana/lorcana-cards/src/cards").resolve()),
        "source_file_count": sum(len(files) for files in paths.values()),
        "card_file_count": len(paths["card_sources"]),
        "test_file_count": len(paths["card_tests"]),
        "helper_file_count": len(paths["helpers"]),
        "engine_reference_file_count": len(paths["engine_references"]),
        "warnings": warnings,
        "errors": errors,
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_json(out_dir / "cards.normalized.json", {"schema_version": SCHEMA_VERSION, "cards": cards})
    for name, inventory in inventories.items():
        _write_json(out_dir / f"{name}.schema_inventory.json", _inventory_payload(inventory))
    _write_json(out_dir / "source_file_index.json", {"schema_version": SCHEMA_VERSION, "files": source_index})
    _write_json(out_dir / "unsupported_patterns.json", _unsupported_patterns(cards))
    _write_json(out_dir / "mapping_coverage.json", _basic_mapping_coverage(cards, inventories))
    _write_json(out_dir / "helper_call_inventory.json", _helper_call_inventory(paths, source_root, helper_definitions))
    _write_json(out_dir / "parser_gap_report.json", _parser_gap_report(parser_gaps))
    return manifest


def _source_paths(source_root: Path) -> dict[str, list[Path]]:
    cards_root = source_root / "packages/lorcana/lorcana-cards/src/cards"
    helpers_root = source_root / "packages/lorcana/lorcana-cards/src/helpers"
    types_root = source_root / "packages/lorcana/lorcana-types/src"
    engine_root = source_root / "packages/lorcana/lorcana-engine/src"
    all_card_ts = sorted(cards_root.glob("**/*.ts"))
    return {
        "card_sources": [
            file
            for file in all_card_ts
            if not file.name.endswith(".test.ts")
            and not file.name.endswith(".i18n.ts")
            and file.name not in {"index.ts", "catalog-data.ts", "sync.ts", "types.ts"}
        ],
        "card_tests": sorted(cards_root.glob("**/*.test.ts")),
        "card_indexes": sorted(file for file in [cards_root / "catalog-data.ts", cards_root / "index.ts"] if file.exists()),
        "helpers": sorted(helpers_root.glob("**/*.ts")),
        "types": sorted(types_root.glob("**/*.ts")),
        "engine_references": sorted(
            file
            for root in [
                engine_root / "runtime-moves/resolution",
                engine_root / "rules",
                engine_root / "targeting",
                engine_root / "triggered-abilities",
                engine_root / "automation",
                engine_root / "support-probe",
                engine_root / "runtime-moves",
                engine_root / "runtime-game",
            ]
            for file in root.glob("**/*.ts")
            if root.exists()
        ),
    }


def _extract_cards_from_file(
    text: str,
    file: Path,
    source_root: Path,
    test_stems: set[str],
    helper_definitions: dict[str, dict[str, Any]] | None = None,
    parser_gaps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    clean = _strip_comments(text)
    cards: list[dict[str, Any]] = []
    import_aliases = _import_aliases(clean)
    for match in re.finditer(r"export\s+const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*{", clean):
        var_name = match.group(1)
        object_start = clean.find("{", match.start())
        snippet = _balanced(clean, object_start, "{", "}")
        if not snippet or ("cardType" not in snippet and "..." not in snippet and not re.search(r"\bType\s*:", snippet)):
            continue
        raw = _parse_object(snippet)
        if raw is None:
            raw = _fallback_card_fields(snippet)
            raw["_parseWarning"] = "json_sanitizer_failed"
            if parser_gaps is not None:
                parser_gaps.append(
                    _parser_gap(
                        source_file=_rel(file, source_root),
                        card_id=raw.get("id"),
                        card_name=raw.get("name") or raw.get("Name"),
                        gap_type="object_literal_parse_failed",
                        snippet=snippet[:1000],
                        impact="unknown",
                        recommended_fix="Improve JS literal sanitizer for this card object shape.",
                        confidence="medium",
                    )
                )
        raw["sourceFile"] = _rel(file, source_root)
        raw["exportedName"] = var_name
        raw["hasTest"] = file.stem in test_stems
        raw["_spreadImports"] = import_aliases
        _normalize_legacy_card_shape(raw, file)
        for field in CARD_FIELDS:
            raw.setdefault(field, [] if field in {"reprints", "inkType", "classifications", "abilities"} else None)
        raw["raw"] = {"tsObject": snippet}
        raw["abilities"] = _normalize_abilities(raw.get("abilities", []), helper_definitions or {}, import_aliases)
        if parser_gaps is not None:
            for index, ability in enumerate(raw["abilities"]):
                if isinstance(ability, dict) and ability.get("type") == "unknown" and ability.get("helper"):
                    parser_gaps.append(
                        _parser_gap(
                            source_file=raw["sourceFile"],
                            card_id=raw.get("id"),
                            card_name=raw.get("name"),
                            gap_type="helper_unresolved",
                            snippet=str(ability.get("rawExpression") or ability.get("rawReference") or ""),
                            impact="lost_ability",
                            recommended_fix="Add a safe structural mapping for this helper or preserve it as an explicitly unsupported ability kind.",
                            confidence="high",
                        )
                    )
        cards.append(raw)
    return cards


def _parse_object(snippet: str) -> dict[str, Any] | None:
    spreads = re.findall(r"(?:^|[,{]\s*)\.\.\.\s*([A-Za-z_$][\w$]*)", snippet)
    snippet = re.sub(r"(^|[,{]\s*)\.\.\.\s*[A-Za-z_$][\w$]*\s*,?", r"\1", snippet)
    sanitized = _sanitize_js_literal(_replace_helper_calls(snippet))
    try:
        value = json.loads(sanitized)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    if spreads:
        value["_spreads"] = spreads
    return value


def _sanitize_js_literal(text: str) -> str:
    text = re.sub(r"\bundefined\b", "null", text)
    text = re.sub(r"`([^`$]*)`", lambda m: json.dumps(m.group(1)), text)
    text = re.sub(r"([,{]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', text)
    text = re.sub(r":\s*([A-Za-z_$][\w$]*)\s*([,}\]])", lambda m: f': "{m.group(1)}"{m.group(2)}' if m.group(1) not in {"true", "false", "null"} else m.group(0), text)
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"([\[,]\s*)([A-Za-z_$][\w$]*)\s*([,\]])", r'\1"\2"\3', text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def _replace_helper_calls(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        args = _split_args(match.group(2))
        keyword = KNOWN_KEYWORD_HELPERS[name]
        raw: dict[str, Any] = {
            "type": "keyword",
            "keyword": keyword,
            "helper": name,
            "args": [_literal_arg(arg) for arg in args],
            "rawExpression": match.group(0),
            "rawHelper": match.group(0),
        }
        if name == "shift" and len(args) == 2:
            target_name = _literal_arg(args[0])
            raw["shiftTarget"] = target_name
            raw["target_name"] = target_name
            raw["cost"] = {"ink": _literal_arg(args[1])}
        elif args:
            value = _literal_arg(args[0])
            if name == "shift":
                raw["cost"] = {"ink": value}
            else:
                raw["value"] = value
        return json.dumps(raw, sort_keys=True)

    pattern = r"\b(" + "|".join(re.escape(name) for name in KNOWN_KEYWORD_HELPERS) + r")\(([^()]*)\)"
    return re.sub(pattern, repl, text)


def _split_args(args: str) -> list[str]:
    if not args.strip():
        return []
    return [arg.strip() for arg in args.split(",")]


def _literal_arg(value: str) -> Any:
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _normalize_abilities(
    value: Any,
    helper_definitions: dict[str, dict[str, Any]] | None = None,
    import_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    abilities: list[dict[str, Any]] = []
    helper_definitions = helper_definitions or {}
    import_aliases = import_aliases or {}
    for index, item in enumerate(value):
        if isinstance(item, dict):
            item.setdefault("rawExpression", item.get("rawHelper"))
            abilities.append(item)
        else:
            helper = str(item)
            canonical = import_aliases.get(helper, helper)
            if canonical in helper_definitions:
                normalized = dict(helper_definitions[canonical])
                normalized.setdefault("id", f"helper-ref-{index}")
                normalized["helper"] = canonical
                normalized["rawReference"] = helper
                normalized["rawExpression"] = helper
                normalized["sourceHelper"] = helper_definitions[canonical].get("sourceHelper")
                abilities.append(normalized)
            elif helper in KNOWN_KEYWORD_HELPERS:
                abilities.append(_keyword_helper_record(helper, raw_expression=helper, ability_id=f"helper-ref-{index}"))
            else:
                abilities.append(
                    {
                        "type": "unknown",
                        "helper": canonical if re.fullmatch(r"[A-Za-z_$][\w$]*", canonical) else None,
                        "rawReference": item,
                        "rawExpression": helper,
                        "id": f"raw-ref-{index}",
                    }
                )
    return abilities


def _keyword_helper_record(helper: str, *, raw_expression: str, ability_id: str | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "type": "keyword",
        "keyword": KNOWN_KEYWORD_HELPERS[helper],
        "helper": helper,
        "rawExpression": raw_expression,
        "rawHelper": raw_expression,
    }
    if ability_id:
        raw["id"] = ability_id
    return raw


def _fallback_card_fields(snippet: str) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for key in [*CARD_FIELDS, "Id", "Name", "Title", "Type", "Colors", "Cost", "Inkwell", "Strength", "Willpower", "Lore", "MoveCost", "Set", "Number", "Rarity", "Characteristics"]:
        value_text = _extract_top_level_property_value(snippet, key)
        if value_text is not None:
            raw[key] = _parse_fallback_ts_value(value_text)
    spreads = re.findall(r"(?:^|[,{]\s*)\.\.\.\s*([A-Za-z_$][\w$]*)", snippet)
    if spreads:
        raw["_spreads"] = spreads
    abilities = _extract_ability_snippets(snippet)
    if abilities:
        raw["abilities"] = abilities
    return raw


def _import_aliases(text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for body, _source in re.findall(r"import\s*{\s*([^}]+)\s*}\s*from\s*[\"']([^\"']+)[\"']", text):
        for part in body.split(","):
            part = part.strip()
            if not part or part.startswith("type "):
                continue
            if " as " in part:
                imported, local = [piece.strip() for piece in part.split(" as ", 1)]
                aliases[local] = imported
            else:
                aliases[part] = part
    return aliases


def _normalize_legacy_card_shape(raw: dict[str, Any], file: Path) -> None:
    if "Id" in raw and not raw.get("id"):
        raw["id"] = raw.get("Id")
    if "Name" in raw and not raw.get("name"):
        raw["name"] = raw.get("Name")
    if "Title" in raw and not raw.get("version"):
        raw["version"] = raw.get("Title")
    if "Type" in raw and not raw.get("cardType"):
        raw["cardType"] = str(raw.get("Type") or "").lower()
    if "Colors" in raw and not raw.get("inkType"):
        raw["inkType"] = [str(value).lower() for value in raw.get("Colors", [])]
    for old, new in {
        "Cost": "cost",
        "Inkwell": "inkable",
        "Strength": "strength",
        "Willpower": "willpower",
        "Lore": "lore",
        "MoveCost": "moveCost",
        "Set": "set",
        "Number": "cardNumber",
        "Rarity": "rarity",
        "Characteristics": "classifications",
    }.items():
        if old in raw and not raw.get(new):
            raw[new] = raw[old]
    if not raw.get("cardType"):
        if "/characters/" in str(file):
            raw["cardType"] = "character"
        elif "/actions/" in str(file):
            raw["cardType"] = "action"
        elif "/items/" in str(file):
            raw["cardType"] = "item"
        elif "/locations/" in str(file):
            raw["cardType"] = "location"


def _resolve_spread_cards(cards: list[dict[str, Any]], parser_gaps: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    by_export: dict[str, dict[str, Any]] = {}
    for card in cards:
        if card.get("cardType"):
            by_export.setdefault(str(card.get("exportedName")), card)
    resolved: list[dict[str, Any]] = []
    for card in cards:
        merged = dict(card)
        for spread in card.get("_spreads", []) or []:
            alias = card.get("_spreadImports", {}).get(spread, spread)
            base = by_export.get(alias) or by_export.get(spread)
            if not base:
                if parser_gaps is not None:
                    parser_gaps.append(
                        _parser_gap(
                            source_file=str(card.get("sourceFile") or ""),
                            card_id=card.get("id"),
                            card_name=card.get("name"),
                            gap_type="spread_unresolved",
                            snippet=f"...{spread}",
                            impact="lost_ability" if not card.get("abilities") else "unknown",
                            recommended_fix="Resolve this spread target from imports or preserve the inherited card object explicitly.",
                            confidence="high",
                        )
                    )
                continue
            merged = _merge_card(base, merged)
        for field in CARD_FIELDS:
            merged.setdefault(field, [] if field in {"reprints", "inkType", "classifications", "abilities"} else None)
        resolved.append(merged)
    return resolved


def _merge_card(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key == "raw":
            continue
        if value is None:
            continue
        if value == [] and key in {"abilities", "classifications", "inkType", "reprints"}:
            continue
        merged[key] = value
    raw = dict(override.get("raw", {}))
    raw["spreadBaseSourceFile"] = base.get("sourceFile")
    raw["spreadBaseExportedName"] = base.get("exportedName")
    merged["raw"] = raw
    return merged


def _extract_ability_snippets(snippet: str) -> list[dict[str, Any]]:
    idx = snippet.find("abilities")
    if idx == -1:
        return []
    bracket = snippet.find("[", idx)
    array = _balanced(snippet, bracket, "[", "]") if bracket != -1 else ""
    if not array or len(array) < 2:
        return []
    # Strip outer brackets to get array content
    inner = array[1:-1].strip()
    if not inner:
        return []
    items = _split_top_level_array(inner)
    abilities = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        # Try to parse as object literal
        if item.startswith("{"):
            parsed = _parse_object(item)
            if parsed is not None:
                # Preserve nested structure
                ability_record = dict(parsed)
                ability_record["raw"] = {"tsObject": item}
                abilities.append(ability_record)
            else:
                # Fallback: preserve raw with unknown type
                abilities.append({
                    "type": "unknown",
                    "raw": {"tsObject": item},
                    "rawExpression": item,
                    "_parseWarning": "ability_object_parse_failed",
                })
        else:
            # Bare identifier or helper call - will be normalized by _normalize_abilities
            abilities.append(item)
    return abilities


def _extract_top_level_property_value(snippet: str, key: str) -> str | None:
    """Extract the value of a top-level property from a TypeScript object snippet.

    Respects quoted strings (single, double, template), arrays, nested objects,
    and function calls - does not split on commas inside delimiters.

    Returns the raw value text (without trailing comma) or None if not found.
    """
    # Pattern to match key at top level (after { or , or newline, not inside nested structure)
    # We look for: key followed by optional whitespace, then colon, then value
    pattern = rf"\b{re.escape(key)}\s*:"

    # Find all occurrences of the key
    for match in re.finditer(pattern, snippet):
        colon_pos = match.end() - 1  # Position of colon
        value_start = colon_pos + 1

        # Skip whitespace after colon
        while value_start < len(snippet) and snippet[value_start] in " \t":
            value_start += 1

        if value_start >= len(snippet):
            continue

        first_char = snippet[value_start]

        if first_char in '"\'`':
            # Quoted string - find matching close quote
            close = _find_matching_quote(snippet, value_start, first_char)
            if close != -1:
                return snippet[value_start:close + 1]
        elif first_char == "[":
            # Array - extract balanced brackets
            result = _balanced(snippet, value_start, "[", "]")
            return result
        elif first_char == "{":
            # Object - extract balanced braces
            result = _balanced(snippet, value_start, "{", "}")
            return result
        elif first_char == "(":
            # Function call - extract balanced parens
            result = _balanced(snippet, value_start, "(", ")")
            return result
        else:
            # Unquoted value - read until comma or closing brace at depth 0
            depth = 0
            quote = None
            escape = False
            end = value_start
            for i in range(value_start, len(snippet)):
                char = snippet[i]
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if quote:
                    if char == quote:
                        quote = None
                    continue
                if char in '"\'':
                    quote = char
                    continue
                if char in "{[(":
                    depth += 1
                elif char in "}])":
                    if depth == 0:
                        end = i
                        break
                    depth -= 1
                elif char in ",\n" and depth == 0:
                    end = i
                    break

            value = snippet[value_start:end].rstrip()
            if value:
                return value

    return None


def _find_matching_quote(text: str, start: int, quote_char: str) -> int:
    """Find the closing quote position, respecting escapes."""
    escape = False
    for i in range(start + 1, len(text)):
        char = text[i]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == quote_char:
            return i
        # Stop at newline (unterminated string but still valid stop)
        if char == "\n":
            break
    return -1


def _parse_fallback_ts_value(value_text: str) -> Any:
    """Parse a TypeScript value from the fallback extractor.

    Handles: strings, numbers, booleans, null, arrays, objects (as raw strings).
    """
    value_text = value_text.strip()

    # Handle null
    if value_text == "null":
        return None

    # Handle booleans
    if value_text == "true":
        return True
    if value_text == "false":
        return False

    # Handle numbers
    if re.fullmatch(r"-?\d+", value_text):
        return int(value_text)

    # Handle quoted strings
    if (value_text.startswith('"') and value_text.endswith('"')) or \
       (value_text.startswith("'") and value_text.endswith("'")):
        return value_text[1:-1]

    # Handle template strings
    if value_text.startswith("`") and value_text.endswith("`"):
        # Remove template string markers, handle basic escape sequences
        inner = value_text[1:-1]
        inner = inner.replace("\\`", "`").replace("\\$", "$").replace("\\n", "\n").replace("\\t", "\t")
        return inner

    # Handle arrays (extract string/number items)
    if value_text.startswith("[") and value_text.endswith("]"):
        inner = value_text[1:-1].strip()
        if not inner:
            return []
        # Parse array items carefully
        items = _split_top_level_array(inner)
        result = []
        for item in items:
            item = item.strip()
            if not item:
                continue
            # Remove quotes if present
            if (item.startswith('"') and item.endswith('"')) or \
               (item.startswith("'") and item.endswith("'")):
                result.append(item[1:-1])
            elif re.fullmatch(r"-?\d+", item):
                result.append(int(item))
            else:
                result.append(item)
        return result

    # Handle objects (as raw string)
    if value_text.startswith("{") and value_text.endswith("}"):
        return {"_rawObject": value_text}

    # Unquoted identifier or string
    return value_text


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def _balanced(text: str, start: int, opener: str, closer: str) -> str:
    if start < 0 or start >= len(text) or text[start] != opener:
        return ""
    depth = 0
    quote: str | None = None
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def _new_inventories() -> dict[str, dict[str, Any]]:
    return {
        "abilities": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
        "effects": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
        "targets": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
        "conditions": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
        "costs": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
        "triggers": {"counts": Counter(), "examples": {}, "source_files": defaultdict(list)},
    }


def _scan_text_inventory(text: str, rel: str, inventories: dict[str, dict[str, Any]]) -> None:
    for helper in re.findall(r"export\s+(?:const|function)\s+([A-Za-z_$][\w$]*)", text):
        _add_inventory(inventories["abilities"], f"helper:{helper}", rel, helper)
    for event in re.findall(r"event\s*:\s*[\"']([^\"']+)[\"']", text):
        _add_inventory(inventories["triggers"], f"event:{event}", rel, event)
    for target in re.findall(r"[\"']([A-Z][A-Z0-9_]+)[\"']", text):
        if "_" in target or target in {"SELF", "CONTROLLER", "OPPONENT"}:
            _add_inventory(inventories["targets"], f"alias:{target}", rel, target)


def _scan_card_inventory(card: dict[str, Any], inventories: dict[str, dict[str, Any]]) -> None:
    rel = str(card.get("sourceFile") or "")
    for ability in card.get("abilities", []):
        if not isinstance(ability, dict):
            continue
        kind = str(ability.get("type") or "unknown")
        _add_inventory(inventories["abilities"], kind, rel, ability)
        if isinstance(ability.get("trigger"), dict):
            trigger = ability["trigger"]
            if trigger.get("event"):
                _add_inventory(inventories["triggers"], f"event:{trigger['event']}", rel, trigger)
            if trigger.get("on"):
                _add_inventory(inventories["triggers"], f"on:{trigger['on']}", rel, trigger)
            if trigger.get("timing"):
                _add_inventory(inventories["triggers"], f"timing:{trigger['timing']}", rel, trigger)
        _scan_cost(ability.get("cost") or ability.get("costs"), rel, inventories)
        _scan_condition(ability.get("condition"), rel, inventories)
        _scan_effect(ability.get("effect") or ability.get("effects"), rel, inventories)


def _scan_effect(value: Any, rel: str, inventories: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in value:
            _scan_effect(item, rel, inventories)
        return
    if not isinstance(value, dict):
        return
    if value.get("type"):
        _add_inventory(inventories["effects"], str(value["type"]), rel, value)
    _scan_target(value.get("target"), rel, inventories)
    _scan_condition(value.get("condition"), rel, inventories)
    for key in ("effects", "branches", "sequence"):
        _scan_effect(value.get(key), rel, inventories)


def _scan_target(value: Any, rel: str, inventories: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, str):
        _add_inventory(inventories["targets"], f"alias:{value}", rel, value)
    elif isinstance(value, dict):
        selector = value.get("selector") or value.get("type") or value.get("kind")
        if selector:
            _add_inventory(inventories["targets"], f"selector:{selector}", rel, value)


def _scan_condition(value: Any, rel: str, inventories: dict[str, dict[str, Any]]) -> None:
    if not isinstance(value, dict):
        return
    kind = value.get("type") or value.get("kind")
    if kind:
        _add_inventory(inventories["conditions"], str(kind), rel, value)
    for key in ("conditions", "operands"):
        if isinstance(value.get(key), list):
            for item in value[key]:
                _scan_condition(item, rel, inventories)
    if isinstance(value.get("condition"), dict):
        _scan_condition(value["condition"], rel, inventories)


def _scan_cost(value: Any, rel: str, inventories: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, list):
        for item in value:
            _scan_cost(item, rel, inventories)
    elif isinstance(value, dict):
        for key in sorted(value):
            _add_inventory(inventories["costs"], key, rel, value.get(key))
        if isinstance(value.get("components"), list):
            for item in value["components"]:
                _scan_cost(item, rel, inventories)
    elif isinstance(value, str):
        _add_inventory(inventories["costs"], value, rel, value)


def _add_inventory(inventory: dict[str, Any], key: str, rel: str, example: Any) -> None:
    inventory["counts"][key] += 1
    inventory["examples"].setdefault(key, example)
    files = inventory["source_files"][key]
    if len(files) < 20 and rel not in files:
        files.append(rel)


def _extract_helper_definitions(files: list[Path], source_root: Path) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for file in sorted(files):
        text = _strip_comments(file.read_text(encoding="utf-8", errors="replace"))
        for match in re.finditer(r"export\s+const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*{", text):
            helper = match.group(1)
            snippet = _balanced(text, text.find("{", match.start()), "{", "}")
            if not snippet:
                continue
            raw = _parse_object(snippet)
            if not raw:
                continue
            raw["helper"] = helper
            raw["rawExpression"] = helper
            raw["rawReference"] = helper
            raw["sourceHelper"] = _rel(file, source_root)
            raw.setdefault("raw", {})["tsObject"] = snippet
            definitions[helper] = raw
    for helper in KNOWN_KEYWORD_HELPERS:
        definitions.setdefault(helper, _keyword_helper_record(helper, raw_expression=helper))
    return definitions


def _helper_call_inventory(
    paths: dict[str, list[Path]], source_root: Path, helper_definitions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    exported_helpers = set(helper_definitions)
    helper_roots = paths.get("helpers", [])
    for file in helper_roots:
        text = _strip_comments(file.read_text(encoding="utf-8", errors="replace"))
        exported_helpers.update(re.findall(r"export\s+(?:const|function)\s+([A-Za-z_$][\w$]*)", text))
    required = set(KNOWN_KEYWORD_HELPERS) | KNOWN_TRIGGER_HELPERS | KNOWN_STATIC_HELPERS | KNOWN_TARGET_HELPERS
    exported_helpers |= required

    calls: dict[str, dict[str, Any]] = {}
    scan_files = sorted([*paths.get("helpers", []), *paths.get("card_sources", [])])
    ignored = {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "describe",
        "it",
        "expect",
        "Array",
        "String",
        "Number",
        "Boolean",
    }
    for file in scan_files:
        rel = _rel(file, source_root)
        text = _strip_comments(file.read_text(encoding="utf-8", errors="replace"))
        names = set(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", text))
        names |= _ability_array_identifier_uses(text)
        for helper in sorted(name for name in names if name not in ignored and (name in exported_helpers or name in required)):
            snippets = _helper_snippets(text, helper)
            entry = calls.setdefault(
                helper,
                {
                    "helper": helper,
                    "count": 0,
                    "source_files": [],
                    "example_snippets": [],
                    "known_mapping": _helper_known_mapping(helper, helper_definitions),
                    "mapped": _helper_known_mapping(helper, helper_definitions) != "unknown",
                    "notes": _helper_notes(helper, helper_definitions),
                },
            )
            occurrences = max(1, len(snippets))
            entry["count"] += occurrences
            if rel not in entry["source_files"]:
                entry["source_files"].append(rel)
            for snippet in snippets[:3]:
                if len(entry["example_snippets"]) < 5 and snippet not in entry["example_snippets"]:
                    entry["example_snippets"].append(snippet)
    for helper in sorted(required):
        calls.setdefault(
            helper,
            {
                "helper": helper,
                "count": 0,
                "source_files": [],
                "example_snippets": [],
                "known_mapping": _helper_known_mapping(helper, helper_definitions),
                "mapped": _helper_known_mapping(helper, helper_definitions) != "unknown",
                "notes": _helper_notes(helper, helper_definitions),
            },
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "helpers": [calls[key] for key in sorted(calls)],
    }


def _ability_array_identifier_uses(text: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"\babilities\s*:", text):
        bracket = text.find("[", match.end())
        array = _balanced(text, bracket, "[", "]") if bracket != -1 else ""
        if not array:
            continue
        for item in _split_top_level_array(array[1:-1]):
            item = item.strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", item):
                names.add(item)
    return names


def _split_top_level_array(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False
    for index, char in enumerate(text):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _helper_snippets(text: str, helper: str) -> list[str]:
    snippets: list[str] = []
    for match in re.finditer(rf"\b{re.escape(helper)}\s*\([^)]*\)|\b{re.escape(helper)}\b", text):
        start = max(0, text.rfind("\n", 0, match.start()) + 1)
        end = text.find("\n", match.end())
        if end == -1:
            end = min(len(text), match.end() + 120)
        snippet = " ".join(text[start:end].strip().split())
        if snippet and snippet not in snippets:
            snippets.append(snippet[:240])
    return snippets


def _helper_known_mapping(helper: str, helper_definitions: dict[str, dict[str, Any]]) -> str:
    if helper in KNOWN_KEYWORD_HELPERS:
        return "keyword"
    definition = helper_definitions.get(helper) or {}
    kind = str(definition.get("type") or "")
    if kind in {"keyword", "triggered", "activated", "static", "action", "replacement"}:
        return kind
    if helper in KNOWN_TRIGGER_HELPERS:
        return "triggered"
    if helper in KNOWN_STATIC_HELPERS:
        return "static"
    if helper in KNOWN_TARGET_HELPERS:
        return "target"
    return "unknown"


def _helper_notes(helper: str, helper_definitions: dict[str, dict[str, Any]]) -> str:
    if helper in helper_definitions:
        source = helper_definitions[helper].get("sourceHelper")
        return f"definition discovered from {source}" if source else "known helper mapping"
    if helper in KNOWN_TRIGGER_HELPERS | KNOWN_STATIC_HELPERS | KNOWN_TARGET_HELPERS:
        return "known helper family; structure preserved when encountered"
    return "helper discovered by source scan"


def _parser_gap(
    *,
    source_file: str,
    card_id: Any,
    card_name: Any,
    gap_type: str,
    snippet: str,
    impact: str,
    recommended_fix: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "source_file": source_file,
        "card_id": "" if card_id is None else str(card_id),
        "card_name": "" if card_name is None else str(card_name),
        "gap_type": gap_type,
        "snippet": snippet,
        "impact": impact,
        "recommended_fix": recommended_fix,
        "confidence": confidence,
    }


def _parser_gap_report(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    unique = {
        (
            gap.get("source_file", ""),
            gap.get("card_id", ""),
            gap.get("gap_type", ""),
            gap.get("snippet", ""),
        ): gap
        for gap in gaps
    }
    ordered = [unique[key] for key in sorted(unique)]
    by_gap_type = Counter(str(gap.get("gap_type") or "unknown") for gap in ordered)
    by_impact = Counter(str(gap.get("impact") or "unknown") for gap in ordered)
    return {
        "schema_version": SCHEMA_VERSION,
        "gaps": ordered,
        "summary": {
            "by_gap_type": dict(sorted(by_gap_type.items())),
            "by_impact": dict(sorted(by_impact.items())),
            "source_files_with_gaps": len({gap.get("source_file") for gap in ordered if gap.get("source_file")}),
        },
    }


def _inventory_payload(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "counts": dict(sorted(inventory["counts"].items())),
        "examples": {key: _jsonable(value) for key, value in sorted(inventory["examples"].items())},
        "source_files": {key: sorted(value) for key, value in sorted(inventory["source_files"].items())},
    }


def _unsupported_patterns(cards: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for card in cards:
        for ability in card.get("abilities", []):
            if isinstance(ability, dict) and ability.get("type") in {"unknown", None}:
                counts[str(ability.get("rawReference") or ability.get("raw") or "unknown")] += 1
    return {"schema_version": SCHEMA_VERSION, "counts": dict(sorted(counts.items()))}


def _basic_mapping_coverage(cards: list[dict[str, Any]], inventories: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ability_total = sum(len(card.get("abilities", [])) for card in cards)
    return {
        "schema_version": SCHEMA_VERSION,
        "total_cards": len(cards),
        "total_ability_records": ability_total,
        "fully_structured_cards": sum(all(isinstance(a, dict) and a.get("type") != "unknown" for a in card.get("abilities", [])) for card in cards),
        "partially_structured_cards": sum(any(isinstance(a, dict) and a.get("type") != "unknown" for a in card.get("abilities", [])) for card in cards),
        "executable_cards": 0,
        "mapped_not_executable_cards": 0,
        "unsupported_cards": 0,
        "ability_type_counts": dict(sorted(inventories["abilities"]["counts"].items())),
        "effect_type_counts": dict(sorted(inventories["effects"]["counts"].items())),
        "condition_type_counts": dict(sorted(inventories["conditions"]["counts"].items())),
        "target_type_counts": dict(sorted(inventories["targets"]["counts"].items())),
        "cost_type_counts": dict(sorted(inventories["costs"]["counts"].items())),
        "trigger_event_counts": {k: v for k, v in sorted(inventories["triggers"]["counts"].items()) if k.startswith("event:")},
        "mapping_status_counts": {},
        "execution_status_counts": {},
        "unsupported_by_reason": {},
        "top_unsupported_patterns": [],
        "top_engine_blockers": [],
        "cards_by_status": {},
    }


def _file_extraction_summary(text: str, category: str) -> dict[str, int]:
    return {
        "exported_consts": len(re.findall(r"export\s+const\s+", text)),
        "type_literals": len(re.findall(r"type\s*:\s*[\"']", text)),
        "trigger_literals": len(re.findall(r"event\s*:\s*[\"']", text)),
        "category_scanned": 1 if category else 0,
    }


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()

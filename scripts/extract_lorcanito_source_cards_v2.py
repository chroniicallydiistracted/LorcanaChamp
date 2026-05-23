#!/usr/bin/env python3
"""Export Lorcanito runtime card catalog into LorcanaChamp-compatible JSON.

This script intentionally avoids regex parsing of TypeScript card files. It asks
Lorcanito's own card package to build `getAllCards()`, serializes that runtime
catalog plus `canonical-cards.json`, then writes a LorcanaChamp-compatible
`cards.normalized.json` shape that can be loaded by
`lorcana_bot.importers.lorcanito_source_importer.import_lorcanito_source_cards`.

Expected source root layout:
  <source-root>/packages/lorcana/lorcana-cards/src/cards/index.ts
  <source-root>/packages/lorcana/lorcana-cards/src/data/canonical-cards.json

Example:
  python3 scripts/export_lorcanito_runtime_cards.py \
    --source-root references/lorcana-simulator \
    --out-dir data/lorcanito_runtime_extracted

Then validate in LorcanaChamp:
  python3 - <<'PY'
  from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards
  db, report = import_lorcanito_source_cards('data/lorcanito_runtime_extracted/cards.normalized.json')
  print(len(db), report.errors, report.ability_type_counts)
  PY
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

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

# Extra Lorcanito fields that LorcanaChamp should preserve at top level, even if
# older extraction did not explicitly list them. The importer keeps the full raw
# object, but keeping these top-level makes parity reports easier to read.
EXTRA_PRESERVED_FIELDS = [
    "fullName",
    "simpleName",
    "flavorText",
    "externalIds",
    "allowedInFormats",
    "allowedInTournamentsFromDate",
    "reprintOfId",
    "baseId",
    "maxCopiesInDeck",
    "cardCopyLimit",
    "specialRarity",
    "printings",
    "implemented",
    "missingTestCase",
    "notImplemented",
    "errata",
    "illustrator",
    "imageUrl",
    "artist",
]

ABILITY_KINDS = {"keyword", "action", "triggered", "activated", "static", "replacement"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Lorcanito getAllCards()+canonical-cards.json into LorcanaChamp-compatible JSON."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Root containing packages/lorcana, usually Lorcanito repo root or references/lorcana-simulator.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/lorcanito_runtime_extracted"),
        help="Output directory for raw runtime export, normalized cards, and reports.",
    )
    parser.add_argument(
        "--runner",
        choices=("auto", "bun", "tsx"),
        default="auto",
        help="Runtime used to execute the temporary TypeScript exporter.",
    )
    parser.add_argument(
        "--keep-temp-exporter",
        action="store_true",
        help="Do not delete the generated temporary TypeScript exporter.",
    )
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _assert_lorcanito_layout(source_root)
    exporter = _write_temp_exporter(source_root)
    try:
        runtime_payload = _run_exporter(source_root, exporter, args.runner)
    finally:
        if not args.keep_temp_exporter:
            try:
                exporter.unlink()
                exporter.parent.rmdir()
            except OSError:
                pass

    cards = runtime_payload.get("cards")
    canonical_cards = runtime_payload.get("canonical_cards")
    if not isinstance(cards, list):
        raise SystemExit("Lorcanito exporter did not return a cards list")
    if not isinstance(canonical_cards, dict):
        raise SystemExit("Lorcanito exporter did not return canonical_cards object")

    normalized_cards = [_normalize_runtime_card(card, canonical_cards) for card in cards if isinstance(card, dict)]
    report = _build_report(normalized_cards, canonical_cards, source_root)

    _write_json(out_dir / "cards.runtime_raw.json", runtime_payload)
    _write_json(out_dir / "canonical-cards.json", canonical_cards)
    _write_json(
        out_dir / "cards.normalized.json",
        {
            "schema_version": SCHEMA_VERSION,
            "source": "lorcanito_getAllCards_runtime_export",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cards": normalized_cards,
        },
    )
    _write_json(out_dir / "runtime_card_export_report.json", report)

    print(f"cards exported: {report['cards_exported']}")
    print(f"canonical entries: {report['canonical_entries']}")
    print(f"id mismatches vs canonical: {len(report['canonical_id_mismatches'])}")
    print(f"duplicate card ids: {len(report['duplicate_ids'])}")
    print(f"unknown ability records: {report['unknown_ability_records']}")
    print(f"non-serializable markers: {report['non_serializable_marker_count']}")
    print(f"wrote: {out_dir / 'cards.normalized.json'}")


def _assert_lorcanito_layout(source_root: Path) -> None:
    required = [
        source_root / "packages/lorcana/lorcana-cards/src/cards/index.ts",
        source_root / "packages/lorcana/lorcana-cards/src/data/canonical-cards.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Not a Lorcanito source root, missing:\n" + "\n".join(missing))


def _write_temp_exporter(source_root: Path) -> Path:
    temp_dir = source_root / ".lorcanachamp_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    exporter = temp_dir / "export_runtime_cards.ts"
    exporter.write_text(
        r'''
import { getAllCards } from "../packages/lorcana/lorcana-cards/src/cards/index";
import canonicalRaw from "../packages/lorcana/lorcana-cards/src/data/canonical-cards.json";

function sanitize(value: any, seen: WeakSet<object> = new WeakSet()): any {
  if (value === undefined) return null;
  if (value === null) return null;
  const t = typeof value;
  if (t === "string" || t === "number" || t === "boolean") return value;
  if (t === "bigint") return Number(value);
  if (t === "symbol") return String(value);
  if (t === "function") return { __non_serializable: "function", name: value.name || null };
  if (Array.isArray(value)) return value.map((item) => sanitize(item, seen));
  if (t === "object") {
    if (seen.has(value)) return { __non_serializable: "circular" };
    seen.add(value);
    const out: Record<string, any> = {};
    for (const key of Object.keys(value)) out[key] = sanitize(value[key], seen);
    seen.delete(value);
    return out;
  }
  return String(value);
}

const cards = await getAllCards();
const payload = {
  schema_version: 1,
  source: "lorcanito_getAllCards_runtime_export",
  card_count: cards.length,
  cards: sanitize(cards),
  canonical_cards: sanitize(canonicalRaw),
};
console.log(JSON.stringify(payload));
'''.lstrip(),
        encoding="utf-8",
    )
    return exporter


def _run_exporter(source_root: Path, exporter: Path, runner: str) -> dict[str, Any]:
    cmd: list[str]
    if runner == "bun" or (runner == "auto" and shutil.which("bun")):
        cmd = ["bun", str(exporter)]
    elif runner == "tsx" or (runner == "auto" and shutil.which("npx")):
        cmd = ["npx", "tsx", str(exporter)]
    else:
        raise SystemExit(
            "No TypeScript runner found. Install Bun or run with --runner tsx in a Node project that can execute TS."
        )

    proc = subprocess.run(
        cmd,
        cwd=source_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "Lorcanito runtime export failed.\n"
            f"command: {' '.join(cmd)}\n"
            f"exit: {proc.returncode}\n"
            f"stdout:\n{proc.stdout[-4000:]}\n"
            f"stderr:\n{proc.stderr[-4000:]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Runtime exporter produced non-JSON stdout: {exc}\n{proc.stdout[:2000]}") from exc


def _normalize_runtime_card(card: dict[str, Any], canonical_cards: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in CARD_FIELDS:
        normalized[field] = card.get(field)
    for field in EXTRA_PRESERVED_FIELDS:
        if field in card:
            normalized[field] = card.get(field)

    # Normalize old/current Lorcanito field variants without erasing raw source.
    normalized["id"] = str(card.get("id") or card.get("canonicalId") or "")
    normalized["cardType"] = _lower_or_none(card.get("cardType"))
    normalized["inkType"] = [_lower_or_none(value) for value in _as_list(card.get("inkType")) if value]
    normalized["cost"] = _int_or_default(card.get("cost"), 0)
    normalized["inkable"] = bool(card.get("inkable", False))
    normalized["strength"] = _int_or_none(card.get("strength"))
    normalized["willpower"] = _int_or_none(card.get("willpower"))
    normalized["lore"] = _int_or_none(card.get("lore"))
    normalized["moveCost"] = _int_or_none(card.get("moveCost"))
    normalized["classifications"] = list(_as_list(card.get("classifications")))
    normalized["abilities"] = list(_as_list(card.get("abilities")))
    normalized["reprints"] = list(_as_list(card.get("reprints")))

    canonical_key = _canonical_key(card)
    canonical_entry = canonical_cards.get(canonical_key) if canonical_key else None
    normalized["canonicalKey"] = canonical_key
    normalized["canonicalEntry"] = canonical_entry

    # Preserve the complete runtime object. This is the field that makes future
    # card-structure regressions auditable without re-reading TypeScript.
    normalized["raw"] = {
        "runtimeCard": card,
        "canonicalKey": canonical_key,
        "canonicalEntry": canonical_entry,
    }
    return normalized


def _canonical_key(card: dict[str, Any]) -> str | None:
    set_value = card.get("set")
    card_number = card.get("cardNumber")
    if set_value is None or card_number is None:
        return None
    try:
        set_num = int(str(set_value).replace("P", "")) if str(set_value).isdigit() else None
    except ValueError:
        set_num = None
    if str(set_value).isdigit():
        base = f"set{set_num}-{int(card_number):03d}"
    else:
        # Promo/non-numeric set codes are still preserved, but canonical JSON may
        # use different keys. Report will surface missing canonical entries.
        base = f"{set_value}-{int(card_number):03d}" if str(card_number).isdigit() else f"{set_value}-{card_number}"
    special = card.get("specialRarity")
    return f"{base}-{special}" if special else base


def _build_report(cards: list[dict[str, Any]], canonical_cards: dict[str, Any], source_root: Path) -> dict[str, Any]:
    ids = [str(card.get("id")) for card in cards]
    id_counts = Counter(ids)
    ability_type_counts: Counter[str] = Counter()
    unknown_ability_records = 0
    cards_missing_canonical: list[dict[str, Any]] = []
    canonical_id_mismatches: list[dict[str, Any]] = []
    non_serializable_marker_count = 0

    for card in cards:
        card_id = str(card.get("id"))
        for ability in card.get("abilities") or []:
            if not isinstance(ability, dict):
                ability_type_counts["non_object"] += 1
                unknown_ability_records += 1
                continue
            ability_type = str(ability.get("type") or ability.get("kind") or "unknown")
            ability_type_counts[ability_type] += 1
            if ability_type not in ABILITY_KINDS:
                unknown_ability_records += 1

        canonical_key = card.get("canonicalKey")
        canonical_entry = card.get("canonicalEntry")
        if canonical_key and canonical_entry is None:
            cards_missing_canonical.append(
                {
                    "id": card_id,
                    "name": card.get("name"),
                    "version": card.get("version"),
                    "set": card.get("set"),
                    "cardNumber": card.get("cardNumber"),
                    "canonicalKey": canonical_key,
                }
            )
        if isinstance(canonical_entry, dict) and canonical_entry.get("id") != card_id:
            canonical_id_mismatches.append(
                {
                    "canonicalKey": canonical_key,
                    "name": card.get("name"),
                    "typescript_id": card_id,
                    "canonical_id": canonical_entry.get("id"),
                }
            )
        non_serializable_marker_count += _count_non_serializable_markers(card)

    return {
        "schema_version": SCHEMA_VERSION,
        "source_root": str(source_root),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cards_exported": len(cards),
        "canonical_entries": len(canonical_cards),
        "duplicate_ids": [card_id for card_id, count in sorted(id_counts.items()) if count > 1],
        "ability_type_counts": dict(sorted(ability_type_counts.items())),
        "unknown_ability_records": unknown_ability_records,
        "cards_missing_canonical": cards_missing_canonical,
        "canonical_id_mismatches": canonical_id_mismatches,
        "non_serializable_marker_count": non_serializable_marker_count,
        "outputs": {
            "runtime_raw": "cards.runtime_raw.json",
            "canonical_cards": "canonical-cards.json",
            "normalized_cards": "cards.normalized.json",
        },
    }


def _count_non_serializable_markers(value: Any) -> int:
    if isinstance(value, dict):
        return (1 if "__non_serializable" in value else 0) + sum(_count_non_serializable_markers(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_non_serializable_markers(v) for v in value)
    return 0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _lower_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).lower()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_default(value: Any, default: int) -> int:
    parsed = _int_or_none(value)
    return default if parsed is None else parsed


if __name__ == "__main__":
    main()

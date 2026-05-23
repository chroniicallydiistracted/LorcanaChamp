from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lorcana_bot.importers.lorcanito_source_importer import import_lorcanito_source_cards


EXECUTABLE = "executable"


def _json_safe(value: Any) -> Any:
    """Convert tuples/objects into JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    return repr(value)


def _object_kind(obj: Any) -> str | None:
    return (
        getattr(obj, "kind", None)
        or getattr(obj, "event", None)
        or getattr(obj, "alias", None)
        or getattr(obj, "selector", None)
    )


def _object_raw(obj: Any) -> Any:
    return _json_safe(getattr(obj, "raw", None))


def _record(
    *,
    card: Any,
    ability: Any,
    object_type: str,
    obj: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "object_type": object_type,
        "object_kind": _object_kind(obj),
        "object_status": getattr(obj, "execution_status", None),
        "card": {
            "id": card.id,
            "full_name": card.full_name,
            "card_type": card.card_type,
            "ink": card.ink,
            "cost": card.cost,
            "set_code": getattr(card, "set_code", None),
            "collector_number": getattr(card, "collector_number", None),
        },
        "ability": {
            "id": getattr(ability, "id", None),
            "kind": getattr(ability, "kind", None),
            "name": getattr(ability, "name", None),
            "status": getattr(ability, "execution_status", None),
            "text": getattr(ability, "text", None),
        },
        "raw": _object_raw(obj),
    }


def _walk_effects(effect: Any) -> list[Any]:
    found = [effect]
    for child in getattr(effect, "effects", ()) or ():
        found.extend(_walk_effects(child))
    for branch in getattr(effect, "branches", ()) or ():
        found.extend(_walk_effects(branch))
    return found


def collect_unsupported(db: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for card in db.all_cards():
        for ability in getattr(card, "source_abilities", ()) or ():
            ability_status = getattr(ability, "execution_status", EXECUTABLE)
            if ability_status != EXECUTABLE:
                records.append(
                    _record(
                        card=card,
                        ability=ability,
                        object_type="ability",
                        obj=ability,
                        reason=ability_status,
                    )
                )

            for cost in getattr(ability, "costs", ()) or ():
                status = getattr(cost, "execution_status", EXECUTABLE)
                if status != EXECUTABLE:
                    records.append(
                        _record(
                            card=card,
                            ability=ability,
                            object_type="cost",
                            obj=cost,
                            reason=status,
                        )
                    )

            trigger = getattr(ability, "trigger", None)
            if trigger is not None:
                status = getattr(trigger, "execution_status", EXECUTABLE)
                if status != EXECUTABLE:
                    records.append(
                        _record(
                            card=card,
                            ability=ability,
                            object_type="trigger",
                            obj=trigger,
                            reason=status,
                        )
                    )

            condition = getattr(ability, "condition", None)
            if condition is not None:
                status = getattr(condition, "execution_status", EXECUTABLE)
                if status != EXECUTABLE:
                    records.append(
                        _record(
                            card=card,
                            ability=ability,
                            object_type="ability_condition",
                            obj=condition,
                            reason=status,
                        )
                    )

            for effect in getattr(ability, "effects", ()) or ():
                for item in _walk_effects(effect):
                    status = getattr(item, "execution_status", EXECUTABLE)
                    if status != EXECUTABLE:
                        records.append(
                            _record(
                                card=card,
                                ability=ability,
                                object_type="effect",
                                obj=item,
                                reason=status,
                            )
                        )

                    target = getattr(item, "target", None)
                    if target is not None:
                        target_status = getattr(target, "execution_status", EXECUTABLE)
                        if target_status != EXECUTABLE:
                            records.append(
                                _record(
                                    card=card,
                                    ability=ability,
                                    object_type="target",
                                    obj=target,
                                    reason=target_status,
                                )
                            )

                    effect_condition = getattr(item, "condition", None)
                    if effect_condition is not None:
                        condition_status = getattr(effect_condition, "execution_status", EXECUTABLE)
                        if condition_status != EXECUTABLE:
                            records.append(
                                _record(
                                    card=card,
                                    ability=ability,
                                    object_type="effect_condition",
                                    obj=effect_condition,
                                    reason=condition_status,
                                )
                            )

    return records


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = [
        "reason",
        "object_type",
        "object_kind",
        "object_status",
        "card_id",
        "card_full_name",
        "card_type",
        "set_code",
        "collector_number",
        "ability_id",
        "ability_kind",
        "ability_name",
        "ability_status",
    ]

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    "reason": row["reason"],
                    "object_type": row["object_type"],
                    "object_kind": row["object_kind"],
                    "object_status": row["object_status"],
                    "card_id": row["card"]["id"],
                    "card_full_name": row["card"]["full_name"],
                    "card_type": row["card"]["card_type"],
                    "set_code": row["card"]["set_code"],
                    "collector_number": row["card"]["collector_number"],
                    "ability_id": row["ability"]["id"],
                    "ability_kind": row["ability"]["kind"],
                    "ability_name": row["ability"]["name"],
                    "ability_status": row["ability"]["status"],
                }
            )


def write_markdown(path: Path, summary: dict[str, Any], records: list[dict[str, Any]], max_examples_per_reason: int) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["reason"]].append(row)

    lines: list[str] = []
    lines.append("# Lorcanito V2 Unsupported Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Cards loaded: `{summary['cards_loaded']}`")
    lines.append(f"- Import errors: `{summary['errors']}`")
    lines.append(f"- Ability records loaded: `{summary['ability_records_loaded']}`")
    lines.append("")
    lines.append("## Unsupported by reason")
    lines.append("")
    lines.append("| Reason | Count |")
    lines.append("|---|---:|")
    for reason, count in sorted(summary["unsupported_by_reason"].items()):
        lines.append(f"| `{reason}` | {count} |")

    lines.append("")
    lines.append("## Examples")
    lines.append("")

    for reason in sorted(grouped):
        rows = grouped[reason]
        lines.append(f"### `{reason}`")
        lines.append("")
        lines.append(f"Total detailed records: `{len(rows)}`")
        lines.append("")
        for row in rows[:max_examples_per_reason]:
            lines.append(f"- **{row['card']['full_name']}** (`{row['card']['id']}`)")
            lines.append(f"  - Object: `{row['object_type']}` / `{row['object_kind']}`")
            lines.append(f"  - Ability: `{row['ability']['kind']}` `{row['ability']['id']}` — {row['ability']['name']}")
            lines.append(f"  - Status: `{row['object_status']}`")
            raw = json.dumps(row["raw"], sort_keys=True, ensure_ascii=False)
            if len(raw) > 700:
                raw = raw[:700] + "..."
            lines.append(f"  - Raw: `{raw}`")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-json",
        default="data/lorcanito_runtime_extracted/cards.normalized.json",
        help="Path to Lorcanito normalized card JSON.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/lorcanito_runtime_extracted/reports/unsupported",
        help="Directory for generated report files.",
    )
    parser.add_argument(
        "--max-examples-per-reason",
        type=int,
        default=25,
        help="Number of examples per reason in the Markdown report.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db, report = import_lorcanito_source_cards(args.source_json)
    records = collect_unsupported(db)

    reason_counts = Counter(row["reason"] for row in records)
    object_type_counts = Counter(row["object_type"] for row in records)
    object_kind_counts = Counter(
        f"{row['object_type']}:{row['object_kind']}" for row in records
    )
    card_counts = Counter(row["card"]["full_name"] for row in records)

    summary = {
        "source_json": args.source_json,
        "cards_loaded": len(db),
        "errors": report.errors,
        "warnings": report.warnings,
        "ability_records_loaded": report.ability_records_loaded,
        "ability_type_counts": report.ability_type_counts,
        "unsupported_by_reason": report.unsupported_by_reason,
        "execution_status_counts": report.execution_status_counts,
        "detailed_record_count": len(records),
        "detailed_reason_counts": dict(sorted(reason_counts.items())),
        "object_type_counts": dict(sorted(object_type_counts.items())),
        "top_object_kind_counts": dict(object_kind_counts.most_common(100)),
        "top_card_counts": dict(card_counts.most_common(100)),
        "top_unsupported_patterns": report.top_unsupported_patterns,
        "outputs": {
            "summary_json": "unsupported_summary.json",
            "records_json": "unsupported_records.json",
            "records_csv": "unsupported_records.csv",
            "markdown": "unsupported_report.md",
        },
    }

    by_reason = defaultdict(list)
    for row in records:
        by_reason[row["reason"]].append(row)

    write_json(out_dir / "unsupported_summary.json", summary)
    write_json(out_dir / "unsupported_records.json", records)
    write_json(out_dir / "unsupported_by_reason.json", dict(sorted(by_reason.items())))
    write_csv(out_dir / "unsupported_records.csv", records)
    write_markdown(out_dir / "unsupported_report.md", summary, records, args.max_examples_per_reason)

    print(f"wrote: {out_dir / 'unsupported_summary.json'}")
    print(f"wrote: {out_dir / 'unsupported_records.json'}")
    print(f"wrote: {out_dir / 'unsupported_by_reason.json'}")
    print(f"wrote: {out_dir / 'unsupported_records.csv'}")
    print(f"wrote: {out_dir / 'unsupported_report.md'}")


if __name__ == "__main__":
    main()

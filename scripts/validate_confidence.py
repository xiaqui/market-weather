#!/usr/bin/env python3
"""Compare confidence candidates on chronologically separated data."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import fetch_market_data as model

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "confidence-validation.json"
VALIDATION_SESSIONS = 252
TOTAL_SESSIONS = 252 * 2
CANDIDATES = (
    "trend_only", "trend_agreement", "trend_agreement_distance",
    "candidate_a", "candidate_a_without_count",
)


def _correct(record: model.BacktestRecord) -> bool:
    return (record.ensemble_probability >= 0.5) == record.actual_up


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bucket(rows: list[tuple[model.BacktestRecord, float]]) -> dict[str, float | int]:
    return {
        "count": len(rows),
        "direction_accuracy": (
            sum(_correct(record) for record, _ in rows) / len(rows) if rows else 0.0
        ),
        "confidence_mean": statistics.fmean(value for _, value in rows) if rows else 0.0,
    }


def evaluate_candidate(
    train: list[model.BacktestRecord], validation: list[model.BacktestRecord], name: str,
) -> dict:
    train_values = [model.confidence_candidates(record)[name] for record in train]
    validation_rows = [
        (record, model.confidence_candidates(record)[name]) for record in validation
    ]
    quartiles = [_percentile(train_values, fraction) for fraction in (0.25, 0.5, 0.75)]
    quantile_rows = [[], [], [], []]
    for row in validation_rows:
        index = sum(row[1] > boundary for boundary in quartiles)
        quantile_rows[index].append(row)
    fixed = {}
    for label, lower, upper in (
        ("0.0-0.4", 0.0, 0.4), ("0.4-0.6", 0.4, 0.6),
        ("0.6-0.8", 0.6, 0.8), ("0.8-1.0", 0.8, 1.0000001),
    ):
        fixed[label] = _bucket([
            row for row in validation_rows if lower <= row[1] < upper
        ])
    quantile = {
        f"q{index + 1}": _bucket(rows) for index, rows in enumerate(quantile_rows)
    }
    values = [value for _, value in validation_rows]
    return {
        "train_quartile_boundaries": quartiles,
        "validation_distribution": {
            "mean": statistics.fmean(values), "min": min(values), "max": max(values),
            "p10": _percentile(values, 0.1), "p50": _percentile(values, 0.5),
            "p90": _percentile(values, 0.9),
        },
        "fixed_buckets": fixed,
        "train_quantile_buckets": quantile,
        "high_minus_low_accuracy": (
            quantile["q4"]["direction_accuracy"] - quantile["q1"]["direction_accuracy"]
            if quantile["q1"]["count"] and quantile["q4"]["count"] else None
        ),
    }


def build_report(histories: dict[str, list[model.Candle]]) -> dict:
    splits = {}
    for market in model.MARKET_ORDER:
        records = model.walk_forward_records(histories, market, sessions=TOTAL_SESSIONS)
        splits[market] = (records[:-VALIDATION_SESSIONS], records[-VALIDATION_SESSIONS:])
    report = {"markets": {}}
    for market, (train, validation) in splits.items():
        report["markets"][market] = {
            "train": {
                "count": len(train),
                "start_date_utc": datetime.fromtimestamp(train[0].timestamp, timezone.utc).date().isoformat(),
                "end_date_utc": datetime.fromtimestamp(train[-1].timestamp, timezone.utc).date().isoformat(),
            },
            "validation": {
                "count": len(validation),
                "start_date_utc": datetime.fromtimestamp(validation[0].timestamp, timezone.utc).date().isoformat(),
                "end_date_utc": datetime.fromtimestamp(validation[-1].timestamp, timezone.utc).date().isoformat(),
            },
            "analog_count_distribution": {
                "min": min(row.analog_count for row in validation),
                "max": max(row.analog_count for row in validation),
                "mean": statistics.fmean(row.analog_count for row in validation),
            },
            "candidates": {
                name: evaluate_candidate(train, validation, name) for name in CANDIDATES
            },
        }
    combined_train = [row for train, _ in splits.values() for row in train]
    combined_validation = [row for _, validation in splits.values() for row in validation]
    report["combined_validation"] = {
        "train_count": len(combined_train),
        "validation_count": len(combined_validation),
        "candidates": {
            name: evaluate_candidate(combined_train, combined_validation, name)
            for name in CANDIDATES
        },
    }
    report["method"] = {
        "split": "older 252 sessions train, newest 252 sessions validation per market",
        "validation_used_for_weight_selection": False,
        "candidate_scores_are_hit_probabilities": False,
        "production_decision": "deferred",
        "production_confidence_definition": "legacy Trend internal agreement",
        "display_label": "Trend信頼度（シグナル一致度・的中確率ではありません）",
        "reason": "No candidate showed a consistently better high than low validation group across markets",
    }
    return report


def main() -> None:
    snapshots = {name: model.fetch_market(symbol) for name, symbol in model.SYMBOLS.items()}
    report = build_report({name: item.candles for name, item in snapshots.items()})
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for market, result in report["markets"].items():
        print(market, result["train"], result["validation"])
        for name, metrics in result["candidates"].items():
            difference = metrics["high_minus_low_accuracy"]
            formatted = "n/a" if difference is None else f"{difference:+.1%}"
            print(f"  {name}: high-low={formatted}")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the pre-registered phase-2 validation without changing forecast rules."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import fetch_market_data as model


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "phase2-validation.json"
WINDOW_SIZE = 252
WINDOW_COUNT = 5


def split_windows(records: list[model.BacktestRecord]) -> list[list[model.BacktestRecord]]:
    """Return newest-first, fixed-size, mutually exclusive session windows."""
    windows = []
    for number in range(WINDOW_COUNT):
        end = len(records) - number * WINDOW_SIZE
        start = max(0, end - WINDOW_SIZE)
        if end <= 0 or end - start < WINDOW_SIZE:
            break
        windows.append(records[start:end])
    return windows


def wilson_interval(successes: int, samples: int, z: float = 1.959963984540054) -> list[float] | None:
    if samples == 0:
        return None
    proportion = successes / samples
    denominator = 1 + z * z / samples
    centre = (proportion + z * z / (2 * samples)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / samples + z * z / (4 * samples * samples)
    ) / denominator
    return [centre - margin, centre + margin]


def paired_counts(records: list[model.BacktestRecord]) -> dict[str, int]:
    counts = {"both_correct": 0, "trend_only_correct": 0,
              "analog_only_correct": 0, "both_wrong": 0}
    for record in records:
        if record.analog_probability is None:
            continue
        trend = (record.trend_probability >= 0.5) == record.actual_up
        analog = (record.analog_probability >= 0.5) == record.actual_up
        key = ("both_correct" if trend and analog else
               "trend_only_correct" if trend else
               "analog_only_correct" if analog else "both_wrong")
        counts[key] += 1
    return counts


def exact_paired_p_value(trend_only: int, analog_only: int) -> float | None:
    """Two-sided exact binomial p-value for discordant pairs, p=0.5."""
    total = trend_only + analog_only
    if total == 0:
        return None
    tail = sum(math.comb(total, index) for index in range(min(trend_only, analog_only) + 1))
    return min(1.0, 2 * tail / (2 ** total))


def describe_window(records: list[model.BacktestRecord]) -> dict[str, Any]:
    diagnostics = model.build_backtest_diagnostics(records)
    available = [record for record in records if record.analog_probability is not None]
    disagreement = [record for record in available if model.direction_group(record) in (
        "trend_up_analog_down", "trend_down_analog_up"
    )]
    pairs = paired_counts(available)
    disagreement_pairs = paired_counts(disagreement)
    summary = model.summarize_backtest_records(records)
    intervals = {
        name: wilson_interval(model._correct_count(rows, f"{name}_probability"), len(rows))
        for name, rows in (
            ("trend", records), ("analog", available), ("ensemble", records)
        )
    }
    return {
        "start_timestamp": records[0].timestamp,
        "end_timestamp": records[-1].timestamp,
        "start_date_utc": datetime.fromtimestamp(records[0].timestamp, timezone.utc).date().isoformat(),
        "end_date_utc": datetime.fromtimestamp(records[-1].timestamp, timezone.utc).date().isoformat(),
        "sample_count": len(records),
        "analog_available_count": diagnostics["analog_available_count"],
        "actual_up_rate": sum(record.actual_up for record in records) / len(records),
        "accuracy": {name: summary[f"{name}_accuracy"] for name in ("trend", "analog", "ensemble")},
        "accuracy_wilson_95": intervals,
        "brier": diagnostics["brier"],
        "agreement": diagnostics["agreement"],
        "disagreement": diagnostics["disagreement"],
        "direction_groups": diagnostics["direction_groups"],
        "paired": pairs,
        "paired_exact_binomial_p_value": exact_paired_p_value(
            pairs["trend_only_correct"], pairs["analog_only_correct"]
        ),
        "disagreement_paired": disagreement_pairs,
        "distance_groups": diagnostics["distance_groups"],
        "strength_groups": diagnostics["strength_groups"],
    }


def build_report(histories: dict[str, list[model.Candle]]) -> dict[str, Any]:
    markets: dict[str, Any] = {}
    for market in model.MARKET_ORDER:
        records = model.walk_forward_records(
            histories, market, sessions=WINDOW_SIZE * WINDOW_COUNT
        )
        windows = split_windows(records)
        described = [describe_window(window) for window in windows]
        validations = described[1:]
        markets[market] = {
            "windows": {f"window_{index}": value for index, value in enumerate(described)},
            "reproducibility": {
                "validation_window_count": len(validations),
                "analog_accuracy_above_trend": sum(
                    item["accuracy"]["analog"] > item["accuracy"]["trend"] for item in validations
                ),
                "analog_disagreement_accuracy_above_trend": sum(
                    item["disagreement"]["analog_accuracy"] > item["disagreement"]["trend_accuracy"]
                    for item in validations
                ),
                "analog_brier_below_trend": sum(
                    item["brier"]["analog"] < item["brier"]["trend"] for item in validations
                ),
            },
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": {
            "window_size_sessions": WINDOW_SIZE,
            "window_0_role": "discovery",
            "window_1_and_earlier_role": "validation",
            "window_order": "newest first",
            "forecast_rules_changed": False,
        },
        "markets": markets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    snapshots = {name: model.fetch_market(symbol) for name, symbol in model.SYMBOLS.items()}
    report = build_report({name: snapshot.candles for name, snapshot in snapshots.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for market, result in report["markets"].items():
        counts = result["reproducibility"]
        total = counts["validation_window_count"]
        print(
            f"{market}: Analog>Trend accuracy "
            f"{counts['analog_accuracy_above_trend']}/{total}, disagreement "
            f"{counts['analog_disagreement_accuracy_above_trend']}/{total}, "
            f"Brier {counts['analog_brier_below_trend']}/{total}"
        )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

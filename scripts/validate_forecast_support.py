#!/usr/bin/env python3
"""Build leak-safe structural diagnostics for forecast_support."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import fetch_market_data as model

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "forecast-support-validation.json"


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    percentile = lambda fraction: ordered[round((len(ordered) - 1) * fraction)]
    return {
        "count": len(values), "min": min(values), "p10": percentile(0.1),
        "median": percentile(0.5), "p90": percentile(0.9), "max": max(values),
        "mean": statistics.fmean(values),
    }


def build_report(histories: dict[str, list[model.Candle]]) -> dict:
    markets = {}
    for market in model.MARKET_ORDER:
        records = model.walk_forward_records(histories, market, sessions=252)
        available = [row for row in records if row.analog_probability is not None]
        agreement = [
            row for row in available
            if abs(row.trend_probability - row.analog_probability) <= 0.15
        ]
        disagreement = [
            row for row in available
            if abs(row.trend_probability - row.analog_probability) >= 0.35
        ]
        ordered_quality = sorted(available, key=lambda row: row.analog_distance_quality)
        third = len(ordered_quality) // 3
        weak_quality = ordered_quality[:third]
        strong_quality = ordered_quality[-third:]
        candidates = {name: [] for name in ("candidate_a", "candidate_b", "candidate_c")}
        for row in records:
            analog = None if row.analog_probability is None else model.AnalogResult(
                row.analog_probability, row.analog_count,
                row.analog_mean_distance or 0.0, 0.0, (),
                row.analog_distance_quality, row.analog_effective_sample_size,
            )
            for name, value in model.forecast_support_candidates(
                row.trend_probability, row.trend_confidence, analog
            ).items():
                candidates[name].append(value)
        mean_support = lambda rows: (
            statistics.fmean(row.forecast_support for row in rows) if rows else None
        )
        markets[market] = {
            "forecast_support": _distribution([row.forecast_support for row in records]),
            "candidate_distributions": {
                name: _distribution(values) for name, values in candidates.items()
            },
            "structure_checks": {
                "close_probability_difference_mean": mean_support(agreement),
                "large_probability_difference_mean": mean_support(disagreement),
                "weak_analog_quality_mean": mean_support(weak_quality),
                "strong_analog_quality_mean": mean_support(strong_quality),
            },
            "reference_only": {
                "direction_accuracy": sum(
                    (row.ensemble_probability >= 0.5) == row.actual_up for row in records
                ) / len(records)
            },
        }
    return {
        "definition": {
            "selected": "candidate_c",
            "formula": "0.35 trend + 0.30 agreement + 0.20 relative distance quality + 0.15 ESS/30",
            "trend_only": "0.35 * trend confidence; unavailable Analog components contribute zero",
            "is_hit_probability": False,
        },
        "markets": markets,
    }


def main() -> None:
    snapshots = {name: model.fetch_market(symbol) for name, symbol in model.SYMBOLS.items()}
    report = build_report({name: item.candles for name, item in snapshots.items()})
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

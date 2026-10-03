#!/usr/bin/env python3
"""Compare the production common Analog with an isolated 3-material experiment.

This module is deliberately not imported by the forecast generation path.  It
uses completed Yahoo daily bars, an as-of join, and expanding historical
candidate sets so that an external close after the forecast clock cannot leak
into either a feature or an Analog outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import fetch_market_data as model
from scripts.validate_phase2 import describe_window, split_windows

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "target-specific-weather-map-v1.json"
DEFAULT_OOS_REPORT = ROOT / "reports" / "target-specific-weather-map-v1-oos.json"
FROZEN_REPORT = ROOT / "reports" / "target-specific-weather-map-v1.json"

MATERIALS = {
    "nikkei": (("^DJI", "US equities"), ("JPY=X", "yen exchange rate"), ("GC=F", "gold")),
    "dow": (("^VIX", "risk aversion"), ("^IXIC", "growth equities"), ("^TNX", "US rates")),
    "usdjpy": (("DX-Y.NYB", "broad US dollar"), ("^TNX", "US rates"), ("^N225", "Japanese equities")),
    "gold": (("DX-Y.NYB", "broad US dollar"), ("^TNX", "US rates"), ("^VIX", "risk aversion")),
}

# Conservative availability clocks for research-only symbols. Yahoo labels
# daily rows by date rather than by the instant at which the close was known.
EXPERIMENTAL_CLOSE = {
    # VIX continues to be disseminated through the end of its 16:15 ET
    # extended calculation session.  The other clocks are the end of the
    # published daily session, not Yahoo's arbitrary daily-row label time.
    "^VIX": ("America/New_York", time(16, 15)),
    "^IXIC": ("America/New_York", time(16, 0)),
    "^TNX": ("America/New_York", time(16, 0)),
    "DX-Y.NYB": ("America/New_York", time(17, 0)),
}


@dataclass(frozen=True)
class TargetSpecificBacktestRecord(model.BacktestRecord):
    """A scored outcome plus the exact information boundary of its forecast."""

    forecast_clock: int = 0
    max_material_timestamp: int = 0


def normalize_experimental_closes(symbol: str, rows: list[model.Candle]) -> list[model.Candle]:
    """Convert Yahoo date labels into conservative close-availability times."""
    if symbol not in EXPERIMENTAL_CLOSE:
        return rows
    zone_name, close_time = EXPERIMENTAL_CLOSE[symbol]
    zone = ZoneInfo(zone_name)
    normalized = []
    for row in rows:
        # Yahoo's daily labels for all four audited symbols retain their session
        # date in UTC (even though their intraday label hour varies by symbol).
        # Taking the date in New York would move some midnight-UTC labels back a
        # day, so do not infer the date in the exchange timezone here.
        session_date = datetime.fromtimestamp(row.timestamp, timezone.utc).date()
        timestamp = int(datetime.combine(session_date, close_time, tzinfo=zone).timestamp())
        normalized.append(replace(row, timestamp=timestamp))
    return normalized


def filter_completed(rows: list[model.Candle], evaluation_timestamp: int) -> list[model.Candle]:
    """Drop rows whose close/outcome was not known at report generation."""
    return [row for row in rows if row.timestamp <= evaluation_timestamp]


def target_material_symbols(target: str) -> tuple[str, ...]:
    return tuple(symbol for symbol, _ in MATERIALS[target])


def material_state_at(
    histories: dict[str, list[model.Candle]], timestamp: int, target: str
) -> model.WeatherMapState | None:
    """Return exactly the three material states available at ``timestamp``.

    A holiday or isolated missing row uses the last completed row (as-of
    semantics). A material with fewer than 21 observations is skipped entirely.
    No forward fill beyond the latest genuinely observed close is manufactured.
    """
    vector: list[float] = []
    for symbol in target_material_symbols(target):
        rows = histories.get(symbol, [])
        end = bisect_right([row.timestamp for row in rows], timestamp)
        available = rows[max(0, end - model.MINIMUM_HISTORY):end]
        if len(available) < model.MINIMUM_HISTORY:
            return None
        features = model.calculate_features(available)
        vol5 = max(features.volatility_5d, model.MINIMUM_DAILY_VOLATILITY)
        vol20 = max(features.volatility_20d, model.MINIMUM_DAILY_VOLATILITY)
        values = (
            features.return_1d / vol5,
            features.return_5d / (vol5 * 5 ** 0.5),
            features.return_20d / (vol20 * 20 ** 0.5),
            features.ma_deviation_20d / vol20,
            max(0.0, min(model.SIGNAL_CLIP, vol5 / vol20)),
        )
        vector.extend(max(-model.SIGNAL_CLIP, min(model.SIGNAL_CLIP, value)) for value in values)
    return model.WeatherMapState(timestamp, tuple(vector))


def max_material_timestamp_at(
    histories: dict[str, list[model.Candle]], timestamp: int, target: str
) -> int:
    """Return the newest material row actually eligible for this state."""
    used = []
    for symbol in target_material_symbols(target):
        rows = histories.get(symbol, [])
        end = bisect_right([row.timestamp for row in rows], timestamp)
        if end:
            used.append(rows[end - 1].timestamp)
    if len(used) != len(target_material_symbols(target)):
        raise ValueError(f"Incomplete material timestamp audit for {target}")
    return max(used)


def forecast_clock_at(
    material_clocks: list[int], previous_target_close: int, next_target_close: int
) -> int | None:
    """Return a clock where both Trend history and material state are knowable.

    The latest material clock can predate the target's previous close during a
    holiday or missing session.  In that case using it as the forecast clock
    while giving Trend the previous target close would be internally
    inconsistent.  Advance the query clock to that known target close without
    manufacturing a material row; the material join remains strictly as-of.
    """
    end = bisect_right(material_clocks, next_target_close - 1)
    if not end:
        return None
    clock = max(material_clocks[end - 1], previous_target_close)
    if clock >= next_target_close:
        raise AssertionError("forecast clock must be strictly before target outcome")
    return clock


def material_states(
    histories: dict[str, list[model.Candle]], target: str, target_rows: list[model.Candle]
) -> list[model.WeatherMapState]:
    clocks = sorted({row.timestamp for rows in histories.values() for row in rows})
    states = []
    for next_index in range(1, len(target_rows)):
        clock = forecast_clock_at(
            clocks, target_rows[next_index - 1].timestamp, target_rows[next_index].timestamp
        )
        if clock is None:
            continue
        state = material_state_at(histories, clock, target)
        if state is not None:
            states.append(state)
    return states


def walk_target_specific(
    production_histories: dict[str, list[model.Candle]],
    material_histories: dict[str, list[model.Candle]], target: str,
    sessions: int = 1260,
) -> list[TargetSpecificBacktestRecord]:
    target_rows = production_histories[target]
    states = material_states(material_histories, target, target_rows)
    clocks = sorted({row.timestamp for rows in material_histories.values() for row in rows})
    records = []
    start = max(model.MINIMUM_HISTORY, len(target_rows) - sessions)
    cumulative_up = [0]
    for index in range(1, len(target_rows)):
        cumulative_up.append(cumulative_up[-1] + (target_rows[index].close > target_rows[index - 1].close))
    for next_index in range(start, len(target_rows)):
        previous_target_close = target_rows[next_index - 1].timestamp
        clock = forecast_clock_at(
            clocks, previous_target_close, target_rows[next_index].timestamp
        )
        if clock is None:
            continue
        current = material_state_at(material_histories, clock, target)
        if current is None:
            continue
        trend = float(model.build_prediction(target_rows[:next_index])["trend_probability"])
        analog = model.find_analogs(current, states, target_rows)
        actual = target_rows[next_index].close > target_rows[next_index - 1].close
        analog_probability = None if analog is None else analog.probability
        ensemble = trend if analog is None else (trend + analog.probability) / 2
        max_material_timestamp = max_material_timestamp_at(material_histories, current.timestamp, target)
        if not (
            max_material_timestamp <= current.timestamp
            and previous_target_close <= current.timestamp < target_rows[next_index].timestamp
        ):
            raise AssertionError("material/target-history/forecast/outcome timestamps are not ordered")
        records.append(TargetSpecificBacktestRecord(
            timestamp=target_rows[next_index].timestamp,
            trend_probability=trend, analog_probability=analog_probability,
            ensemble_probability=ensemble, actual_up=actual,
            analog_count=0 if analog is None else analog.count,
            analog_mean_distance=None if analog is None else analog.mean_distance,
            historical_up_probability=cumulative_up[next_index - 1] / (next_index - 1),
            forecast_clock=current.timestamp,
            max_material_timestamp=max_material_timestamp,
        ))
    return records


def _paired(common: list[model.BacktestRecord], experiment: list[model.BacktestRecord]):
    """Build the common intersection once and reject outcome mismatches."""
    experiment_by_time = {row.timestamp: row for row in experiment}
    common_by_time = {row.timestamp: row for row in common}
    timestamps = sorted(set(common_by_time) & set(experiment_by_time))
    pairs = []
    for timestamp in timestamps:
        left, right = common_by_time[timestamp], experiment_by_time[timestamp]
        if left.actual_up != right.actual_up:
            raise ValueError(f"Actual outcome differs for paired timestamp {timestamp}")
        pairs.append((left, right))
    return pairs


def _split_paired_windows(pairs):
    """Cut windows only after pairing, guaranteeing identical membership."""
    return split_windows(pairs)


def build_report(production: dict[str, list[model.Candle]], materials: dict[str, list[model.Candle]],
                 evaluation_timestamp: int | None = None) -> dict[str, Any]:
    evaluation_timestamp = int(datetime.now(timezone.utc).timestamp()) if evaluation_timestamp is None else evaluation_timestamp
    production = {name: filter_completed(rows, evaluation_timestamp) for name, rows in production.items()}
    materials = {name: filter_completed(rows, evaluation_timestamp) for name, rows in materials.items()}
    markets = {}
    for target in model.MARKET_ORDER:
        # Five non-overlapping years retain the full preceding history as the
        # Analog candidate pool and match the existing phase-2 evaluation.
        common = model.walk_forward_records(production, target, sessions=1260)
        specific = walk_target_specific(production, materials, target)
        pairs = _paired(common, specific)
        paired_windows = _split_paired_windows(pairs)
        common_windows = [[pair[0] for pair in window] for window in paired_windows]
        specific_windows = [[pair[1] for pair in window] for window in paired_windows]
        markets[target] = {
            "materials": [{"symbol": symbol, "role": role} for symbol, role in MATERIALS[target]],
            "aligned_sample_count": len(pairs),
            "windows": [
                {"role": "discovery" if index == 0 else "exploratory_validation",
                 "pairing": {"sample_count_equal": len(left) == len(right),
                             "timestamp_range_equal": (left[0].timestamp, left[-1].timestamp) ==
                                                      (right[0].timestamp, right[-1].timestamp),
                             "actual_outcomes_equal": all(a.actual_up == b.actual_up for a, b in zip(left, right))},
                 "common": describe_window(left), "target_specific": describe_window(right)}
                for index, (left, right) in enumerate(zip(common_windows, specific_windows))
            ],
        }
    return {
        "generated_at": datetime.fromtimestamp(evaluation_timestamp, timezone.utc).isoformat(timespec="seconds"),
        "evaluation_timestamp": evaluation_timestamp,
        "production_forecast_changed": False,
        "decision": "research_only_do_not_adopt",
        "method": {
            "window_sessions": 252, "window_order": "newest first and mutually exclusive",
            "validation_status": "exploratory; these windows were already observed in prior research",
            "future_confirmation": "rerun unchanged on a later prospective 252-session window",
            "missing_policy": "as-of last completed close; skip state until every material has 21 observations",
            "forecast_clock_policy": "max(latest material close before outcome, previous target close); always strictly before outcome",
            "pairing_policy": "intersection on target and timestamp with identical actual outcome, then shared 252-session windows",
            "experimental_daily_availability": {
                "^VIX": "session UTC date at 16:15 America/New_York",
                "^IXIC": "session UTC date at 16:00 America/New_York",
                "^TNX": "session UTC date at 16:00 America/New_York",
                "DX-Y.NYB": "session UTC date at 17:00 America/New_York",
            },
        },
        "markets": markets,
    }



def _metric_deltas(common: dict[str, Any], target_specific: dict[str, Any]) -> dict[str, Any]:
    """Return target-specific minus common metrics for the paired OOS rows."""
    return {
        "accuracy": {
            name: target_specific["accuracy"][name] - common["accuracy"][name]
            for name in ("trend", "analog", "ensemble")
        },
        "brier": {
            name: target_specific["brier"][name] - common["brier"][name]
            for name in ("trend", "analog", "ensemble")
        },
    }


def build_oos_report(
    production: dict[str, list[model.Candle]],
    materials: dict[str, list[model.Candle]],
    frozen_evaluation_timestamp: int,
    evaluation_timestamp: int | None = None,
) -> dict[str, Any]:
    """Score only paired outcomes completed after the frozen v1 boundary."""
    evaluation_timestamp = (
        int(datetime.now(timezone.utc).timestamp())
        if evaluation_timestamp is None else evaluation_timestamp
    )
    if evaluation_timestamp <= frozen_evaluation_timestamp:
        raise ValueError("OOS evaluation must be later than the frozen v1 boundary")
    production = {
        name: filter_completed(rows, evaluation_timestamp) for name, rows in production.items()
    }
    materials = {
        name: filter_completed(rows, evaluation_timestamp) for name, rows in materials.items()
    }
    markets = {}
    for target in model.MARKET_ORDER:
        common = model.walk_forward_records(production, target, sessions=1260)
        specific = walk_target_specific(production, materials, target)
        pairs = [
            pair for pair in _paired(common, specific)
            if frozen_evaluation_timestamp < pair[0].timestamp <= evaluation_timestamp
        ]
        if not pairs:
            raise ValueError(f"No post-boundary paired outcomes for {target}")
        common_rows = [pair[0] for pair in pairs]
        specific_rows = [pair[1] for pair in pairs]
        common_summary = describe_window(common_rows)
        specific_summary = describe_window(specific_rows)
        markets[target] = {
            "materials": [
                {"symbol": symbol, "role": role} for symbol, role in MATERIALS[target]
            ],
            "sample_count": len(pairs),
            "outcome_dates_utc": [
                datetime.fromtimestamp(pair[0].timestamp, timezone.utc).date().isoformat()
                for pair in pairs
            ],
            "pairing": {
                "sample_count_equal": len(common_rows) == len(specific_rows),
                "timestamps_equal": all(a.timestamp == b.timestamp for a, b in pairs),
                "actual_outcomes_equal": all(a.actual_up == b.actual_up for a, b in pairs),
                "all_outcomes_after_frozen_boundary": all(
                    a.timestamp > frozen_evaluation_timestamp for a, _ in pairs
                ),
            },
            "common": common_summary,
            "target_specific": specific_summary,
            "target_specific_minus_common": _metric_deltas(
                common_summary, specific_summary
            ),
        }
    return {
        "generated_at": datetime.fromtimestamp(
            evaluation_timestamp, timezone.utc
        ).isoformat(timespec="seconds"),
        "evaluation_timestamp": evaluation_timestamp,
        "frozen_v1_evaluation_timestamp": frozen_evaluation_timestamp,
        "frozen_v1_evaluation_time": datetime.fromtimestamp(
            frozen_evaluation_timestamp, timezone.utc
        ).isoformat(timespec="seconds"),
        "production_forecast_changed": False,
        "decision": "short_term_oos_observation_do_not_adopt_or_tune",
        "method": {
            "oos_boundary": "outcome timestamp strictly greater than frozen v1 evaluation timestamp",
            "pairing_policy": "same target and timestamp with identical actual outcome",
            "model_policy": "frozen target-specific v1 materials, features, Analog distance, 50:50 Ensemble, and availability clocks",
            "interpretation": "small-sample initial OOS observation; not statistical significance",
        },
        "markets": markets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--oos", action="store_true",
        help="score only outcomes after the frozen v1 report evaluation timestamp",
    )
    args = parser.parse_args()
    evaluation_timestamp = int(datetime.now(timezone.utc).timestamp())
    production_snapshots = {name: model.fetch_market(symbol) for name, symbol in model.SYMBOLS.items()}
    symbols = sorted({symbol for rows in MATERIALS.values() for symbol, _ in rows})
    fetched = {symbol: model.fetch_market(symbol).candles for symbol in symbols}
    fetched = {symbol: normalize_experimental_closes(symbol, rows) for symbol, rows in fetched.items()}
    production = {name: snapshot.candles for name, snapshot in production_snapshots.items()}
    if args.oos:
        frozen = json.loads(FROZEN_REPORT.read_text(encoding="utf-8"))
        report = build_oos_report(
            production, fetched, frozen["evaluation_timestamp"],
            evaluation_timestamp=evaluation_timestamp,
        )
        output = args.output or DEFAULT_OOS_REPORT
    else:
        report = build_report(production, fetched, evaluation_timestamp=evaluation_timestamp)
        output = args.output or DEFAULT_REPORT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

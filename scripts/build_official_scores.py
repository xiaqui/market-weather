#!/usr/bin/env python3
"""Select one auditable forecast per market session and publish official scores."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "reports" / "live-forecast-history.json"
OUTPUT_PATH = ROOT / "web" / "official-scores.json"
JST = ZoneInfo("Asia/Tokyo")
NOMINAL_INTERVAL_COVERAGE: float | None = None


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def session_open(market: str, target: str) -> datetime:
    """Return the actual start of the labelled session (DST via zoneinfo)."""
    day = date.fromisoformat(target)
    if market == "nikkei":
        return datetime.combine(day, time(9), JST)
    eastern = ZoneInfo("America/New_York")
    if market == "dow":
        return datetime.combine(day, time(9, 30), eastern)
    if market == "usdjpy":
        previous = day - timedelta(days=1)
        return datetime.combine(previous, time(17), eastern)
    if market == "gold":
        # Yahoo labels these nearly-24-hour sessions by their closing date.
        previous = day - timedelta(days=1)
        return datetime.combine(previous, time(18), eastern)
    raise ValueError(f"Unknown market: {market}")


def _candidate(record: dict[str, Any], root: Path) -> tuple[bool, str, datetime | None]:
    try:
        generated = datetime.fromisoformat(record["forecast_source_generated_at"])
        if generated.tzinfo is None:
            return False, "generated_at_has_no_timezone", None
        market = record["market"]
        target = record["target_session_date"]
    except (KeyError, TypeError, ValueError):
        return False, "invalid_session_metadata", None
    symbol = market_data.SYMBOLS.get(market)
    if symbol is None:
        return False, "unknown_market_symbol", generated
    try:
        opening = session_open(market, target)
    except (TypeError, ValueError):
        return False, "invalid_session_metadata", generated
    if generated >= opening:
        return False, "generated_after_session_open", generated
    snapshot_path = root / str(record.get("forecast_file", ""))
    if not snapshot_path.is_file():
        return False, "snapshot_not_found", generated
    try:
        payload = _read(snapshot_path)
        markets = payload.get("forecast", {}).get("markets", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return False, "snapshot_unreadable", generated
    snapshot_market = next(
        (item for item in markets if isinstance(item, dict) and item.get("id") == record["market"]),
        None,
    ) if isinstance(markets, list) else None
    if snapshot_market is None:
        return False, "market_not_in_snapshot", generated
    last_date = snapshot_market.get("last_data_date")
    if not isinstance(last_date, str) or not last_date:
        return False, "missing_last_data_date", generated
    try:
        input_close = market_data.session_date_close_timestamp(symbol, last_date)
    except (TypeError, ValueError):
        return False, "invalid_last_data_date", generated
    if input_close > generated.timestamp():
        return False, "future_input_data", generated
    return True, "eligible", generated


def select_representatives(records: list[dict[str, Any]], root: Path = ROOT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], datetime]]] = defaultdict(list)
    audit: list[dict[str, Any]] = []
    for record in records:
        eligible, reason, generated = _candidate(record, root)
        item = {
            "market": record.get("market"),
            "target_session_date": record.get("target_session_date"),
            "forecast_file": record.get("forecast_file"),
            "generated_at": record.get("forecast_source_generated_at"),
            "status": "candidate" if eligible else "excluded",
            "reason": reason,
        }
        audit.append(item)
        if eligible and generated is not None:
            grouped[(record["market"], record["target_session_date"])].append((record, generated))

    selected: list[dict[str, Any]] = []
    for key, candidates in sorted(grouped.items()):
        target_day = date.fromisoformat(key[1])
        overnight = [
            pair for pair in candidates
            if pair[1].astimezone(JST).date() == target_day
            and time(0) <= pair[1].astimezone(JST).time() <= time(6)
        ]
        pool = overnight or candidates
        winner, _ = max(pool, key=lambda pair: pair[1])
        selected.append(winner)
        for item in audit:
            if (item["market"], item["target_session_date"]) != key or item["status"] != "candidate":
                continue
            if item["forecast_file"] == winner.get("forecast_file") and item["generated_at"] == winner.get("forecast_source_generated_at"):
                item.update(status="selected", reason="latest_00_06_jst" if overnight else "latest_before_open_fallback")
            else:
                item.update(status="excluded", reason="duplicate_not_representative")
    return selected, audit


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    comparable = [r for r in records if r.get("actual_direction") in {"up", "down"} and all(isinstance(r.get(f"{name}_probability"), (int, float)) for name in ("trend", "analog", "ensemble"))]
    forecasters = {}
    for name in ("trend", "analog", "ensemble"):
        probabilities = [float(r[f"{name}_probability"]) for r in comparable]
        correct = sum((p >= .5) == (r["actual_direction"] == "up") for p, r in zip(probabilities, comparable))
        briers = [(p - (1 if r["actual_direction"] == "up" else 0)) ** 2 for p, r in zip(probabilities, comparable)]
        forecasters[name] = {"samples": len(comparable), "accuracy": correct / len(comparable) if comparable else None, "mean_brier": _average(briers)}

    ranges = [r for r in records if all(isinstance(r.get(field), (int, float)) for field in ("predicted_range_low", "predicted_range_high", "actual_close")) and r["actual_close"] != 0]
    widths = [(r["predicted_range_high"] - r["predicted_range_low"]) / abs(r["actual_close"]) for r in ranges]
    coverage = [r["predicted_range_low"] <= r["actual_close"] <= r["predicted_range_high"] for r in ranges]
    interval_score = None
    if NOMINAL_INTERVAL_COVERAGE is not None:
        alpha = 1 - NOMINAL_INTERVAL_COVERAGE
        interval_score = _average([(r["predicted_range_high"] - r["predicted_range_low"]) + (2 / alpha) * max(r["predicted_range_low"] - r["actual_close"], 0) + (2 / alpha) * max(r["actual_close"] - r["predicted_range_high"], 0) for r in ranges])
    return {
        "representative_samples": len(records),
        "comparison_population": len(comparable),
        "small_sample": len(comparable) < 30,
        "forecasters": forecasters,
        "range": {"samples": len(ranges), "inside_rate": sum(coverage) / len(coverage) if coverage else None, "mean_width_close_ratio": _average(widths), "nominal_coverage": NOMINAL_INTERVAL_COVERAGE, "mean_interval_score": interval_score},
    }


def build_report(history_path: Path = HISTORY_PATH, output_path: Path = OUTPUT_PATH, root: Path = ROOT) -> dict[str, Any]:
    history = _read(history_path) if history_path.exists() else []
    if not isinstance(history, list):
        raise ValueError("Live forecast history must be a list")
    representatives, audit = select_representatives([r for r in history if isinstance(r, dict)], root)
    by_market = {market: _metrics([r for r in representatives if r.get("market") == market]) for market in market_data.SYMBOLS}
    report = {
        "schema_version": 1,
        "selection_policy": "latest valid 00:00-06:00 JST forecast before session open; otherwise latest valid forecast before open",
        "interval_score_note": "N/A: forecast interval nominal coverage is not defined; coverage and relative width are reported separately.",
        "overall": _metrics(representatives),
        "markets": by_market,
        "representatives": representatives,
        "audit": audit,
    }
    _write(output_path, report)
    return report


def main() -> None:
    report = build_report()
    print(f"Official scores: representatives={report['overall']['representative_samples']} comparable={report['overall']['comparison_population']}")


if __name__ == "__main__":
    main()

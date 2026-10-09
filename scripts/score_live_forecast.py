#!/usr/bin/env python3
"""Score saved prospective forecasts against completed daily sessions."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data

ROOT = Path(__file__).resolve().parents[1]
PROSPECTIVE_DIR = ROOT / "reports" / "live-forecast"
HISTORY_PATH = ROOT / "reports" / "live-forecast-history.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _coerce_probability(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number > 1:
        return None
    return number


def _direction_from_probability(value: float | None) -> str | None:
    if value is None:
        return None
    return "up" if value >= 0.5 else "down"


def _actual_direction(previous_close: float, close: float) -> str:
    if close > previous_close:
        return "up"
    if close < previous_close:
        return "down"
    return "flat"


def _brier_contribution(probability: float | None, actual_direction: str) -> float | None:
    # A flat session is neither of the binary up/down outcomes. Excluding it
    # avoids awarding an arbitrary probability an artificially good score.
    if probability is None or actual_direction == "flat":
        return None
    outcome = 1.0 if actual_direction == "up" else 0.0
    return (probability - outcome) ** 2


def _local_session_date(symbol: str, timestamp: int) -> str:
    hours = market_data.MARKET_HOURS.get(symbol)
    zone = timezone.utc if hours is None else ZoneInfo(hours.timezone_name)
    return datetime.fromtimestamp(timestamp, zone).date().isoformat()


def _target_session_date(
    market: dict[str, Any], symbol: str, candles: list[market_data.Candle], source_timestamp: int
) -> str | None:
    saved = market.get("next_session_date")
    if isinstance(saved, str) and saved:
        return saved
    available = [candle for candle in candles if candle.timestamp <= source_timestamp]
    if not available:
        return None
    return market_data.next_session_date(symbol, available)


def _display_forecast_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _score_market(
    forecast_file: Path,
    source_generated_at: str,
    market: dict[str, Any],
    candles: list[market_data.Candle],
) -> tuple[dict[str, Any] | None, str | None]:
    market_id = market.get("id")
    symbol = market_data.SYMBOLS.get(market_id)
    if symbol is None:
        return None, None
    source_timestamp = int(datetime.fromisoformat(source_generated_at).timestamp())
    target_date = _target_session_date(market, symbol, candles, source_timestamp)
    if target_date is None:
        return None, market_id
    # Never score a forecast whose target had already closed when the forecast
    # was generated. This second line of defense also protects history from
    # stale or manually created snapshots that bypassed the snapshot writer.
    if market_data.session_date_close_timestamp(symbol, target_date) <= source_timestamp:
        return None, None

    index_by_date = {
        _local_session_date(symbol, candle.timestamp): index
        for index, candle in enumerate(candles)
    }
    target_index = index_by_date.get(target_date)
    if target_index is None or target_index == 0:
        return None, market_id

    target_candle = candles[target_index]
    previous_candle = candles[target_index - 1]
    trend_probability = _coerce_probability(market.get("trend_probability"))
    analog_probability = _coerce_probability(market.get("analog_probability"))
    ensemble_probability = _coerce_probability(market.get("up_probability"))
    actual_direction = _actual_direction(previous_candle.close, target_candle.close)
    ensemble_direction = _direction_from_probability(ensemble_probability)
    entry = {
        "forecast_file": _display_forecast_path(forecast_file),
        "forecast_source_generated_at": source_generated_at,
        "market": market_id,
        "target_session_date": target_date,
        "trend_probability": trend_probability,
        "trend_direction": _direction_from_probability(trend_probability),
        "analog_probability": analog_probability,
        "analog_direction": _direction_from_probability(analog_probability),
        "ensemble_probability": ensemble_probability,
        "trend_brier_contribution": _brier_contribution(trend_probability, actual_direction),
        "analog_brier_contribution": _brier_contribution(analog_probability, actual_direction),
        "ensemble_brier_contribution": _brier_contribution(ensemble_probability, actual_direction),
        "forecast_support": _coerce_probability(market.get("forecast_support")),
        "ensemble_direction": ensemble_direction,
        "actual_direction": actual_direction,
        "ensemble_correct": (
            None if actual_direction == "flat" or ensemble_direction is None
            else ensemble_direction == actual_direction
        ),
        "predicted_range_low": market.get("range_low"),
        "predicted_range_high": market.get("range_high"),
        "actual_close": target_candle.close,
        "actual_in_predicted_range": (
            isinstance(market.get("range_low"), (int, float))
            and isinstance(market.get("range_high"), (int, float))
            and float(market["range_low"]) <= target_candle.close <= float(market["range_high"])
        ),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return entry, None


def score_prospective_forecasts(
    prospective_dir: Path = PROSPECTIVE_DIR,
    history_path: Path = HISTORY_PATH,
    histories: dict[str, list[market_data.Candle]] | None = None,
) -> dict[str, int]:
    if history_path.exists():
        history = _load_json(history_path)
        if not isinstance(history, list):
            raise ValueError(f"History must be a JSON list: {history_path}")
    else:
        history = []

    existing = {
        (
            record.get("forecast_file"),
            record.get("forecast_source_generated_at"),
            record.get("market"),
            record.get("target_session_date"),
        )
        for record in history
        if isinstance(record, dict)
    }

    market_histories = histories or {
        market_id: market_data.fetch_history(symbol)
        for market_id, symbol in market_data.SYMBOLS.items()
    }

    added = 0
    waiting = 0
    processed = 0
    for forecast_file in sorted(prospective_dir.glob("*.json")):
        payload = _load_json(forecast_file)
        source_generated_at = payload.get("source_generated_at")
        markets = payload.get("forecast", {}).get("markets", [])
        if not isinstance(source_generated_at, str) or not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            processed += 1
            market_id = market.get("id")
            candles = market_histories.get(market_id)
            if candles is None:
                continue
            scored, waiting_market = _score_market(
                forecast_file, source_generated_at, market, candles
            )
            if waiting_market is not None:
                waiting += 1
                continue
            if scored is None:
                continue
            key = (
                scored["forecast_file"],
                scored["forecast_source_generated_at"],
                scored["market"],
                scored["target_session_date"],
            )
            if key in existing:
                continue
            history.append(scored)
            existing.add(key)
            added += 1

    if added:
        _write_json(history_path, history)

    return {
        "processed": processed,
        "added": added,
        "waiting": waiting,
        "history_size": len(history),
    }


def main() -> None:
    summary = score_prospective_forecasts()
    print(
        "Scored prospective forecasts: "
        f"processed={summary['processed']}, "
        f"added={summary['added']}, "
        f"waiting={summary['waiting']}, "
        f"history_size={summary['history_size']}"
    )


if __name__ == "__main__":
    main()

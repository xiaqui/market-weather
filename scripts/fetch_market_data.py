#!/usr/bin/env python3
"""Build a transparent next-session forecast from Yahoo daily candles."""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FORECAST_PATH = ROOT / "shared" / "forecast.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=1y"
SYMBOLS = {
    "nikkei": "^N225",
    "dow": "^DJI",
    "usdjpy": "JPY=X",
    "gold": "GC=F",
}

# The first baseline deliberately has few, documented knobs.  Direction is a
# weighted blend of returns and moving-average deviations, expressed in units
# of recent volatility.  tanh and this scale keep probabilities away from 0/1.
SIGNAL_WEIGHTS = (0.10, 0.20, 0.25, 0.15, 0.30)
PROBABILITY_SPREAD = 0.32
SIGNAL_CLIP = 3.0
RANGE_VOLATILITY_MULTIPLIER = 1.28  # roughly an 80% one-day normal interval
MINIMUM_DAILY_VOLATILITY = 0.002
MINIMUM_HISTORY = 21
FULL_CONFIDENCE_HISTORY = 60


@dataclass(frozen=True)
class Candle:
    """One real Yahoo daily observation; absent OHLC rows are not fabricated."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@dataclass(frozen=True)
class Features:
    return_1d: float
    return_5d: float
    return_20d: float
    ma_deviation_5d: float
    ma_deviation_20d: float
    volatility_5d: float
    volatility_20d: float


@dataclass(frozen=True)
class MarketSnapshot:
    """Completed daily candles plus Yahoo's latest tradable price."""

    candles: list[Candle]
    current: float


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def parse_history(
    payload: dict[str, Any], symbol: str, now_timestamp: float | None = None
) -> list[Candle]:
    """Parse only complete OHLC observations from a Yahoo Chart response."""
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote_data = result["indicators"]["quote"][0]
        opens, highs = quote_data["open"], quote_data["high"]
        lows, closes = quote_data["low"], quote_data["close"]
        volumes = quote_data.get("volume", [None] * len(timestamps))
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"No daily history returned for {symbol}") from error

    candles: list[Candle] = []
    for index, raw_timestamp in enumerate(timestamps):
        try:
            values = [_finite_number(items[index]) for items in (opens, highs, lows, closes)]
            volume = _finite_number(volumes[index]) if index < len(volumes) else None
        except (IndexError, TypeError):
            continue
        timestamp = _finite_number(raw_timestamp)
        if timestamp is None or any(value is None or value <= 0 for value in values):
            continue
        open_value, high, low, close = values
        if high < max(open_value, close) or low > min(open_value, close):
            continue
        candles.append(Candle(int(timestamp), open_value, high, low, close, volume))

    candles.sort(key=lambda candle: candle.timestamp)

    # Yahoo includes the currently forming interval in daily chart responses.
    # Its timestamp falls inside the current regular session.  Keep it out of
    # all features and backtests until that session has ended; the live value
    # remains available separately through meta.regularMarketPrice.
    now = time.time() if now_timestamp is None else now_timestamp
    try:
        regular_session = result["meta"]["currentTradingPeriod"]["regular"]
        session_start = float(regular_session["start"])
        session_end = float(regular_session["end"])
    except (KeyError, TypeError, ValueError):
        session_start = session_end = 0.0
    if session_start <= now < session_end:
        candles = [
            candle
            for candle in candles
            if not session_start <= candle.timestamp < session_end
        ]
    if len(candles) < MINIMUM_HISTORY:
        raise ValueError(
            f"Insufficient daily history for {symbol}: {len(candles)} "
            f"(need {MINIMUM_HISTORY})"
        )
    return candles


def fetch_market(symbol: str) -> MarketSnapshot:
    """Fetch completed daily history and the latest price from Yahoo Finance."""
    request = Request(
        YAHOO_CHART_URL.format(quote(symbol, safe="")),
        headers={"User-Agent": "market-weather/0.2"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    candles = parse_history(payload, symbol)
    try:
        current = _finite_number(payload["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"No current price returned for {symbol}") from error
    if current is None or current <= 0:
        raise ValueError(f"Invalid current price returned for {symbol}")
    return MarketSnapshot(candles, current)


def fetch_history(symbol: str) -> list[Candle]:
    """Compatibility helper returning completed daily observations."""
    return fetch_market(symbol).candles


def fetch_price(symbol: str) -> float:
    """Compatibility helper returning Yahoo's latest regular-market price."""
    return fetch_market(symbol).current


def calculate_features(candles: list[Candle]) -> Features:
    """Calculate features using only observations supplied through the endpoint."""
    if len(candles) < MINIMUM_HISTORY:
        raise ValueError(f"At least {MINIMUM_HISTORY} candles are required")
    closes = [candle.close for candle in candles]
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    current = closes[-1]
    return Features(
        return_1d=current / closes[-2] - 1,
        return_5d=current / closes[-6] - 1,
        return_20d=current / closes[-21] - 1,
        ma_deviation_5d=current / statistics.fmean(closes[-5:]) - 1,
        ma_deviation_20d=current / statistics.fmean(closes[-20:]) - 1,
        volatility_5d=statistics.pstdev(returns[-5:]),
        volatility_20d=statistics.pstdev(returns[-20:]),
    )


def weather_for_probability(probability: float) -> str:
    if probability >= 0.62:
        return "sunny"
    if probability >= 0.54:
        return "partly_cloudy"
    if probability > 0.46:
        return "cloudy"
    return "rainy"


def risk_for_volatility(volatility: float) -> str:
    if volatility < 0.008:
        return "calm"
    if volatility < 0.015:
        return "normal"
    if volatility < 0.025:
        return "caution"
    return "storm"


def build_prediction(
    candles: list[Candle], current_price: float | None = None
) -> dict[str, float | str]:
    """Create the baseline prediction from past and current candles only."""
    features = calculate_features(candles)
    volatility_5d = max(features.volatility_5d, MINIMUM_DAILY_VOLATILITY)
    volatility_20d = max(features.volatility_20d, MINIMUM_DAILY_VOLATILITY)
    signals = (
        features.return_1d / volatility_5d,
        features.return_5d / (volatility_5d * math.sqrt(5)),
        features.return_20d / (volatility_20d * math.sqrt(20)),
        features.ma_deviation_5d / volatility_5d,
        features.ma_deviation_20d / volatility_20d,
    )
    score = sum(weight * max(-SIGNAL_CLIP, min(SIGNAL_CLIP, signal)) for weight, signal in zip(SIGNAL_WEIGHTS, signals))
    probability = 0.5 + PROBABILITY_SPREAD * math.tanh(score)

    nonzero_signs = [math.copysign(1, signal) for signal in signals if signal != 0]
    agreement = abs(sum(nonzero_signs)) / len(nonzero_signs) if nonzero_signs else 0.0
    sufficiency = min(1.0, len(candles) / FULL_CONFIDENCE_HISTORY)
    confidence = sufficiency * (0.5 + 0.5 * agreement)

    current = candles[-1].close if current_price is None else current_price
    range_factor = max(features.volatility_20d, MINIMUM_DAILY_VOLATILITY) * RANGE_VOLATILITY_MULTIPLIER
    low, high = current * math.exp(-range_factor), current * math.exp(range_factor)
    return {
        "current": current,
        "up_probability": round(probability, 4),
        "range_low": round(low, 4),
        "range_high": round(high, 4),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "weather": weather_for_probability(probability),
        "risk": risk_for_volatility(features.volatility_20d),
    }


def backtest(candles: list[Candle]) -> tuple[int, int, float]:
    """Walk forward, predicting each next row without exposing it to the model."""
    correct = 0
    samples = 0
    for next_index in range(MINIMUM_HISTORY, len(candles)):
        history = candles[:next_index]
        prediction = build_prediction(history)
        predicted_up = prediction["up_probability"] >= 0.5
        actual_up = candles[next_index].close > candles[next_index - 1].close
        correct += predicted_up == actual_up
        samples += 1
    return correct, samples, correct / samples if samples else 0.0


def update_forecast(path: Path = FORECAST_PATH) -> dict[str, dict[str, float | str]]:
    """Fetch all markets successfully before atomically replacing the forecast."""
    snapshots = {market_id: fetch_market(symbol) for market_id, symbol in SYMBOLS.items()}
    predictions = {
        market_id: build_prediction(snapshot.candles, snapshot.current)
        for market_id, snapshot in snapshots.items()
    }
    _write_forecast(path, predictions)
    return predictions


def _write_forecast(path: Path, predictions: dict[str, dict[str, float | str]]) -> None:
    forecast = json.loads(path.read_text(encoding="utf-8"))
    markets = {market["id"]: market for market in forecast["markets"]}
    missing = SYMBOLS.keys() - markets.keys()
    if missing:
        raise ValueError(f"Markets missing from forecast: {', '.join(sorted(missing))}")

    for market_id, prediction in predictions.items():
        markets[market_id].update(prediction)
    forecast["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(forecast, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    snapshots = {market_id: fetch_market(symbol) for market_id, symbol in SYMBOLS.items()}
    predictions = {
        market_id: build_prediction(snapshot.candles, snapshot.current)
        for market_id, snapshot in snapshots.items()
    }
    # Reuse already fetched data: production runs must not silently mix snapshots.
    _write_forecast(FORECAST_PATH, predictions)

    for market_id, prediction in predictions.items():
        correct, samples, accuracy = backtest(snapshots[market_id].candles)
        print(f"{market_id}: {json.dumps(prediction, ensure_ascii=False)}")
        print(f"  backtest: {accuracy:.1%} ({correct}/{samples})")
    print(f"Updated {FORECAST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

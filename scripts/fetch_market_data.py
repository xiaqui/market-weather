#!/usr/bin/env python3
"""Build a transparent next-session forecast from Yahoo daily candles."""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
import time
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
FORECAST_PATH = ROOT / "shared" / "forecast.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=10y"
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
ANALOG_K = 30
MIN_ANALOGS = 15
ANALOG_WEIGHT = 0.5
DISTANCE_EPSILON = 0.25
MAX_ANALOG_WEIGHT = 4.0
BACKTEST_SESSIONS = 252
MAX_STALENESS_HOURS = 168.0
EXTERNAL_RETURN_CLIP = 0.30
MARKET_ORDER = tuple(SYMBOLS)
BASE_STATE_NAMES = ("n1", "n5", "n20", "n_ma20", "vol_ratio")
PAIR_NAMES = tuple(
    f"{left}_minus_{right}_n5"
    for index, left in enumerate(MARKET_ORDER)
    for right in MARKET_ORDER[index + 1 :]
)
WEATHER_MAP_FEATURE_NAMES = tuple(
    f"{market}_{feature}" for market in MARKET_ORDER for feature in BASE_STATE_NAMES
) + PAIR_NAMES
CONTEXT_FEATURE_COUNT = 4
SUPPORTED_NEXT_SESSION_START_YEAR = 2016
SUPPORTED_NEXT_SESSION_END_YEAR = 2099


def weather_map_feature_names(target_market: str) -> tuple[str, ...]:
    return WEATHER_MAP_FEATURE_NAMES + (
        f"{target_market}_hours_since_close",
        *(
            f"{market}_return_since_{target_market}_close"
            for market in MARKET_ORDER
            if market != target_market
        ),
    )


@dataclass(frozen=True)
class MarketHours:
    timezone_name: str
    normal_close: datetime_time
    date_from_utc: bool = False


MARKET_HOURS = {
    "^N225": MarketHours("Asia/Tokyo", datetime_time(15, 30)),
    "^DJI": MarketHours("America/New_York", datetime_time(16, 0)),
    "JPY=X": MarketHours("America/New_York", datetime_time(17, 0), True),
    "GC=F": MarketHours("America/New_York", datetime_time(17, 0), True),
}


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


@dataclass(frozen=True)
class WeatherMapState:
    """Cross-market information that was available at one UTC instant."""

    timestamp: int
    vector: tuple[float, ...]
    target_close_timestamp: int = 0


@dataclass(frozen=True)
class AnalogResult:
    probability: float
    count: int
    mean_distance: float
    mean_next_return: float
    nearest: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class BacktestRecord:
    timestamp: int
    trend_probability: float
    analog_probability: float | None
    ensemble_probability: float
    actual_up: bool
    analog_count: int
    analog_mean_distance: float | None
    historical_up_probability: float = 0.5


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _fourth_thursday_of_november(year: int) -> date:
    day = date(year, 11, 1)
    return day + timedelta(days=(3 - day.weekday()) % 7 + 21)


def _is_us_early_close(session_date: date) -> bool:
    """Known recurring US cash/futures shortened sessions, not today's hours."""
    thanksgiving = _fourth_thursday_of_november(session_date.year)
    if session_date == thanksgiving + timedelta(days=1):
        return True
    if session_date.month == 7 and session_date.day == 3 and session_date.weekday() < 5:
        return True
    return (
        session_date.month == 12
        and session_date.day == 24
        and session_date.weekday() < 5
    )


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(
        days=(weekday - first.weekday()) % 7 + 7 * (occurrence - 1)
    )


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    return current - timedelta(days=(current.weekday() - weekday) % 7)


def _observed_us_holiday(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _easter_sunday(year: int) -> date:
    century = year // 100
    year_in_century = year % 100
    leap_century = century // 4
    century_remainder = century % 4
    correction = (century + 8) // 25
    adjustment = (century - correction + 1) // 3
    epact = (19 * (year % 19) + century - leap_century - adjustment + 15) % 30
    leap_years = year_in_century // 4
    remainder = year_in_century % 4
    weekday_offset = (32 + 2 * century_remainder + 2 * leap_years - epact - remainder) % 7
    moon = (year % 19 + 11 * epact + 22 * weekday_offset) // 451
    month = (epact + weekday_offset - 7 * moon + 114) // 31
    day = (epact + weekday_offset - 7 * moon + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def _us_market_holidays(year: int) -> frozenset[date]:
    """Full-day US cash-equity closures used by the Dow."""
    holidays = {
        _observed_us_holiday(date(year, 1, 1)),
        _nth_weekday_of_month(year, 1, 0, 3),  # MLK Day
        _nth_weekday_of_month(year, 2, 0, 3),  # Presidents Day
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday_of_month(year, 5, 0),  # Memorial Day
        _observed_us_holiday(date(year, 6, 19)),  # Juneteenth
        _observed_us_holiday(date(year, 7, 4)),
        _nth_weekday_of_month(year, 9, 0, 1),  # Labor Day
        _nth_weekday_of_month(year, 11, 3, 4),  # Thanksgiving
        _observed_us_holiday(date(year, 12, 25)),
    }
    observed_next_new_year = _observed_us_holiday(date(year + 1, 1, 1))
    if observed_next_new_year.year == year:
        holidays.add(observed_next_new_year)
    return frozenset(holidays)


@lru_cache(maxsize=None)
def _gold_futures_full_closures(year: int) -> frozenset[date]:
    """Conservative full-day closures for COMEX Gold, not NYSE holidays.

    Many US federal holidays have a shortened Globex metals session and still
    produce a daily bar. Treating every NYSE holiday as closed would therefore
    skip valid Gold forecast targets.
    """
    holidays = {
        _observed_us_holiday(date(year, 1, 1)),
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _observed_us_holiday(date(year, 12, 25)),
    }
    observed_next_new_year = _observed_us_holiday(date(year + 1, 1, 1))
    if observed_next_new_year.year == year:
        holidays.add(observed_next_new_year)
    return frozenset(holidays)


def _vernal_equinox_day(year: int) -> int:
    return int(20.8431 + 0.242194 * (year - 1980) - (year - 1980) // 4)


def _autumnal_equinox_day(year: int) -> int:
    return int(23.2488 + 0.242194 * (year - 1980) - (year - 1980) // 4)


@lru_cache(maxsize=None)
def _japan_market_holidays(year: int) -> frozenset[date]:
    if not SUPPORTED_NEXT_SESSION_START_YEAR <= year <= SUPPORTED_NEXT_SESSION_END_YEAR:
        raise ValueError(
            "Japanese next-session calendar supports years "
            f"{SUPPORTED_NEXT_SESSION_START_YEAR}-{SUPPORTED_NEXT_SESSION_END_YEAR}"
        )
    holidays = {
        date(year, 1, 1),
        date(year, 2, 11),
        date(year, 3, _vernal_equinox_day(year)),
        date(year, 4, 29),
        date(year, 5, 3),
        date(year, 5, 4),
        date(year, 5, 5),
        date(year, 9, _autumnal_equinox_day(year)),
        date(year, 11, 3),
        date(year, 11, 23),
    }
    if year >= 2000:
        holidays.add(_nth_weekday_of_month(year, 1, 0, 2))  # Coming of Age Day
    else:
        holidays.add(date(year, 1, 15))
    if year >= 2003:
        holidays.add(_nth_weekday_of_month(year, 9, 0, 3))  # Respect for the Aged Day
    else:
        holidays.add(date(year, 9, 15))
    if year == 2020:
        holidays.update({
            date(year, 7, 23),  # Marine Day
            date(year, 7, 24),  # Sports Day
            date(year, 8, 10),  # Mountain Day
        })
    elif year == 2021:
        holidays.update({
            date(year, 7, 22),  # Marine Day
            date(year, 7, 23),  # Sports Day
            date(year, 8, 8),   # Mountain Day
        })
    else:
        if year >= 2003:
            holidays.add(_nth_weekday_of_month(year, 7, 0, 3))  # Marine Day
        elif year >= 1996:
            holidays.add(date(year, 7, 20))
        if year >= 2016:
            holidays.add(date(year, 8, 11))
        if year >= 2000:
            holidays.add(_nth_weekday_of_month(year, 10, 0, 2))  # Sports Day
        else:
            holidays.add(date(year, 10, 10))
    if year >= 2020:
        holidays.add(date(year, 2, 23))
    elif 1989 <= year <= 2018:
        holidays.add(date(year, 12, 23))

    for holiday in sorted(tuple(holidays)):
        if holiday.weekday() != 6:
            continue
        substitute = holiday + timedelta(days=1)
        while substitute.weekday() >= 5 or substitute in holidays:
            substitute += timedelta(days=1)
        holidays.add(substitute)

    start = min(holidays)
    end = max(holidays)
    current = start + timedelta(days=1)
    while current < end:
        if (
            current.weekday() < 5
            and current not in holidays
            and current - timedelta(days=1) in holidays
            and current + timedelta(days=1) in holidays
        ):
            holidays.add(current)
        current += timedelta(days=1)
    return frozenset(holidays)


def _is_market_session_day(symbol: str, session_date: date) -> bool:
    if session_date.weekday() >= 5:
        return False
    if symbol == "^N225":
        if (session_date.month, session_date.day) in {(1, 2), (1, 3), (12, 31)}:
            return False
        return session_date not in _japan_market_holidays(session_date.year)
    if symbol == "^DJI":
        return session_date not in _us_market_holidays(session_date.year)
    if symbol == "JPY=X":
        # Spot FX is a global 24/5 market. US cash-equity holidays are not
        # full-session closures, so weekdays remain valid forecast targets.
        return True
    if symbol == "GC=F":
        return session_date not in _gold_futures_full_closures(session_date.year)
    return True


def session_close_timestamp(symbol: str, raw_timestamp: int) -> int:
    """Map a Yahoo daily label to that session's conservative calendar close."""
    hours = MARKET_HOURS.get(symbol)
    if hours is None:
        return raw_timestamp
    zone = ZoneInfo(hours.timezone_name)
    label_zone = timezone.utc if hours.date_from_utc else zone
    session_date = datetime.fromtimestamp(raw_timestamp, label_zone).date()
    close_time = hours.normal_close
    if symbol == "^N225" and session_date < date(2024, 11, 5):
        close_time = datetime_time(15, 0)
    elif symbol == "^DJI" and _is_us_early_close(session_date):
        close_time = datetime_time(13, 0)
    elif symbol == "GC=F" and _is_us_early_close(session_date):
        close_time = datetime_time(13, 30)
    return int(datetime.combine(session_date, close_time, tzinfo=zone).timestamp())


def last_data_date(symbol: str, candles: list[Candle]) -> str:
    """Return the market-local trading date of the latest completed input candle."""
    hours = MARKET_HOURS.get(symbol)
    zone = ZoneInfo(hours.timezone_name) if hours is not None else timezone.utc
    return datetime.fromtimestamp(candles[-1].timestamp, zone).date().isoformat()


def next_session_date(symbol: str, candles: list[Candle]) -> str:
    """Return the next real market session date after the latest completed candle."""
    hours = MARKET_HOURS.get(symbol)
    zone = ZoneInfo(hours.timezone_name) if hours is not None else timezone.utc
    session_date = datetime.fromtimestamp(candles[-1].timestamp, zone).date()
    if (
        symbol == "^N225"
        and not SUPPORTED_NEXT_SESSION_START_YEAR
        <= session_date.year
        <= SUPPORTED_NEXT_SESSION_END_YEAR
    ):
        raise ValueError(
            "Japanese next-session calendar supports years "
            f"{SUPPORTED_NEXT_SESSION_START_YEAR}-{SUPPORTED_NEXT_SESSION_END_YEAR}"
        )
    while True:
        session_date += timedelta(days=1)
        if _is_market_session_day(symbol, session_date):
            return session_date.isoformat()


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

    # Derive availability for every historical row from its own session date.
    # Never reuse today's currentTradingPeriod close across ten years: that
    # leaks ordinary US closes when today happens to be a half day.
    if symbol in MARKET_HOURS:
        candles = [
            Candle(
                session_close_timestamp(symbol, candle.timestamp),
                candle.open, candle.high, candle.low, candle.close, candle.volume,
            )
            for candle in candles
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
    # Every feature has a 20-session horizon. Keeping only the required tail
    # makes 10-year walk-forward state construction linear rather than
    # repeatedly copying the full prefix.
    closes = [candle.close for candle in candles[-MINIMUM_HISTORY:]]
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
        "trend_probability": round(probability, 4),
        "up_probability": round(probability, 4),
        "range_low": round(low, 4),
        "range_high": round(high, 4),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "weather": weather_for_probability(probability),
        "risk": risk_for_volatility(features.volatility_20d),
    }


def _asof_history(candles: list[Candle], timestamp: int) -> list[Candle]:
    """Return only rows whose completed-candle timestamp is available by UTC time."""
    end = bisect_right([candle.timestamp for candle in candles], timestamp)
    return candles[max(0, end - MINIMUM_HISTORY) : end]


def _asof_candle(candles: list[Candle], timestamp: int) -> Candle | None:
    end = bisect_right([candle.timestamp for candle in candles], timestamp)
    return candles[end - 1] if end else None


def build_weather_map_vector(histories: dict[str, list[Candle]]) -> tuple[float, ...]:
    """Build 20 per-market and six relative, scale-free weather-map features."""
    missing = set(MARKET_ORDER) - histories.keys()
    if missing:
        raise ValueError(f"Markets missing from weather map: {', '.join(sorted(missing))}")
    per_market: dict[str, tuple[float, ...]] = {}
    for market in MARKET_ORDER:
        features = calculate_features(histories[market])
        vol5 = max(features.volatility_5d, MINIMUM_DAILY_VOLATILITY)
        vol20 = max(features.volatility_20d, MINIMUM_DAILY_VOLATILITY)
        directional = (
            features.return_1d / vol5,
            features.return_5d / (vol5 * math.sqrt(5)),
            features.return_20d / (vol20 * math.sqrt(20)),
            features.ma_deviation_20d / vol20,
        )
        per_market[market] = tuple(
            max(-SIGNAL_CLIP, min(SIGNAL_CLIP, value)) for value in directional
        ) + (max(0.0, min(SIGNAL_CLIP, vol5 / vol20)),)
    vector = tuple(value for market in MARKET_ORDER for value in per_market[market])
    relative = tuple(
        per_market[left][1] - per_market[right][1]
        for index, left in enumerate(MARKET_ORDER)
        for right in MARKET_ORDER[index + 1 :]
    )
    return vector + relative


def weather_map_at(
    histories: dict[str, list[Candle]], timestamp: int, target_market: str
) -> WeatherMapState | None:
    """Build one target-specific state using only data available at its clock."""
    available = {market: _asof_history(rows, timestamp) for market, rows in histories.items()}
    if any(len(available.get(market, [])) < MINIMUM_HISTORY for market in MARKET_ORDER):
        return None
    target_close = available[target_market][-1]
    staleness = min(
        MAX_STALENESS_HOURS,
        max(0.0, (timestamp - target_close.timestamp) / 3600),
    )
    external_moves = []
    for market in MARKET_ORDER:
        if market == target_market:
            continue
        latest = available[market][-1]
        at_target_close = _asof_candle(histories[market], target_close.timestamp)
        if at_target_close is None:
            return None
        move = latest.close / at_target_close.close - 1
        external_moves.append(max(-EXTERNAL_RETURN_CLIP, min(EXTERNAL_RETURN_CLIP, move)))
    context = (staleness, *external_moves)
    return WeatherMapState(
        timestamp,
        build_weather_map_vector(available) + context,
        target_close.timestamp,
    )


def snapshot_clock(
    histories: dict[str, list[Candle]], target_market: str, next_close: int | None = None,
    global_timestamps: list[int] | None = None,
) -> int:
    """Latest global completed close, optionally strictly before a target outcome."""
    timestamps = global_timestamps or sorted({
        candle.timestamp for rows in histories.values() for candle in rows
    })
    end = len(timestamps) if next_close is None else bisect_right(timestamps, next_close - 1)
    if end == 0:
        raise ValueError(f"No completed data available for {target_market}")
    return timestamps[end - 1]


def _standardized_distances(
    query: tuple[float, ...], candidates: list[tuple[WeatherMapState, float]]
) -> list[tuple[float, WeatherMapState, float]]:
    """Standardize with candidate history only, then return RMS Euclidean distance."""
    count = len(candidates)
    sums = [0.0] * len(query)
    squared_sums = [0.0] * len(query)
    for state, _ in candidates:
        for index, value in enumerate(state.vector):
            sums[index] += value
            squared_sums[index] += value * value
    means = [value / count for value in sums]
    deviations = [
        math.sqrt(max(0.0, squared_sums[index] / count - means[index] ** 2))
        for index in range(len(query))
    ]
    scales = [deviation if deviation > 1e-12 else 1.0 for deviation in deviations]
    result = []
    for state, next_return in candidates:
        squared = sum(
            ((query[i] - state.vector[i]) / scales[i]) ** 2
            for i in range(len(query))
        )
        result.append((math.sqrt(squared / len(query)), state, next_return))
    return sorted(result, key=lambda item: item[0])


def find_analogs(
    current: WeatherMapState,
    historical_states: list[WeatherMapState],
    target_candles: list[Candle],
) -> AnalogResult | None:
    """Find completed historical outcomes available strictly before/currently at query."""
    target_timestamps = [candle.timestamp for candle in target_candles]
    candidates: list[tuple[WeatherMapState, float]] = []
    for state in historical_states:
        if state.timestamp >= current.timestamp:
            continue
        base_index = bisect_right(target_timestamps, state.timestamp) - 1
        next_index = base_index + 1
        if base_index < 0 or next_index >= len(target_candles):
            continue
        # Knowing this outcome at the query instant is mandatory. This also
        # prevents adjacent candidates from leaking their next close.
        if target_candles[next_index].timestamp > current.timestamp:
            continue
        next_return = target_candles[next_index].close / target_candles[base_index].close - 1
        candidates.append((state, next_return))
    if len(candidates) < MIN_ANALOGS:
        return None
    nearest = _standardized_distances(current.vector, candidates)[:ANALOG_K]
    weights = [min(MAX_ANALOG_WEIGHT, 1 / (distance + DISTANCE_EPSILON)) for distance, _, _ in nearest]
    weight_sum = sum(weights)
    probability = sum(weight for weight, (_, _, value) in zip(weights, nearest) if value > 0) / weight_sum
    mean_return = sum(weight * value for weight, (_, _, value) in zip(weights, nearest)) / weight_sum
    return AnalogResult(
        probability=max(0.0, min(1.0, probability)),
        count=len(nearest),
        mean_distance=statistics.fmean(item[0] for item in nearest),
        mean_next_return=mean_return,
        nearest=tuple((item[1].timestamp, item[0]) for item in nearest[:3]),
    )


def _historical_states(
    histories: dict[str, list[Candle]], target_market: str
) -> list[WeatherMapState]:
    states = []
    target = histories[target_market]
    global_timestamps = sorted({
        candle.timestamp for rows in histories.values() for candle in rows
    })
    for next_index in range(1, len(target)):
        timestamp = snapshot_clock(
            histories, target_market, target[next_index].timestamp, global_timestamps
        )
        if timestamp < target[next_index - 1].timestamp:
            continue
        state = weather_map_at(histories, timestamp, target_market)
        if state is not None:
            states.append(state)
    return states


def build_cross_asset_predictions(
    snapshots: dict[str, MarketSnapshot]
) -> tuple[dict[str, dict[str, float | str | int | None]], dict[str, list[WeatherMapState]]]:
    """Combine unchanged Trend forecasts with leak-safe cross-asset analogs."""
    histories = {market: snapshot.candles for market, snapshot in snapshots.items()}
    predictions = {}
    state_sets = {}
    for market in MARKET_ORDER:
        snapshot = snapshots[market]
        prediction = build_prediction(snapshot.candles, snapshot.current)
        prediction["last_data_date"] = last_data_date(SYMBOLS[market], snapshot.candles)
        prediction["next_session_date"] = next_session_date(
            SYMBOLS[market], snapshot.candles
        )
        query_timestamp = snapshot_clock(histories, market)
        query = weather_map_at(histories, query_timestamp, market)
        if query is None:
            raise ValueError(f"Insufficient aligned history for {market} weather map")
        states = _historical_states(histories, market)
        state_sets[market] = states
        analog = find_analogs(query, states, snapshot.candles)
        trend = float(prediction["trend_probability"])
        if analog is None:
            final = trend
            prediction.update({
                "analog_probability": None, "analog_count": 0,
                "analog_mean_distance": None, "analog_mean_next_return": None,
            })
        else:
            final = (1 - ANALOG_WEIGHT) * trend + ANALOG_WEIGHT * analog.probability
            prediction.update({
                "analog_probability": round(analog.probability, 4),
                "analog_count": analog.count,
                "analog_mean_distance": round(analog.mean_distance, 4),
                "analog_mean_next_return": round(analog.mean_next_return, 6),
            })
        prediction["up_probability"] = round(max(0.0, min(1.0, final)), 4)
        prediction["weather"] = weather_for_probability(final)
        predictions[market] = prediction
    return predictions, state_sets


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


def walk_forward_records(
    histories: dict[str, list[Candle]], market: str,
    sessions: int = BACKTEST_SESSIONS,
) -> list[BacktestRecord]:
    """Return leak-safe per-session forecasts for evaluation and diagnostics."""
    target = histories[market]
    states = _historical_states(histories, market)
    global_timestamps = sorted({
        candle.timestamp for rows in histories.values() for candle in rows
    })
    cumulative_up = [0]
    for index in range(1, len(target)):
        cumulative_up.append(
            cumulative_up[-1] + (target[index].close > target[index - 1].close)
        )
    records = []
    # Report the latest trading year while retaining the full preceding
    # decade as the expanding analog candidate set.
    start = max(MINIMUM_HISTORY, len(target) - sessions)
    for next_index in range(start, len(target)):
        history = target[:next_index]
        clock = snapshot_clock(
            histories, market, target[next_index].timestamp, global_timestamps
        )
        current = weather_map_at(histories, clock, market)
        if current is None:
            continue
        trend = float(build_prediction(history)["trend_probability"])
        analog = find_analogs(current, states, target)
        actual_up = target[next_index].close > target[next_index - 1].close
        historical_up_probability = (
            cumulative_up[next_index - 1] / (next_index - 1)
            if next_index > 1 else 0.5
        )
        if analog is None:
            ensemble = trend
            analog_probability = None
            analog_count = 0
            analog_mean_distance = None
        else:
            analog_probability = analog.probability
            analog_count = analog.count
            analog_mean_distance = analog.mean_distance
            ensemble = (1 - ANALOG_WEIGHT) * trend + ANALOG_WEIGHT * analog.probability
        records.append(BacktestRecord(
            timestamp=target[next_index].timestamp,
            trend_probability=trend,
            analog_probability=analog_probability,
            ensemble_probability=ensemble,
            actual_up=actual_up,
            analog_count=analog_count,
            analog_mean_distance=analog_mean_distance,
            historical_up_probability=historical_up_probability,
        ))
    return records


def _accuracy(records: list[BacktestRecord], field: str) -> float:
    if not records:
        return 0.0
    return sum((getattr(record, field) >= 0.5) == record.actual_up for record in records) / len(records)


def _correct_count(records: list[BacktestRecord], field: str) -> int:
    return sum((getattr(record, field) >= 0.5) == record.actual_up for record in records)


def summarize_backtest_records(records: list[BacktestRecord]) -> dict[str, float | int]:
    analog_records = [record for record in records if record.analog_probability is not None]
    trend_correct = _correct_count(records, "trend_probability")
    analog_correct = _correct_count(analog_records, "analog_probability")
    ensemble_correct = _correct_count(records, "ensemble_probability")
    return {
        "trend_correct": trend_correct,
        "trend_samples": len(records),
        "trend_accuracy": trend_correct / len(records) if records else 0.0,
        "analog_correct": analog_correct,
        "analog_samples": len(analog_records),
        "analog_accuracy": analog_correct / len(analog_records) if analog_records else 0.0,
        "ensemble_correct": ensemble_correct,
        "ensemble_samples": len(records),
        "ensemble_accuracy": ensemble_correct / len(records) if records else 0.0,
    }


def cross_asset_backtest(
    histories: dict[str, list[Candle]], market: str
) -> dict[str, float | int]:
    """Summarize the same walk-forward records used by diagnostics."""
    return summarize_backtest_records(walk_forward_records(histories, market))


def combined_strength(record: BacktestRecord) -> float | None:
    if record.analog_probability is None:
        return None
    return abs(record.trend_probability - 0.5) + abs(record.analog_probability - 0.5)


def strength_bin(strength: float) -> str:
    if strength < 0.10:
        return "weak"
    if strength < 0.25:
        return "medium"
    return "strong"


def direction_group(record: BacktestRecord) -> str | None:
    if record.analog_probability is None:
        return None
    trend = "up" if record.trend_probability >= 0.5 else "down"
    analog = "up" if record.analog_probability >= 0.5 else "down"
    return f"trend_{trend}_analog_{analog}"


def brier_score(records: list[BacktestRecord], field: str) -> float | None:
    available = [record for record in records if getattr(record, field) is not None]
    if not available:
        return None
    return statistics.fmean(
        (getattr(record, field) - float(record.actual_up)) ** 2
        for record in available
    )


def _diagnostic_metrics(records: list[BacktestRecord]) -> dict[str, float | int]:
    if not records:
        return {
            "sample_count": 0, "actual_up_rate": 0.0,
            "trend_accuracy": 0.0, "analog_accuracy": 0.0,
            "ensemble_accuracy": 0.0,
        }
    return {
        "sample_count": len(records),
        "actual_up_rate": sum(record.actual_up for record in records) / len(records),
        "trend_accuracy": _accuracy(records, "trend_probability"),
        "analog_accuracy": _accuracy(records, "analog_probability"),
        "ensemble_accuracy": _accuracy(records, "ensemble_probability"),
    }


def build_backtest_diagnostics(records: list[BacktestRecord]) -> dict[str, Any]:
    """Aggregate fixed, non-optimized views without changing forecast behavior."""
    available = [record for record in records if record.analog_probability is not None]
    group_names = (
        "trend_up_analog_up", "trend_up_analog_down",
        "trend_down_analog_up", "trend_down_analog_down",
    )
    direction_groups = {
        name: _diagnostic_metrics([
            record for record in available if direction_group(record) == name
        ])
        for name in group_names
    }
    agreement = [
        record for record in available
        if (record.trend_probability >= 0.5) == (record.analog_probability >= 0.5)
    ]
    disagreement = [record for record in available if record not in agreement]

    strength_groups = {
        name: _diagnostic_metrics([
            record for record in available if strength_bin(combined_strength(record)) == name
        ])
        for name in ("weak", "medium", "strong")
    }
    agreement_strength_groups = {
        name: _diagnostic_metrics([
            record for record in agreement if strength_bin(combined_strength(record)) == name
        ])
        for name in ("weak", "medium", "strong")
    }

    distance_records = sorted(
        (record for record in available if record.analog_mean_distance is not None),
        key=lambda record: record.analog_mean_distance,
    )
    distance_groups: dict[str, dict[str, float | int]] = {}
    for group_index, name in enumerate(("closest", "middle", "farthest")):
        start = len(distance_records) * group_index // 3
        end = len(distance_records) * (group_index + 1) // 3
        group = distance_records[start:end]
        metrics = _diagnostic_metrics(group)
        metrics["mean_distance"] = (
            statistics.fmean(record.analog_mean_distance for record in group)
            if group else 0.0
        )
        distance_groups[name] = metrics

    return {
        "sample_count": len(records),
        "analog_available_count": len(available),
        "analog_unavailable_count": len(records) - len(available),
        "direction_groups": direction_groups,
        "agreement": _diagnostic_metrics(agreement),
        "disagreement": _diagnostic_metrics(disagreement),
        "strength_groups": strength_groups,
        "agreement_strength_groups": agreement_strength_groups,
        "distance_groups": distance_groups,
        "below_k": _diagnostic_metrics([
            record for record in available if record.analog_count < ANALOG_K
        ]),
        "brier": {
            "trend": brier_score(records, "trend_probability"),
            "analog": brier_score(records, "analog_probability"),
            "ensemble": brier_score(records, "ensemble_probability"),
        },
    }


def _format_metrics(metrics: dict[str, float | int]) -> str:
    return (
        f"n={metrics['sample_count']}, actual_up={metrics['actual_up_rate']:.1%}, "
        f"Trend={metrics['trend_accuracy']:.1%}, "
        f"Analog={metrics['analog_accuracy']:.1%}, "
        f"Ensemble={metrics['ensemble_accuracy']:.1%}"
    )


def print_backtest_diagnostics(market: str, diagnostics: dict[str, Any]) -> None:
    print(f"  diagnostics ({market}, analog available {diagnostics['analog_available_count']}/"
          f"{diagnostics['sample_count']}):")
    for name, metrics in diagnostics["direction_groups"].items():
        print(f"    {name}: {_format_metrics(metrics)}")
    print(f"    agreement: {_format_metrics(diagnostics['agreement'])}")
    print(f"    disagreement: {_format_metrics(diagnostics['disagreement'])}")
    for name, metrics in diagnostics["strength_groups"].items():
        print(f"    strength_{name}: {_format_metrics(metrics)}")
    for name, metrics in diagnostics["agreement_strength_groups"].items():
        print(f"    agreement_strength_{name}: {_format_metrics(metrics)}")
    for name, metrics in diagnostics["distance_groups"].items():
        print(f"    distance_{name} (mean={metrics['mean_distance']:.4f}): "
              f"{_format_metrics(metrics)}")
    print(f"    analog_count_below_{ANALOG_K}: {_format_metrics(diagnostics['below_k'])}")
    brier = diagnostics["brier"]
    formatted_brier = {
        name: f"{value:.4f}" if value is not None else "n/a"
        for name, value in brier.items()
    }
    print(f"    Brier: Trend={formatted_brier['trend']}, "
          f"Analog={formatted_brier['analog']}, Ensemble={formatted_brier['ensemble']}")


def update_forecast(path: Path = FORECAST_PATH) -> dict[str, dict[str, float | str | int | None]]:
    """Fetch all markets successfully before atomically replacing the forecast."""
    snapshots = {market_id: fetch_market(symbol) for market_id, symbol in SYMBOLS.items()}
    predictions, _ = build_cross_asset_predictions(snapshots)
    _write_forecast(path, predictions)
    return predictions


def _write_forecast(
    path: Path, predictions: dict[str, dict[str, float | str | int | None]]
) -> None:
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
    predictions, _ = build_cross_asset_predictions(snapshots)
    # Reuse already fetched data: production runs must not silently mix snapshots.
    _write_forecast(FORECAST_PATH, predictions)

    histories = {market: snapshot.candles for market, snapshot in snapshots.items()}
    for market_id, prediction in predictions.items():
        records = walk_forward_records(histories, market_id)
        report = summarize_backtest_records(records)
        print(f"{market_id}: {json.dumps(prediction, ensure_ascii=False)}")
        print(
            "  backtest: "
            f"Trend {report['trend_accuracy']:.1%} "
            f"({report['trend_correct']}/{report['trend_samples']}), "
            f"Analog {report['analog_accuracy']:.1%} "
            f"({report['analog_correct']}/{report['analog_samples']}), "
            f"Ensemble {report['ensemble_accuracy']:.1%} "
            f"({report['ensemble_correct']}/{report['ensemble_samples']})"
        )
        print_backtest_diagnostics(market_id, build_backtest_diagnostics(records))
    print(f"Updated {FORECAST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

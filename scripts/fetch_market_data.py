#!/usr/bin/env python3
"""Fetch current market prices and update the canonical forecast file."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
FORECAST_PATH = ROOT / "shared" / "forecast.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=5d"
SYMBOLS = {
    "nikkei": "^N225",
    "dow": "^DJI",
    "usdjpy": "JPY=X",
    "gold": "GC=F",
}


def fetch_price(symbol: str) -> float:
    """Return Yahoo Finance's latest regular-market price for *symbol*."""
    url = YAHOO_CHART_URL.format(quote(symbol, safe=""))
    request = Request(url, headers={"User-Agent": "market-weather/0.1"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)

    try:
        value = payload["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(f"No current price returned for {symbol}") from error
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid current price returned for {symbol}: {value!r}")
    price = float(value)
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"Invalid current price returned for {symbol}: {value!r}")
    return price


def update_forecast(path: Path = FORECAST_PATH) -> dict[str, float]:
    """Fetch every price first, then atomically update current values in *path*."""
    prices = {market_id: fetch_price(symbol) for market_id, symbol in SYMBOLS.items()}
    forecast = json.loads(path.read_text(encoding="utf-8"))
    markets = {market["id"]: market for market in forecast["markets"]}
    missing = SYMBOLS.keys() - markets.keys()
    if missing:
        raise ValueError(f"Markets missing from forecast: {', '.join(sorted(missing))}")

    for market_id, price in prices.items():
        markets[market_id]["current"] = price
    forecast["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
            json.dump(forecast, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return prices


def main() -> None:
    prices = update_forecast()
    for market_id, price in prices.items():
        print(f"{market_id}: {price}")
    print(f"Updated {FORECAST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

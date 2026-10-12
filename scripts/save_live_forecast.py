#!/usr/bin/env python3
"""Save the current forecast as an immutable prospective snapshot."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts import fetch_market_data as market_data


ROOT = Path(__file__).resolve().parents[1]
FORECAST_PATH = ROOT / "shared" / "forecast.json"
PROSPECTIVE_DIR = ROOT / "reports" / "live-forecast"
LOGGER = logging.getLogger(__name__)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_name(generated_at: str) -> str:
    moment = datetime.fromisoformat(generated_at)
    if moment.tzinfo is None:
        raise ValueError("forecast generated_at must include a timezone")
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H-%M-%SZ.json")


def _without_completed_targets(
    forecast: dict[str, Any], generated_at: str
) -> tuple[dict[str, Any], int]:
    """Return a snapshot payload containing only prospective market targets."""
    source_timestamp = int(datetime.fromisoformat(generated_at).timestamp())
    filtered = deepcopy(forecast)
    markets = forecast.get("markets", [])
    if not isinstance(markets, list):
        return filtered, 0

    prospective_markets = []
    stale_count = 0
    for market in markets:
        if not isinstance(market, dict):
            prospective_markets.append(market)
            continue
        market_id = market.get("id")
        symbol = market_data.SYMBOLS.get(market_id)
        target_date = market.get("next_session_date")
        if symbol is None or not isinstance(target_date, str) or not target_date:
            prospective_markets.append(market)
            continue
        if market_data.session_date_close_timestamp(symbol, target_date) <= source_timestamp:
            stale_count += 1
            LOGGER.warning(
                "Skipping stale prospective forecast: generated_at=%s market=%s target=%s",
                generated_at,
                market_id,
                target_date,
            )
            continue
        prospective_markets.append(market)
    filtered["markets"] = prospective_markets
    return filtered, stale_count


def save_snapshot(
    forecast_path: Path = FORECAST_PATH,
    prospective_dir: Path = PROSPECTIVE_DIR,
) -> tuple[Path | None, bool]:
    """Create one deterministic snapshot, returning ``(path, created)``.

    An existing snapshot for the same ``generated_at`` is accepted only when
    its forecast payload is identical. This check also covers legacy filenames.
    """
    forecast = _load_json(forecast_path)
    if not isinstance(forecast, dict):
        raise ValueError(f"Forecast must be a JSON object: {forecast_path}")
    generated_at = forecast.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        raise ValueError(f"Forecast has no generated_at: {forecast_path}")

    snapshot_forecast, stale_count = _without_completed_targets(forecast, generated_at)
    snapshot = {"source_generated_at": generated_at, "forecast": snapshot_forecast}
    destination = prospective_dir / _snapshot_name(generated_at)

    for candidate in prospective_dir.glob("*.json"):
        existing = _load_json(candidate)
        if not isinstance(existing, dict) or existing.get("source_generated_at") != generated_at:
            continue
        if existing.get("forecast") != snapshot_forecast:
            raise FileExistsError(
                f"Snapshot for {generated_at} already exists with different content: {candidate}"
            )
        return candidate, False

    if stale_count and not snapshot_forecast.get("markets"):
        LOGGER.warning(
            "Skipping prospective snapshot because all markets are stale: generated_at=%s",
            generated_at,
        )
        return None, False

    prospective_dir.mkdir(parents=True, exist_ok=True)

    # Exclusive creation is the final guard against concurrent overwrite.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(snapshot, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination, True


def main() -> None:
    path, created = save_snapshot()
    if path is None:
        print("No prospective forecast snapshot saved; all market targets were stale.")
        return
    action = "Saved" if created else "Already saved"
    print(f"{action} prospective forecast: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

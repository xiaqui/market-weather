#!/usr/bin/env python3
"""Save the current forecast as an immutable prospective snapshot."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FORECAST_PATH = ROOT / "shared" / "forecast.json"
PROSPECTIVE_DIR = ROOT / "reports" / "live-forecast"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_name(generated_at: str) -> str:
    moment = datetime.fromisoformat(generated_at)
    if moment.tzinfo is None:
        raise ValueError("forecast generated_at must include a timezone")
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H-%M-%SZ.json")


def save_snapshot(
    forecast_path: Path = FORECAST_PATH,
    prospective_dir: Path = PROSPECTIVE_DIR,
) -> tuple[Path, bool]:
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

    snapshot = {"source_generated_at": generated_at, "forecast": forecast}
    prospective_dir.mkdir(parents=True, exist_ok=True)
    destination = prospective_dir / _snapshot_name(generated_at)

    for candidate in prospective_dir.glob("*.json"):
        existing = _load_json(candidate)
        if not isinstance(existing, dict) or existing.get("source_generated_at") != generated_at:
            continue
        if existing.get("forecast") != forecast:
            raise FileExistsError(
                f"Snapshot for {generated_at} already exists with different content: {candidate}"
            )
        return candidate, False

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
    action = "Saved" if created else "Already saved"
    print(f"{action} prospective forecast: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

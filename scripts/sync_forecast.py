#!/usr/bin/env python3
"""Copy the canonical forecast into each distributable client."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared" / "forecast.json"
TARGETS = (
    ROOT / "android" / "app" / "src" / "main" / "assets" / "forecast.json",
    ROOT / "android" / "app" / "src" / "test" / "resources" / "forecast.json",
    ROOT / "web" / "forecast.json",
)
def main() -> None:
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, target)
        print(f"Synced {SOURCE.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
if __name__ == "__main__":
    main()

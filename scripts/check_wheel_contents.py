"""Reject metadata-only wheels produced by an incomplete package map."""

from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZipFile

EXPECTED = {
    "shockgraph_analytics/__init__.py",
    "shockgraph_calibration/__init__.py",
    "shockgraph_collector/__init__.py",
    "shockgraph_data_pipeline/__init__.py",
    "shockgraph_domain/__init__.py",
    "shockgraph_domain/event_feed.py",
    "shockgraph_risk/__init__.py",
    "shockgraph_risk/forward_risk_capture.py",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("wheel path is required", file=sys.stderr)
        return 2
    with ZipFile(Path(sys.argv[1])) as wheel:
        missing = EXPECTED - set(wheel.namelist())
    if missing:
        print("wheel missing packages: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1
    print(f"wheel contains {len(EXPECTED)} required source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/event_study"))

from shockgraph_analytics.contracts import ResearchDataset  # noqa: E402
from shockgraph_analytics.evaluation import evaluate  # noqa: E402


def run(input_path: Path, output_dir: Path, min_train: int, min_scenario: int) -> Path:
    raw = input_path.read_bytes()
    dataset = ResearchDataset.model_validate_json(raw)
    result = evaluate(dataset, min_train=min_train, min_scenario=min_scenario)
    result["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
    content = (
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    run_id = hashlib.sha256(content.encode()).hexdigest()
    directory = output_dir / run_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "report.json"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("existing report does not match its content address") from None
    print(
        json.dumps(
            {
                "status": result["status"],
                "run_id": run_id,
                "report": str(path),
                "evaluated_events": result["evaluated_events"],
            },
            ensure_ascii=False,
        )
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="발표 단위 과거 분포·확률 가중 기준 모델 비교")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/event-research")
    parser.add_argument("--min-train", type=int, default=20)
    parser.add_argument("--min-scenario", type=int, default=2)
    args = parser.parse_args()
    run(args.input, args.output, args.min_train, args.min_scenario)


if __name__ == "__main__":
    main()

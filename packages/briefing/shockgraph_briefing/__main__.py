"""Run the explicit collect -> draft -> review workflow for CAMT."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import timedelta
from pathlib import Path

import httpx

from .filings import collect_camt
from .pipeline import (
    CaptureStatus,
    Window,
    make_draft,
    openai_summary,
    read_artifact,
    review,
    utc_now,
    write_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/briefing"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("collect")
    draft = commands.add_parser("draft")
    draft.add_argument("--allow-source-transfer", action="store_true", required=True)
    approve = commands.add_parser("publish")
    approve.add_argument("--reviewed-sha256", required=True)
    args = parser.parse_args()
    directory: Path = args.directory
    capture_path = directory / "capture-camt.json"
    draft_path = directory / "draft-camt.json"

    try:
        if args.command == "collect":
            user_agent = os.environ.get("SHOCKGRAPH_SEC_USER_AGENT", "")
            if not user_agent.strip():
                print("Set SHOCKGRAPH_SEC_USER_AGENT to the operator application and contact.")
                return 2
            try:
                with httpx.Client(timeout=12.0) as client:
                    filing = collect_camt(client, user_agent=user_agent)
            except (httpx.HTTPError, ValueError, LookupError) as error:
                write_artifact(capture_path, CaptureStatus(checked_at=utc_now(), status="failed"))
                http_status = (
                    f" HTTP {error.response.status_code}"
                    if isinstance(error, httpx.HTTPStatusError)
                    else ""
                )
                print(
                    f"SEC collection failed: {type(error).__name__}{http_status}", file=sys.stderr
                )
                return 1
            now = utc_now()
            write_artifact(capture_path, CaptureStatus(checked_at=now, status="ok", filing=filing))
            state = (
                "eligible"
                if filing and filing.accepted_at >= now - Window
                else "outside-7d"
                if filing
                else "no-filing"
            )
            print(f"CAMT collection: {state}")
            if filing:
                print(f"{filing.form} {filing.accession} {filing.accepted_at.isoformat()}")
            return 0

        capture = CaptureStatus.model_validate_json(read_artifact(capture_path))
        filing = capture.filing
        now = utc_now()
        if (
            capture.status != "ok"
            or not now - timedelta(days=1) <= capture.checked_at <= now
            or filing is None
            or not now - Window <= filing.accepted_at <= now
        ):
            print("No eligible CAMT filing in the 7-day window.", file=sys.stderr)
            return 2
        if args.command == "draft":
            model = os.environ.get("SHOCKGRAPH_BRIEFING_MODEL", "").strip()
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not model or not key:
                print("Set SHOCKGRAPH_BRIEFING_MODEL and OPENAI_API_KEY.", file=sys.stderr)
                return 2
            with httpx.Client(timeout=25.0) as client:
                result = make_draft(
                    filing,
                    lambda chunks: openai_summary(
                        chunks,
                        client=client,
                        model=model,
                        api_key=key,
                    ),
                    model=model,
                    as_of=now,
                )
            write_artifact(draft_path, result)
            digest = hashlib.sha256(read_artifact(draft_path)).hexdigest()
            print(f"Review every claim against the filing first. Draft SHA-256: {digest}")
            return 0
        result = review(
            filing,
            read_artifact(draft_path),
            reviewed_sha256=args.reviewed_sha256,
            as_of=now,
        )
        write_artifact(directory / "reviewed-camt.json", result)
        print("Reviewed CAMT briefing published to the local artifact directory.")
        return 0
    except (OSError, httpx.HTTPError, ValueError, LookupError, TypeError) as error:
        print(f"Briefing command failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

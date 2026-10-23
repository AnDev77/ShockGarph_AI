"""Read-only S3 audit of a private price vintage and forward risk record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.archive_forward_capture import audit_capture  # noqa: E402
from scripts.private_r2 import configured_r2  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="비공개 가격 빈티지 원격 재검증")
    parser.add_argument("--index-key", required=True)
    args = parser.parse_args(argv)
    try:
        client, bucket = configured_r2()
    except (ValueError, ImportError):
        print(json.dumps({"status": "private_archive_not_configured"}))
        return 2
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    try:
        result = audit_capture(client, bucket=bucket, index_key=args.index_key)
    except Exception:
        print(json.dumps({"status": "private_archive_audit_failed"}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

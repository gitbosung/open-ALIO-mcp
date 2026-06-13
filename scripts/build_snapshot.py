"""Build the runtime SQLite snapshot used by uvx/package installs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from open_alio_mcp.snapshot import (  # noqa: E402
    SNAPSHOT_FILENAME,
    pack_data_dir,
    validate_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack data/ into alio_snapshot.db")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data",
        help="Source data directory. Defaults to ./data.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / SNAPSHOT_FILENAME,
        help="Output SQLite snapshot path. Defaults to ./dist/alio_snapshot.db.",
    )
    args = parser.parse_args()

    meta = pack_data_dir(args.data_dir, args.out)
    ok, reason = validate_snapshot(args.out)
    if not ok:
        print(f"[FAIL] snapshot validation failed: {reason}", file=sys.stderr)
        return 1

    print(f"[OK] wrote {args.out}")
    print(f"docs={meta['doc_count']} raw_bytes={meta['raw_bytes']} built_at={meta['built_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

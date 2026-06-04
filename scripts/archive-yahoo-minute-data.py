from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from grit_day_trading.market_archive import archive_yahoo_minutes_for_committed_fills
from grit_day_trading.storage import connect, initialize_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive Yahoo Finance minute bars for committed fill symbols.")
    parser.add_argument("--db", default="data/grit_day_trading.db", help="SQLite database path.")
    parser.add_argument("--date", help="Optional trade date filter in YYYY-MM-DD format.")
    parser.add_argument("--force", action="store_true", help="Refresh existing archive rows.")
    args = parser.parse_args(argv)

    conn = connect(args.db)
    try:
        initialize_database(conn)
        summary = archive_yahoo_minutes_for_committed_fills(conn, trade_date=args.date, force=args.force)
    finally:
        conn.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

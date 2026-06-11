from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from grit_day_trading.market_archive import archive_yahoo_minutes_for_symbol_group_window
from grit_day_trading.storage import connect, initialize_database


DEFAULT_SYMBOLS = ("MU", "NVDA", "SPY")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive local 1-minute bars for research symbols into SQLite.")
    parser.add_argument("--db", default="data/grit_day_trading.db", help="SQLite database path.")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols to archive. Defaults to MU,NVDA,SPY.",
    )
    parser.add_argument(
        "--date",
        default=datetime.now(UTC).date().isoformat(),
        help="End trade date in YYYY-MM-DD format. Use the most recent US session after close.",
    )
    parser.add_argument(
        "--window-trading-days",
        type=int,
        default=1,
        help="Number of recent calendar days to archive, capped by the backend contract at 30.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh existing archive rows.")
    args = parser.parse_args(argv)

    symbols = [symbol for symbol in args.symbols.replace("，", ",").split(",") if symbol.strip()]
    conn = connect(args.db)
    try:
        initialize_database(conn)
        summary = archive_yahoo_minutes_for_symbol_group_window(
            conn,
            symbols=symbols,
            end_date=args.date,
            window_trading_days=args.window_trading_days,
            force=args.force,
        )
    finally:
        conn.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

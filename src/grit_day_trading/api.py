from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .service import daily_summary, get_batch, import_stp_txt, list_batches, list_fills, list_quarantine
from .storage import connect, initialize_database


DEFAULT_DB_PATH = Path("data/grit_day_trading.db")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    resolved_db_path = Path(db_path or os.getenv("GRIT_DAY_TRADING_DB", DEFAULT_DB_PATH))
    app = FastAPI(title="Grit Day Trading Platform", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_conn():
        conn = connect(resolved_db_path)
        initialize_database(conn)
        try:
            yield conn
        finally:
            conn.close()

    @app.get("/api/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/imports/stp-txt")
    async def upload_stp_txt(file: Annotated[UploadFile, File()], conn=Depends(get_conn)):
        raw_bytes = await file.read()
        return import_stp_txt(conn, file.filename or "stp.txt", raw_bytes)

    @app.get("/api/imports")
    def imports(conn=Depends(get_conn)):
        return {"items": list_batches(conn)}

    @app.get("/api/imports/{batch_id}")
    def import_batch(batch_id: str, conn=Depends(get_conn)):
        try:
            return get_batch(conn, batch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="batch_not_found") from exc

    @app.get("/api/imports/{batch_id}/quarantine")
    def import_quarantine(batch_id: str, conn=Depends(get_conn)):
        try:
            get_batch(conn, batch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="batch_not_found") from exc
        return {"items": list_quarantine(conn, batch_id)}

    @app.get("/api/fills")
    def fills(
        date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        account: str | None = None,
        symbol: str | None = None,
        conn=Depends(get_conn),
    ):
        return {"items": list_fills(conn, date=date, account=account, symbol=symbol)}

    @app.get("/api/review/daily-summary")
    def review_daily_summary(date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")], conn=Depends(get_conn)):
        return daily_summary(conn, date)

    return app


app = create_app()


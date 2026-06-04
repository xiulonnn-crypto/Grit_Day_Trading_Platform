from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Path as ApiPath, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .market_archive import (
    archive_yahoo_minutes_for_committed_fills,
    archive_yahoo_minutes_for_symbol_window,
    list_market_minute_archives,
)
from .market_context import get_market_context_for_fill, get_market_context_snapshot, replay_market_context
from .service import (
    daily_summary,
    get_batch,
    import_stp_txt,
    list_batches,
    list_fills,
    list_quarantine,
    list_trade_groups,
    review_summary,
    review_summary_groups,
)
from .storage import connect, initialize_database
from .strategy import (
    BB_SQUEEZE_TEMPLATE_KEY,
    LIQUIDITY_SWEEP_TEMPLATE_KEY,
    MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY,
    create_strategy_config,
    get_strategy_templates,
    get_strategy_optimization_run,
    list_strategy_configs,
    list_strategy_optimization_runs,
    list_strategy_signal_runs,
    list_strategy_test_batches,
    run_strategy_optimization,
    run_strategy_signal_replay,
    run_strategy_test_batch,
    update_strategy_config,
)
from .watchlist import generate_watchlist, get_watchlist


DEFAULT_DB_PATH = Path("data/grit_day_trading.db")
REQUIRED_API_ROUTES = (
    "/api/market-data/minute-archives",
    "/api/market-data/yahoo-minute-archive",
    "/api/strategy-templates",
)


class MarketContextReplayRequest(BaseModel):
    fill_id: str = Field(min_length=1)
    provider: str = Field(default="fake", pattern=r"^(fake|futu|yahoo)$")
    minutes_before: int = Field(default=30, ge=1, le=390)
    minutes_after: int = Field(default=30, ge=1, le=390)
    force: bool = False


class WatchlistGenerateRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    provider: str = Field(default="fake", pattern=r"^(fake|futu)$")
    force: bool = False


class WatchlistUpdateRequest(BaseModel):
    provider: str = Field(default="fake", pattern=r"^(fake|futu)$")
    force: bool = True


class YahooMinuteArchiveRequest(BaseModel):
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbol: str | None = Field(default=None, min_length=1, max_length=16)
    window_trading_days: int | None = Field(default=None, ge=1, le=30)
    force: bool = False


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template_key: str = Field(
        pattern=rf"^({BB_SQUEEZE_TEMPLATE_KEY}|{LIQUIDITY_SWEEP_TEMPLATE_KEY}|{MOMENTUM_MEAN_REVERSION_TEMPLATE_KEY})$"
    )
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    params: dict[str, Any] | None = None


class StrategyRunRequest(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbol: str = Field(min_length=1, max_length=16)
    provider: str = Field(default="yahoo", pattern=r"^yahoo$")
    force: bool = False


class StrategyTestRunRequest(BaseModel):
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbol: str = Field(min_length=1, max_length=16)
    provider: str = Field(default="yahoo", pattern=r"^yahoo$")
    window_trading_days: int = Field(default=30, ge=1, le=30)
    force: bool = False


class StrategyOptimizationRequest(StrategyTestRunRequest):
    objective: str = Field(default="stable_profitability_v1", pattern=r"^stable_profitability_v1$")
    search_space: dict[str, list[Any]] | None = None


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
    def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "app": "grit_day_trading_platform",
            "version": app.version,
            "required_routes": list(REQUIRED_API_ROUTES),
        }

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

    @app.get("/api/review/summary")
    def review_summary_endpoint(
        date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        conn=Depends(get_conn),
    ):
        return review_summary(conn, date=date, symbol=symbol)

    @app.get("/api/review/summary-groups")
    def review_summary_groups_endpoint(
        group_by: Annotated[str, Query(pattern=r"^(date|symbol)$")],
        date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        conn=Depends(get_conn),
    ):
        return {"items": review_summary_groups(conn, group_by=group_by, date=date, symbol=symbol)}

    @app.get("/api/trade-groups")
    def trade_groups(
        date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        account: str | None = None,
        symbol: str | None = None,
        conn=Depends(get_conn),
    ):
        return {"items": list_trade_groups(conn, date=date, account=account, symbol=symbol)}

    @app.post("/api/market-context/replay")
    def market_context_replay(request: MarketContextReplayRequest, conn=Depends(get_conn)):
        try:
            return replay_market_context(
                conn,
                fill_id=request.fill_id,
                provider_name=request.provider,
                minutes_before=request.minutes_before,
                minutes_after=request.minutes_after,
                force=request.force,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/fills/{fill_id}/market-context")
    def fill_market_context(fill_id: str, conn=Depends(get_conn)):
        try:
            return get_market_context_for_fill(conn, fill_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc

    @app.get("/api/market-context/{snapshot_id}")
    def market_context_snapshot(snapshot_id: str, conn=Depends(get_conn)):
        try:
            return get_market_context_snapshot(conn, snapshot_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc

    @app.post("/api/market-data/yahoo-minute-archive")
    def yahoo_minute_archive(request: YahooMinuteArchiveRequest, conn=Depends(get_conn)):
        try:
            if request.symbol or request.window_trading_days:
                if not request.symbol:
                    raise ValueError("archive_symbol_required")
                if not request.date:
                    raise ValueError("archive_end_date_required")
                return archive_yahoo_minutes_for_symbol_window(
                    conn,
                    symbol=request.symbol,
                    end_date=request.date,
                    window_trading_days=request.window_trading_days or 1,
                    force=request.force,
                )
            return archive_yahoo_minutes_for_committed_fills(conn, trade_date=request.date, force=request.force)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/market-data/minute-archives")
    def market_minute_archives(
        date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        provider: str | None = None,
        conn=Depends(get_conn),
    ):
        return {"items": list_market_minute_archives(conn, trade_date=date, symbol=symbol, provider=provider)}

    @app.post("/api/watchlist/generate")
    def watchlist_generate(request: WatchlistGenerateRequest, conn=Depends(get_conn)):
        return generate_watchlist(conn, trade_date=request.date, provider_name=request.provider, force=request.force)

    @app.get("/api/watchlist")
    def watchlist(date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")], conn=Depends(get_conn)):
        return get_watchlist(conn, date)

    @app.put("/api/watchlist/{date}")
    def watchlist_update(
        date: Annotated[str, ApiPath(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        request: WatchlistUpdateRequest,
        conn=Depends(get_conn),
    ):
        return generate_watchlist(conn, trade_date=date, provider_name=request.provider, force=request.force)

    @app.get("/api/strategy-templates")
    def strategy_templates():
        return {"items": get_strategy_templates()}

    @app.get("/api/strategies")
    def strategies(conn=Depends(get_conn)):
        return {"items": list_strategy_configs(conn)}

    @app.post("/api/strategies")
    def strategy_create(request: StrategyCreateRequest, conn=Depends(get_conn)):
        try:
            return create_strategy_config(
                conn,
                name=request.name,
                template_key=request.template_key,
                params=request.params,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/strategies/{strategy_id}")
    def strategy_update(strategy_id: str, request: StrategyUpdateRequest, conn=Depends(get_conn)):
        try:
            return update_strategy_config(
                conn,
                strategy_id,
                name=request.name,
                enabled=request.enabled,
                params=request.params,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/strategies/{strategy_id}/runs")
    def strategy_run(strategy_id: str, request: StrategyRunRequest, conn=Depends(get_conn)):
        try:
            return run_strategy_signal_replay(
                conn,
                strategy_id=strategy_id,
                trade_date=request.date,
                symbol=request.symbol,
                provider=request.provider,
                force=request.force,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/strategy-runs")
    def strategy_runs(
        date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        conn=Depends(get_conn),
    ):
        return {
            "items": list_strategy_signal_runs(
                conn,
                trade_date=date,
                symbol=symbol,
                strategy_id=strategy_id,
            )
        }

    @app.post("/api/strategies/{strategy_id}/test-runs")
    def strategy_test_run(strategy_id: str, request: StrategyTestRunRequest, conn=Depends(get_conn)):
        try:
            return run_strategy_test_batch(
                conn,
                strategy_id=strategy_id,
                end_date=request.end_date,
                symbol=request.symbol,
                provider=request.provider,
                window_trading_days=request.window_trading_days,
                force=request.force,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/strategy-test-runs")
    def strategy_test_runs(
        end_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        conn=Depends(get_conn),
    ):
        return {
            "items": list_strategy_test_batches(
                conn,
                end_date=end_date,
                symbol=symbol,
                strategy_id=strategy_id,
            )
        }

    @app.post("/api/strategies/{strategy_id}/optimizations")
    def strategy_optimization(strategy_id: str, request: StrategyOptimizationRequest, conn=Depends(get_conn)):
        try:
            return run_strategy_optimization(
                conn,
                strategy_id=strategy_id,
                end_date=request.end_date,
                symbol=request.symbol,
                provider=request.provider,
                window_trading_days=request.window_trading_days,
                objective=request.objective,
                search_space=request.search_space,
                force=request.force,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/strategy-optimizations")
    def strategy_optimizations(
        end_date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        conn=Depends(get_conn),
    ):
        return {
            "items": list_strategy_optimization_runs(
                conn,
                end_date=end_date,
                symbol=symbol,
                strategy_id=strategy_id,
            )
        }

    @app.get("/api/strategy-optimizations/{optimization_id}")
    def strategy_optimization_detail(optimization_id: str, conn=Depends(get_conn)):
        try:
            return get_strategy_optimization_run(conn, optimization_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc

    return app


app = create_app()


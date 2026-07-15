from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.schemas import DiagnosticStartRequest, IndexSelectionUpdate, IndexSelectionView, PaperCapitalTargetRequest
from application.dashboard_service import DashboardService
from application.diagnostic_capture import DiagnosticCaptureService
from application.index_selection import IndexSelectionService, IndexSelectionSnapshot
from application.runtime_service import RuntimeService, production_paper_engine_factory
from config.settings import TradingConfig
from core.index_registry import IndexRegistry
from database.capital_ledger import CapitalLedger
from database.trade_store import TradeStore


def _selection_view(snapshot: IndexSelectionSnapshot) -> IndexSelectionView:
    return IndexSelectionView(
        symbols=sorted(snapshot.symbols),
        version=snapshot.version,
        is_all=snapshot.is_all,
        pause_new_entries=snapshot.pause_new_entries,
    )


def create_app(
    frontend_dir: Path | None = None,
    *,
    trade_store: TradeStore | None = None,
    capital_ledger: CapitalLedger | None = None,
    config: TradingConfig | None = None,
    diagnostics: DiagnosticCaptureService | None = None,
    now_provider: Callable[[], datetime] | None = None,
    runtime: RuntimeService | None = None,
) -> FastAPI:
    registry = IndexRegistry.default()
    selection = IndexSelectionService(registry)
    diagnostic_capture = diagnostics or DiagnosticCaptureService()
    runtime_service = runtime or RuntimeService(
        production_paper_engine_factory(diagnostic_capture, selection)
    )
    dashboard = DashboardService(
        trade_store=trade_store or TradeStore(),
        capital_ledger=capital_ledger or CapitalLedger(),
        config=config or TradingConfig.load(),
        now_provider=now_provider or datetime.now,
        active_trade_provider=lambda: (
            runtime_service.engine.active_trade
            if runtime_service.engine is not None
            else None
        ),
    )
    app = FastAPI(title="AutoTrader Control API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.index_registry = registry
    app.state.index_selection = selection
    app.state.dashboard = dashboard
    app.state.diagnostics = diagnostic_capture
    app.state.runtime = runtime_service

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "execution_safety": "PAPER_ONLY_DURING_BUILD"}

    @app.get("/api/runtime")
    def runtime_status() -> dict:
        return runtime_service.snapshot().__dict__

    @app.post("/api/engine/start")
    def start_engine() -> dict:
        try:
            return runtime_service.start().__dict__
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/engine/stop")
    def stop_engine() -> dict:
        try:
            return runtime_service.stop().__dict__
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/indices")
    def indices() -> dict:
        rows = []
        for symbol in sorted(registry.symbols):
            spec = registry.get(symbol)
            rows.append({
                "symbol": spec.symbol,
                "display_name": spec.display_name,
                "lot_size": spec.lot_size,
                "permission": spec.permission.value,
                "metadata_requires_runtime_validation": spec.metadata_requires_runtime_validation,
                "runtime_connected": spec.runtime_connected,
            })
        return {
            "indices": rows,
            "selection": _selection_view(selection.snapshot()).model_dump(),
        }

    @app.put("/api/indices/selection", response_model=IndexSelectionView)
    def update_selection(request: IndexSelectionUpdate) -> IndexSelectionView:
        try:
            snapshot = selection.update(
                set(request.symbols),
                expected_version=request.expected_version,
                execution_mode="PAPER",
            )
        except ValueError as exc:
            message = str(exc)
            status = 409 if "selection version" in message.lower() else 422
            raise HTTPException(status_code=status, detail=message) from exc
        return _selection_view(snapshot)

    @app.get("/api/performance")
    def performance(period: str = "today", mode: str = "PAPER") -> dict:
        try:
            return dashboard.performance(period, mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/positions/active")
    def active_position(mode: str = "PAPER") -> dict | None:
        try:
            return dashboard.active_position(mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/trades")
    def trades(mode: str = "PAPER") -> list[dict]:
        try:
            return dashboard.journal(mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/capital")
    def capital(mode: str = "PAPER") -> dict:
        try:
            return dashboard.capital(mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/capital/paper/target")
    def adjust_paper_capital(request: PaperCapitalTargetRequest) -> dict:
        runtime_snapshot = runtime_service.snapshot()
        try:
            return dashboard.adjust_paper_target(
                target_equity=request.target_equity,
                note=request.note,
                engine_running=runtime_snapshot.state == "RUNNING",
                has_open_position=runtime_snapshot.has_active_position,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/diagnostics")
    def diagnostic_status() -> dict:
        snapshot = diagnostic_capture.snapshot()
        return {
            "capturing": snapshot.capturing,
            "top_count": snapshot.top_count,
            "rows": list(snapshot.rows),
        }

    @app.post("/api/diagnostics/start")
    def start_diagnostics(request: DiagnosticStartRequest) -> dict:
        try:
            snapshot = diagnostic_capture.start(request.top_count)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "capturing": snapshot.capturing,
            "top_count": snapshot.top_count,
            "rows": list(snapshot.rows),
        }

    @app.post("/api/diagnostics/stop")
    def stop_diagnostics() -> dict:
        snapshot = diagnostic_capture.stop()
        return {
            "capturing": snapshot.capturing,
            "top_count": snapshot.top_count,
            "rows": list(snapshot.rows),
        }

    @app.get("/api/diagnostics/download")
    def download_diagnostics(format: str = Query(default="csv", pattern="^(csv|json)$")) -> Response:
        if format == "json":
            return Response(
                diagnostic_capture.to_json(),
                media_type="application/json",
                headers={"Content-Disposition": "attachment; filename=pair-diagnostics.json"},
            )
        return Response(
            diagnostic_capture.to_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=pair-diagnostics.csv"},
        )

    @app.websocket("/api/events")
    async def runtime_events(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                runtime_snapshot = runtime_service.snapshot()
                diagnostic_snapshot = diagnostic_capture.snapshot()
                await websocket.send_json(
                    {
                        "type": "runtime_snapshot",
                        "runtime": runtime_snapshot.__dict__,
                        "position": dashboard.active_position("PAPER"),
                        "diagnostics": {
                            "capturing": diagnostic_snapshot.capturing,
                            "top_count": diagnostic_snapshot.top_count,
                            "rows": list(diagnostic_snapshot.rows),
                        },
                    }
                )
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return

    compiled_frontend = frontend_dir or Path(__file__).resolve().parents[1] / "webui" / "dist"
    if compiled_frontend.exists():
        app.mount("/", StaticFiles(directory=compiled_frontend, html=True), name="web-ui")
    else:
        @app.get("/")
        def frontend_not_built() -> dict[str, str]:
            return {
                "status": "frontend_not_built",
                "instruction": "Run npm.cmd install and npm.cmd run build in webui.",
            }

    return app


app = create_app()

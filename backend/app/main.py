"""FastAPI 应用组装（M0）。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, batches, chat, diagnoses, evaluations, nl, system
from app.api import uploads_api
from app.batches import BatchRunner
from app.config import Settings
from app.db import Database, new_id
from app.errors import ApiError
from app.knowledge import KnowledgeService
from app.runtime.runner import DiagnosisRunner
from app.startup import SelfCheck

logger = logging.getLogger("edg.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    gaps = settings.production_startup_gaps()
    if gaps:
        message = "生产环境启动自检失败，缺少：" + "；".join(gaps)
        logger.error(message)
        raise RuntimeError(message)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_dirs()
        db = Database(settings.db_path)
        db.migrate()
        async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as saver:
            knowledge = KnowledgeService(settings, db)
            knowledge.ensure_built()
            runner = DiagnosisRunner(settings, db, knowledge, saver)
            batch_runner = BatchRunner(settings, db, runner)
            app.state.settings = settings
            app.state.db = db
            app.state.knowledge = knowledge
            app.state.runner = runner
            app.state.batch_runner = batch_runner
            app.state.checkpointer = saver
            app.state.self_check = SelfCheck(settings, settings.db_path, knowledge, True)
            await runner.reconcile_on_startup()
            await batch_runner.resume_queued()
            ttl_task = asyncio.create_task(
                runner.ttl_loop(settings.interrupt_scan_seconds), name="interrupt-ttl-scan"
            )
            logger.info(
                "startup self-check: %s; interrupt ttl scan every %ss",
                app.state.self_check.components,
                settings.interrupt_scan_seconds,
            )
            try:
                yield
            finally:
                ttl_task.cancel()
                await asyncio.gather(ttl_task, return_exceptions=True)
                await batch_runner.wait_all()
                for task in list(runner._tasks.values()):
                    task.cancel()
                await runner.wait_all()
                db.close()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = new_id("req")
        request.state.request_id = request_id
        if settings.csrf_enforce and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if not origin or not origin.startswith(settings.app_origin):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "CSRF_ORIGIN_INVALID",
                            "message": "Origin 校验失败，请刷新页面",
                            "request_id": request_id,
                        }
                    },
                )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        if "text/event-stream" not in response.headers.get("content-type", ""):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        body = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", new_id("req")),
            }
        }
        if exc.details:
            body["error"]["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        fields = []
        code = "VALIDATION_FAILED"
        for error in exc.errors():
            loc = [str(part) for part in error.get("loc", []) if part != "body"]
            field = loc[-1] if loc else "body"
            fields.append(
                {
                    "field": field,
                    "reason": error.get("type", "INVALID").upper(),
                    "message": error.get("msg", "字段校验失败"),
                }
            )
            if field == "device_id" and error.get("type") == "missing":
                code = "DEVICE_ID_INVALID"
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": code,
                    "message": "请求字段校验失败",
                    "request_id": getattr(request.state, "request_id", new_id("req")),
                    "details": {"fields": fields},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "request_id": getattr(request.state, "request_id", new_id("req")),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务内部错误，请联系管理员",
                    "request_id": getattr(request.state, "request_id", new_id("req")),
                }
            },
        )

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(system.router, prefix=prefix)
    app.include_router(uploads_api.router, prefix=prefix)
    app.include_router(nl.router, prefix=prefix)
    app.include_router(diagnoses.router, prefix=prefix)
    app.include_router(batches.router, prefix=prefix)
    app.include_router(evaluations.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    return app


app = create_app()

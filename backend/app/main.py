from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import AppError


settings = get_settings()
app = FastAPI(
    title="SetRescue AI API",
    version="0.1.0",
    description="Local-first production readiness and adaptive recovery API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)
app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "error": {"code": exc.code, "message": exc.public_message, "details": exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"success": False, "data": None, "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed.", "details": {"fields": details}}},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logging.getLogger("setrescue").exception("Database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": {"code": "DATABASE_ERROR", "message": "A database operation failed.", "details": {}}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("setrescue").exception("Unhandled API error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "details": {}}},
    )


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "api": settings.api_prefix}

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.public_message = message
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)


def not_found(resource: str = "Resource") -> AppError:
    return AppError(404, "RESOURCE_NOT_FOUND", f"{resource} was not found.")


def success(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}

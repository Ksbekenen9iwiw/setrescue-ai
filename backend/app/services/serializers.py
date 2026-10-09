from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.inspection import inspect


def iso(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def model_dict(instance: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or set()
    return {
        column.key: iso(getattr(instance, column.key))
        for column in inspect(instance).mapper.column_attrs
        if column.key not in excluded
    }


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback

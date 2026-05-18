import contextlib
import contextvars
import time
import uuid
from typing import Any, Dict, List, Optional

from django.db import connection

from .utils import safe_truncate


_fias_context = contextvars.ContextVar("fias_log_context", default=None)


@contextlib.contextmanager
def fias_log_context(
    *,
    session_id: Optional[str],
    message_log_id: Optional[int],
    state_stage: str,
    log_ids: Optional[List[int]] = None,
):
    payload = {
        "session_id": session_id,
        "message_log_id": message_log_id,
        "state_stage": state_stage,
        "log_ids": log_ids if log_ids is not None else [],
    }
    token = _fias_context.set(payload)
    try:
        yield payload
    finally:
        _fias_context.reset(token)


def get_current_fias_log_ids() -> List[int]:
    context = _fias_context.get() or {}
    return list(context.get("log_ids") or [])


def log_fias_request_sync(
    *,
    method: str,
    endpoint: str,
    request_payload: Optional[Dict[str, Any]],
    response_payload: Optional[Dict[str, Any]],
    http_status: Optional[int],
    duration_ms: float,
    error_message: Optional[str] = None,
) -> Optional[int]:
    context = _fias_context.get()
    if not context:
        return None

    try:
        extracted = _extract_fias_result(response_payload)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO fias_request_log (
                    request_id,
                    session_id,
                    message_log_id,
                    state_stage,
                    method,
                    endpoint,
                    request_payload,
                    response_payload,
                    http_status,
                    duration_ms,
                    error_message,
                    fias_house_guid,
                    fias_street_guid,
                    building_id,
                    created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, NOW()
                )
                RETURNING id
                """,
                [
                    str(uuid.uuid4()),
                    context.get("session_id"),
                    context.get("message_log_id"),
                    context.get("state_stage"),
                    method,
                    endpoint,
                    _json_dumps(safe_truncate(request_payload or {}, 2000)),
                    _json_dumps(safe_truncate(response_payload or {}, 4000)),
                    http_status,
                    duration_ms,
                    error_message,
                    extracted.get("fias_house_guid"),
                    extracted.get("fias_street_guid"),
                    extracted.get("building_id"),
                ],
            )
            log_id = cursor.fetchone()[0]
            context.setdefault("log_ids", []).append(log_id)
            return log_id
    except Exception:
        return None


def timed_fias_call(func, *, method: str, endpoint: str, request_payload: Dict[str, Any]):
    start = time.perf_counter()
    try:
        response_payload = func()
        duration_ms = (time.perf_counter() - start) * 1000
        log_fias_request_sync(
            method=method,
            endpoint=endpoint,
            request_payload=request_payload,
            response_payload=response_payload,
            http_status=200,
            duration_ms=duration_ms,
            error_message=None,
        )
        return response_payload
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        status = getattr(getattr(exc, "response", None), "status_code", None)
        response_text = getattr(getattr(exc, "response", None), "text", None)
        log_fias_request_sync(
            method=method,
            endpoint=endpoint,
            request_payload=request_payload,
            response_payload={"raw_error_response": response_text} if response_text else {},
            http_status=status,
            duration_ms=duration_ms,
            error_message=str(exc)[:1000],
        )
        raise


def _extract_fias_result(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    if not isinstance(payload, dict):
        return result
    addresses = payload.get("addresses")
    candidates = addresses if isinstance(addresses, list) else [payload]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        level = item.get("object_level_id")
        guid = item.get("object_guid")
        if level == 10 and guid:
            result["fias_house_guid"] = guid
        hierarchy = item.get("hierarchy") or []
        if isinstance(hierarchy, list):
            for node in hierarchy:
                if isinstance(node, dict) and node.get("object_level_id") == 8 and node.get("object_guid"):
                    result["fias_street_guid"] = node.get("object_guid")
    return result


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)

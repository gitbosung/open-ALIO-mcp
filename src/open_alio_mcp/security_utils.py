# -*- coding: utf-8 -*-
"""Security helpers for MCP tools and external API calls."""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

SENSITIVE_QUERY_KEYS = {
    "servicekey",
    "apikey",
    "api_key",
    "authkey",
    "key",
    "oc",
    "clientsecret",
    "client_secret",
    "naver_client_secret",
    "data_go_kr_service_key",
    "law_api_oc",
}
RESERVED_API_PARAMS = {
    "serviceKey",
    "ServiceKey",
    "apiKey",
    "apikey",
    "authKey",
    "key",
    "OC",
    "type",
    "resultType",
}
_SECRET_REPLACEMENTS = [
    re.compile(r"((?:serviceKey|ServiceKey|apiKey|apikey|authKey|key|OC)=)[^&\s]+", re.IGNORECASE),
    re.compile(r"((?:DATA_GO_KR_SERVICE_KEY|NAVER_CLIENT_SECRET|LAW_API_OC)=)[^\s]+", re.IGNORECASE),
    re.compile(r"((?:X-Naver-Client-Secret)\s*[:=]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"((?:Authorization)\s*[:=]\s*(?:Bearer\s+)?)\S+", re.IGNORECASE),
]
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ORG_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{0,32}$")

MAX_RESPONSE_CHARS = int(os.environ.get("MAX_RESPONSE_CHARS", "50000"))
MAX_ITEMS_PER_TOOL = int(os.environ.get("MAX_ITEMS_PER_TOOL", "100"))
MAX_YEAR = max(datetime.now().year + 1, 2026)


class InputValidationError(ValueError):
    """Raised when an MCP tool argument fails local validation."""


@dataclass(frozen=True)
class ArgSpec:
    kind: str
    required: bool = False
    max_length: int | None = None
    min_value: int | None = None
    max_value: int | None = None
    choices: tuple[Any, ...] | None = None
    pattern: re.Pattern[str] | None = None
    max_items: int | None = None
    forbid_path_separators: bool = False


def mask_sensitive_url(input_value: str) -> str:
    """Mask sensitive query parameters in a URL-like string."""
    if not input_value:
        return input_value
    try:
        parts = urlsplit(str(input_value))
        if not parts.scheme or not parts.netloc:
            raise ValueError("not a url")
        pairs = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            pairs.append((key, "***" if key.lower() in SENSITIVE_QUERY_KEYS else value))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs, doseq=True, safe="*"), parts.fragment))
    except Exception:
        return mask_sensitive_text(str(input_value))


def mask_sensitive_text(value: Any) -> str:
    """Mask common API key patterns in arbitrary log/error text."""
    text = str(value)
    for pattern in _SECRET_REPLACEMENTS:
        text = pattern.sub(r"\1***", text)
    return text


def safe_error_message(error: Exception | str, *, max_chars: int = 500) -> str:
    """Return a short sanitized error string for logs or user-visible payloads."""
    msg = mask_sensitive_text(error)
    if len(msg) > max_chars:
        return msg[:max_chars] + "...(truncated)"
    return msg


def build_query_params(
    defaults: dict[str, Any] | None,
    user_params: dict[str, Any] | None,
    forced: dict[str, Any] | None,
    *,
    reserved: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Merge API params while preventing user-controlled reserved params.

    Values in ``forced`` always win. Reserved keys found in user_params are ignored.
    """
    blocked: list[str] = []
    reserved_keys = reserved or RESERVED_API_PARAMS
    out = {k: v for k, v in (defaults or {}).items() if v is not None}
    for key, value in (user_params or {}).items():
        if value is None:
            continue
        if key in reserved_keys:
            blocked.append(key)
            continue
        out[key] = value
    out.update({k: v for k, v in (forced or {}).items() if v is not None})
    return out, blocked


def request_get_with_security(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    retries: int = 1,
    logger: logging.Logger | None = None,
    label: str = "External API",
    retry_delay: float = 1.0,
) -> requests.Response:
    """GET wrapper with timeout, retry, HTTP-status logging, and secret masking."""
    log = logger or logging.getLogger(__name__)
    attempts = max(retries, 0) + 1
    last_error: requests.RequestException | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            if not response.ok:
                log.warning("%s returned HTTP %s: %s", label, response.status_code, mask_sensitive_url(response.url))
            return response
        except requests.RequestException as exc:
            last_error = exc
            log.warning(
                "%s request failed attempt=%d/%d: %s",
                label,
                attempt,
                attempts,
                safe_error_message(exc),
            )
            if attempt < attempts:
                time.sleep(retry_delay)
    assert last_error is not None
    raise last_error


def _text(max_length: int = 100, *, required: bool = False) -> ArgSpec:
    return ArgSpec("str", required=required, max_length=max_length)


def _org_code(*, required: bool = False) -> ArgSpec:
    return ArgSpec("str", required=required, max_length=32, pattern=_ORG_CODE_RE)


def _doc_id() -> ArgSpec:
    return ArgSpec("str", required=True, max_length=200, forbid_path_separators=True)


def _int(min_value: int, max_value: int) -> ArgSpec:
    return ArgSpec("int", min_value=min_value, max_value=max_value)


def _choice(*choices: Any) -> ArgSpec:
    return ArgSpec("choice", choices=choices)


def _year_optional() -> ArgSpec:
    return ArgSpec("int", min_value=0, max_value=MAX_YEAR)


METRIC_CATEGORIES = (
    "staff",
    "salary",
    "executive_pay",
    "recruitment",
    "budget",
    "welfare",
    "work_life",
    "welfare_etc",
    "tax",
    "head_expense",
    "finance",
)

TOOL_ARG_SPECS: dict[str, dict[str, ArgSpec]] = {
    "search_institutions": {"query": _text(), "org_type": _text(50), "ministry": _text(80), "limit": _int(1, 100)},
    "get_institution_profile": {"org_code": _org_code(required=True), "include_detail": ArgSpec("bool")},
    "list_disclosure_items": {
        "query": _text(),
        "group": _text(50),
        "disclosure_type": _choice("", "정기", "수시"),
        "schedule": _text(50),
        "metric_category": _choice("", *METRIC_CATEGORIES),
        "only_with_metric": ArgSpec("bool"),
        "limit": _int(1, 100),
    },
    "list_metric_items": {"category": _choice(*METRIC_CATEGORIES), "item_query": _text(), "org_code": _org_code()},
    "get_institution_metrics": {
        "org_code": _org_code(required=True),
        "category": _choice(*METRIC_CATEGORIES),
        "item_query": _text(),
        "year_from": _year_optional(),
        "year_to": _year_optional(),
    },
    "get_institution_staff_summary": {"org_code": _org_code(), "query": _text(), "year_from": _year_optional(), "year_to": _year_optional()},
    "compare_institutions": {
        "org_codes": ArgSpec("str_list", required=True, min_value=2, max_value=5, max_items=5, pattern=_ORG_CODE_RE),
        "category": _choice(*METRIC_CATEGORIES),
        "item_query": _text(),
        "year_from": _year_optional(),
        "year_to": _year_optional(),
    },
    "find_institutions_by_criteria": {
        "category": _choice(*METRIC_CATEGORIES),
        "item_query": _text(required=True),
        "mode": _choice("top_n", "bottom_n", "growth_rate"),
        "year_from": _year_optional(),
        "year_to": _year_optional(),
        "org_type": _text(50),
        "ministry": _text(80),
        "n": _int(1, 50),
        "exclude_subsidiaries": ArgSpec("bool"),
        "use_classification_org_type": ArgSpec("bool"),
    },
    "get_institution_branches": {"org_code": _org_code(required=True), "limit": _int(1, 100)},
    "search_public_services": {"query": _text(), "org_code": _org_code(), "service_class": _text(50), "lifecycle": _text(50), "limit": _int(1, 50)},
    "search_facilities": {
        "org_code": _org_code(),
        "region": _text(50),
        "district": _text(50),
        "facility_type_code": _text(30),
        "free_only": ArgSpec("bool"),
        "reservable_only": ArgSpec("bool"),
        "query": _text(),
        "page": _int(1, 1000),
        "limit": _int(1, 50),
    },
    "get_facility_profile": {"facility_sn": _int(1, 10**12)},
    "search_recruitments": {
        "query": _text(),
        "org_code": _org_code(),
        "work_region_code": _text(30),
        "region": _text(50),
        "ncs": _text(80),
        "hire_type": _text(50),
        "recruit_type": _text(50),
        "education": _text(50),
        "pref": _text(100),
        "closing_within_days": _int(0, 365),
        "sort": _choice("latest", "deadline", "headcount"),
        "ongoing_only": ArgSpec("bool"),
        "include_cancelled": ArgSpec("bool"),
        "use_snapshot": ArgSpec("bool"),
        "limit": _int(1, 50),
    },
    "analyze_recruitments": {
        "dimension": _choice("region", "ncs", "hire_type", "recruit_type", "education", "org"),
        "ongoing_only": ArgSpec("bool"),
        "region": _text(50),
        "ncs": _text(80),
        "hire_type": _text(50),
        "pref": _text(100),
        "top_n": _int(1, 100),
        "use_snapshot": ArgSpec("bool"),
    },
    "get_recruitment_profile": {"recruitment_sn": _int(1, 10**12)},
    "get_institution_news": {"org_code": _org_code(), "query": _text(), "days": _int(0, 365), "sort": _choice("date", "sim"), "limit": _int(1, 50), "max_fetch": _int(1, 1000)},
    "get_institution_briefing": {"org_code": _org_code(), "query": _text(), "news_days": _int(0, 365), "metric_years": _int(1, 10), "news_count": _int(1, 20)},
    "cross_check_news_with_metrics": {"topic": _text(50, required=True), "org_code": _org_code(), "query": _text(), "news_days": _int(0, 365), "metric_years": _int(1, 10), "news_limit": _int(1, 50)},
    "digest_institution_news": {"org_code": _org_code(), "query": _text(), "days": _int(0, 365), "max_fetch": _int(1, 1000), "per_theme": _int(1, 10)},
    "search_laws": {"query": _text(required=True), "page": _int(1, 1000), "display": _int(1, 100), "scope": _choice(1, 2)},
    "get_law_text": {"mst": _text(64, required=True), "article": _text(20), "full_text": ArgSpec("bool")},
    "search_admin_rules": {"query": _text(required=True), "page": _int(1, 1000), "display": _int(1, 100), "scope": _choice(1, 2)},
    "get_admin_rule_text": {"rule_id": _text(64, required=True)},
    "search_evaluation_handbook": {"query": _text(required=True), "year": _year_optional(), "part": _text(80), "limit": _int(1, 50)},
    "list_evaluation_org_types": {"year": _year_optional()},
    "list_evaluation_indicators": {"org_class": _text(30), "org_subtype": _text(80), "year": _year_optional()},
    "get_evaluation_indicator_detail": {"query": _text(required=True), "year": _year_optional()},
    "compare_evaluation_handbook_years": {"query": _text(required=True), "year_a": _int(2000, MAX_YEAR), "year_b": _int(2000, MAX_YEAR), "limit": _int(1, 20)},
    "search_guidelines": {"query": _text(required=True), "year": _year_optional(), "issuer": _text(80), "limit": _int(1, 50)},
    "get_guideline_text": {"doc_id": _doc_id(), "article": _text(20)},
}


def _validate_value(name: str, value: Any, spec: ArgSpec) -> Any:
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise InputValidationError(f"{name}은(는) boolean이어야 합니다")
        return value
    if spec.kind == "choice":
        if value not in (spec.choices or ()):
            raise InputValidationError(f"{name} 허용값: {list(spec.choices or ())}")
        return value
    if spec.kind == "int":
        if isinstance(value, bool):
            raise InputValidationError(f"{name}은(는) 정수여야 합니다")
        try:
            ivalue = int(value)
        except (TypeError, ValueError) as exc:
            raise InputValidationError(f"{name}은(는) 정수여야 합니다") from exc
        if spec.min_value is not None and ivalue < spec.min_value:
            raise InputValidationError(f"{name}은(는) {spec.min_value} 이상이어야 합니다")
        if spec.max_value is not None and ivalue > spec.max_value:
            raise InputValidationError(f"{name}은(는) {spec.max_value} 이하여야 합니다")
        return ivalue
    if spec.kind == "str_list":
        if not isinstance(value, list):
            raise InputValidationError(f"{name}은(는) 문자열 목록이어야 합니다")
        if spec.min_value is not None and len(value) < spec.min_value:
            raise InputValidationError(f"{name}은(는) 최소 {spec.min_value}개 필요합니다")
        if spec.max_value is not None and len(value) > spec.max_value:
            raise InputValidationError(f"{name}은(는) 최대 {spec.max_value}개까지 허용됩니다")
        return [_validate_value(f"{name}[]", item, ArgSpec("str", required=True, max_length=32, pattern=spec.pattern)) for item in value]

    if not isinstance(value, str):
        raise InputValidationError(f"{name}은(는) 문자열이어야 합니다")
    text = value.strip()
    if spec.required and not text:
        raise InputValidationError(f"{name}이(가) 필요합니다")
    if spec.max_length is not None and len(text) > spec.max_length:
        raise InputValidationError(f"{name}은(는) {spec.max_length}자 이하여야 합니다")
    if _CONTROL_CHARS_RE.search(text):
        raise InputValidationError(f"{name}에 제어문자는 사용할 수 없습니다")
    if spec.forbid_path_separators and ("/" in text or "\\" in text or ".." in text):
        raise InputValidationError(f"{name}에 경로 구분자는 사용할 수 없습니다")
    if spec.pattern and not spec.pattern.match(text):
        raise InputValidationError(f"{name} 형식이 올바르지 않습니다")
    return text


def validate_tool_call(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Validate and coerce MCP tool arguments based on TOOL_ARG_SPECS."""
    specs = TOOL_ARG_SPECS.get(func.__name__)
    if not specs:
        return args, kwargs

    sig = inspect.signature(func)
    bound = sig.bind_partial(*args, **kwargs)
    bound.apply_defaults()
    for name, spec in specs.items():
        if name in bound.arguments:
            bound.arguments[name] = _validate_value(name, bound.arguments[name], spec)

    year_from = bound.arguments.get("year_from")
    year_to = bound.arguments.get("year_to")
    if year_from and year_to and int(year_from) > int(year_to):
        raise InputValidationError("year_from은 year_to보다 클 수 없습니다")

    return bound.args, bound.kwargs


def _json_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(value))


def _truncate_value(value: Any, *, max_list_items: int, max_string_chars: int) -> tuple[Any, bool]:
    truncated = False
    if isinstance(value, str):
        if len(value) > max_string_chars:
            return value[:max_string_chars] + "\n\n[응답 문자열이 길어 일부만 표시했습니다.]", True
        return value, False
    if isinstance(value, list):
        items = []
        for item in value[:max_list_items]:
            new_item, was_truncated = _truncate_value(item, max_list_items=max_list_items, max_string_chars=max_string_chars)
            items.append(new_item)
            truncated = truncated or was_truncated
        if len(value) > max_list_items:
            truncated = True
            items.append({"_truncated": f"{len(value) - max_list_items}개 항목 생략"})
        return items, truncated
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            new_item, was_truncated = _truncate_value(item, max_list_items=max_list_items, max_string_chars=max_string_chars)
            out[key] = new_item
            truncated = truncated or was_truncated
        return out, truncated
    return value, False


def limit_tool_response(response: Any, *, max_chars: int = MAX_RESPONSE_CHARS, max_items: int = MAX_ITEMS_PER_TOOL) -> Any:
    """Limit MCP response size to protect LLM context and client stability."""
    if _json_len(response) <= max_chars:
        return response
    limited, truncated = _truncate_value(
        response,
        max_list_items=max_items,
        max_string_chars=max(1000, min(5000, max_chars // 8)),
    )
    if _json_len(limited) > max_chars:
        preview = json.dumps(response, ensure_ascii=False, default=str)[:max_chars]
        limited = {
            "data": {"truncated": True, "preview": preview},
            "is_error": False,
            "caveats": ["응답이 너무 길어 미리보기만 표시했습니다. 검색 조건을 좁혀주세요."],
        }
        return limited
    if truncated and isinstance(limited, dict):
        caveats = limited.setdefault("caveats", [])
        if isinstance(caveats, list):
            caveats.append("응답이 너무 길어 일부 항목 또는 긴 문자열을 생략했습니다. 검색 조건을 좁혀주세요.")
    return limited


def validation_error_response(message: str) -> dict[str, Any]:
    return {
        "data": None,
        "is_error": True,
        "error": f"입력값 검증 실패: {message}",
    }


def unexpected_error_response() -> dict[str, Any]:
    return {
        "data": None,
        "is_error": True,
        "error": "도구 실행 중 오류가 발생했습니다. 입력 조건을 확인하거나 잠시 후 다시 시도해 주세요.",
    }


def secure_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a tool with input validation, safe errors, and response limits."""
    logger = logging.getLogger("open-ALIO-mcp")

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            safe_args, safe_kwargs = validate_tool_call(func, args, kwargs)
            return limit_tool_response(func(*safe_args, **safe_kwargs))
        except InputValidationError as exc:
            return validation_error_response(str(exc))
        except Exception as exc:  # noqa: BLE001 - last-resort guard for MCP user surface
            logger.error("Tool %s failed: %s", func.__name__, safe_error_message(exc))
            return unexpected_error_response()

    return wrapper


def wrap_fastmcp_tool_registration(tool_method: Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]) -> Callable[..., Callable[[Callable[..., Any]], Callable[..., Any]]]:
    """Inject secure_tool into FastMCP.tool registration."""

    @wraps(tool_method)
    def secured_tool(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        register = tool_method(*args, **kwargs)

        @wraps(register)
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return register(secure_tool(func))

        return decorator

    return secured_tool

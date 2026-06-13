"""공공데이터포털 — 재정경제부 공공기관 NKOD OpenAPI 클라이언트."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import requests
import xmltodict
from dotenv import load_dotenv

from .security_utils import (
    build_query_params,
    mask_sensitive_text,
    request_get_with_security,
)

load_dotenv()

log = logging.getLogger("alio")

KEY = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
PUBLIC_INST_BASE = os.environ.get(
    "PUBLIC_INST_BASE_URL", "https://apis.data.go.kr/1051000/public_inst"
).rstrip("/")
FACILITY_BASE = os.environ.get(
    "PUBLIC_FACILITY_BASE_URL", "https://apis.data.go.kr/1051000/fclt"
).rstrip("/")
BIZ_BASE = os.environ.get(
    "PUBLIC_BIZ_BASE_URL", "https://apis.data.go.kr/1051000/biz"
).rstrip("/")
RECRUIT_BASE = os.environ.get(
    "PUBLIC_RECRUIT_BASE_URL", "https://apis.data.go.kr/1051000/recruitment"
).rstrip("/")

_cache: dict[str, tuple[float, Any]] = {}
TTL = 3600


class AlioAPIError(Exception):
    pass


def _ok_code(code: Any) -> bool:
    return str(code) in ("00", "0", "200")


def _find(d: Any, target: str) -> Any:
    if isinstance(d, dict):
        for k, v in d.items():
            if k == target:
                return v
            found = _find(v, target)
            if found is not None:
                return found
    elif isinstance(d, list):
        for item in d:
            found = _find(item, target)
            if found is not None:
                return found
    return None


def call_api(url: str, params: dict[str, Any] | None = None, *, ttl: int = TTL) -> dict:
    """공통 GET: 캐시 → 호출 → JSON/XML 통일 → 오류코드 검사."""
    if not KEY:
        raise AlioAPIError("DATA_GO_KR_SERVICE_KEY가 .env에 없습니다.")

    params = dict(params or {})
    cache_key = url + str(sorted(params.items()))
    if cache_key in _cache and time.time() - _cache[cache_key][0] < ttl:
        return _cache[cache_key][1]

    p, blocked = build_query_params(
        {"pageNo": 1, "numOfRows": 100},
        params,
        {"serviceKey": KEY, "resultType": "json"},
    )
    if blocked:
        log.warning("예약 API 파라미터 무시: %s", ", ".join(blocked))

    try:
        r = request_get_with_security(
            url,
            params=p,
            timeout=15,
            retries=1,
            logger=log,
            label="ALIO API",
        )
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        raise AlioAPIError(f"API 연결 실패: {mask_sensitive_text(e)}") from e

    if "json" in (r.headers.get("Content-Type") or "").lower() or p.get("resultType") == "json":
        try:
            data = r.json()
        except ValueError as e:
            raise AlioAPIError("공공데이터 API JSON 파싱 실패") from e
    else:
        data = xmltodict.parse(r.text)

    code = _find(data, "resultCode")
    if code is not None and not _ok_code(code):
        msg = _find(data, "resultMsg") or "알 수 없는 오류"
        if "LIMITED" in str(msg).upper():
            raise AlioAPIError("일일 호출 한도 초과")
        raise AlioAPIError(f"공공데이터 API 오류 [{code}] {msg}")

    if isinstance(data, dict):
        _cache[cache_key] = (time.time(), data)
    return data


def list_institutions(
    *,
    page_no: int = 1,
    num_of_rows: int = 100,
    inst_cd: str | None = None,
) -> dict:
    """공공기관 정보 목록조회 GET /list"""
    params: dict[str, Any] = {"pageNo": page_no, "numOfRows": num_of_rows}
    if inst_cd:
        params["instCd"] = inst_cd
    return call_api(f"{PUBLIC_INST_BASE}/list", params)


def list_branches(
    *,
    inst_cd: str,
    page_no: int = 1,
    num_of_rows: int = 100,
) -> dict:
    """공공기관 지점 목록조회 GET /brnch"""
    return call_api(
        f"{PUBLIC_INST_BASE}/brnch",
        {"instCd": inst_cd, "pageNo": page_no, "numOfRows": num_of_rows},
    )


def fetch_all_institutions(*, page_size: int = 100) -> list[dict]:
    """전체 기관 목록 페이지네이션 수집."""
    first = list_institutions(page_no=1, num_of_rows=page_size)
    total = int(first.get("totalCount") or 0)
    rows = list(first.get("result") or [])
    page = 2
    while len(rows) < total:
        chunk = list_institutions(page_no=page, num_of_rows=page_size)
        batch = chunk.get("result") or []
        if not batch:
            break
        rows.extend(batch)
        page += 1
    return rows


def list_facilities(
    *,
    page_no: int = 1,
    num_of_rows: int = 10,
    mng_inst_cd: str | None = None,
    ctpv_nm: str | None = None,
    sgg_nm: str | None = None,
    fclt_type_cd: str | None = None,
    chagfee_yn: str | None = None,
    indr_se: str | None = None,
    inst_type: str | None = None,
    inst_clsf: str | None = None,
    weekdays_tm_yn: str | None = None,
    sat_tm_yn: str | None = None,
    hldy_tm_yn: str | None = None,
) -> dict:
    """시설정보 목록조회 GET /list"""
    params: dict[str, Any] = {"pageNo": page_no, "numOfRows": num_of_rows}
    optional = {
        "mngInstCd": mng_inst_cd,
        "ctpvNm": ctpv_nm,
        "sggNm": sgg_nm,
        "fcltTypeCd": fclt_type_cd,
        "chagfeeYn": chagfee_yn,
        "indrSe": indr_se,
        "instType": inst_type,
        "instClsf": inst_clsf,
        "weekdaysTmYn": weekdays_tm_yn,
        "satTmYn": sat_tm_yn,
        "hldyTmYn": hldy_tm_yn,
    }
    params.update({k: v for k, v in optional.items() if v})
    return call_api(f"{FACILITY_BASE}/list", params)


def get_facility_detail(*, sn: int | str) -> dict:
    """시설정보 상세조회 GET /detail (첨부파일 메타 포함)."""
    return call_api(f"{FACILITY_BASE}/detail", {"sn": sn})


def list_businesses(
    *,
    page_no: int = 1,
    num_of_rows: int = 10,
    inst_cd: str | None = None,
    biz_nm: str | None = None,
    biz_clsf: str | None = None,
    srvc_clsf: str | None = None,
    lifecycl_lst: str | None = None,
    inst_type: str | None = None,
    inst_clsf: str | None = None,
) -> dict:
    """사업정보 목록조회 GET /list"""
    params: dict[str, Any] = {"pageNo": page_no, "numOfRows": num_of_rows}
    optional = {
        "instCd": inst_cd,
        "bizNm": biz_nm,
        "bizClsf": biz_clsf,
        "srvcClsf": srvc_clsf,
        "lifecyclLst": lifecycl_lst,
        "instType": inst_type,
        "instClsf": inst_clsf,
    }
    params.update({k: v for k, v in optional.items() if v})
    return call_api(f"{BIZ_BASE}/list", params)


def list_recruitments(
    *,
    page_no: int = 1,
    num_of_rows: int = 10,
    pblnt_inst_cd: str | None = None,
    title: str | None = None,
    ongoing_yn: str | None = None,
    pbanc_bgng_ymd: str | None = None,
    pbanc_end_ymd: str | None = None,
    hire_type_lst: str | None = None,
    work_rgn_lst: str | None = None,
    acbg_cond_lst: str | None = None,
    recrut_se: str | None = None,
    replmpr_yn: str | None = None,
    inst_type: str | None = None,
    inst_clsf: str | None = None,
    ncs_cd_lst: str | None = None,
) -> dict:
    """채용공시 목록조회 GET /list"""
    params: dict[str, Any] = {"pageNo": page_no, "numOfRows": num_of_rows}
    optional = {
        "pblntInstCd": pblnt_inst_cd,
        "recrutPbancTtl": title,
        "ongoingYn": ongoing_yn,
        "pbancBgngYmd": pbanc_bgng_ymd,
        "pbancEndYmd": pbanc_end_ymd,
        "hireTypeLst": hire_type_lst,
        "workRgnLst": work_rgn_lst,
        "acbgCondLst": acbg_cond_lst,
        "recrutSe": recrut_se,
        "replmprYn": replmpr_yn,
        "instType": inst_type,
        "instClsf": inst_clsf,
        "ncsCdLst": ncs_cd_lst,
    }
    params.update({k: v for k, v in optional.items() if v})
    return call_api(f"{RECRUIT_BASE}/list", params)


def get_recruitment_detail(*, sn: int | str) -> dict:
    """채용공시 상세조회 GET /detail (전형단계·첨부파일 포함)."""
    return call_api(f"{RECRUIT_BASE}/detail", {"sn": sn})


def fetch_all_recruitments(
    *,
    ongoing_yn: str | None = "Y",
    page_size: int = 100,
    max_pages: int = 30,
) -> list[dict]:
    """진행중(기본) 채용공고 전수 수집 — 스냅샷·집계용."""
    first = list_recruitments(page_no=1, num_of_rows=page_size, ongoing_yn=ongoing_yn)
    total = int(first.get("totalCount") or 0)
    rows = list(first.get("result") or [])
    page = 2
    while len(rows) < total and page <= max_pages:
        chunk = list_recruitments(page_no=page, num_of_rows=page_size, ongoing_yn=ongoing_yn)
        batch = chunk.get("result") or []
        if not batch:
            break
        rows.extend(batch)
        page += 1
    return rows


def normalize_recruitment(row: dict) -> dict:
    """채용 API 응답 1건 → MCP 공통 스키마."""
    return {
        "recruitment_sn": row.get("recrutPblntSn"),
        "org_code": row.get("pblntInstCd"),
        "org_name": row.get("instNm"),
        "title": row.get("recrutPbancTtl"),
        "hire_type": row.get("hireTypeNmLst"),
        "recruit_type": row.get("recrutSeNm"),
        "headcount": row.get("recrutNope"),
        "work_region": row.get("workRgnNmLst"),
        "ncs": row.get("ncsCdNmLst"),
        "education": row.get("acbgCondNmLst"),
        "period_start": row.get("pbancBgngYmd"),
        "period_end": row.get("pbancEndYmd"),
        "ongoing": row.get("ongoingYn"),
        "days_remaining": row.get("decimalDay"),
        "apply_url": row.get("srcUrl"),
        "pref_conditions": row.get("prefCondCn"),
    }


def normalize_business(row: dict) -> dict:
    """사업 API 응답 1건 → MCP 공통 스키마."""
    return {
        "biz_sn": row.get("bizSn"),
        "org_code": row.get("instCd"),
        "org_name": row.get("instNm"),
        "name": row.get("bizNm"),
        "category": row.get("bizClsfNm"),
        "service_class": row.get("srvcClsfNm"),
        "description": row.get("bizExpln"),
        "target": row.get("utztnTrgtExpln"),
        "how_to_use": row.get("utztnMthdExpln"),
        "inquiry": row.get("utztnInqInfo"),
        "homepage": row.get("siteUrl"),
        "lifecycle": row.get("lifecyclNmLst"),
        "period": row.get("bizPeriodSeNm") or row.get("bizPeriodExpln"),
        "start_date": row.get("bgngYmd"),
        "end_date": row.get("endYmd"),
    }


_URL_RE = re.compile(r"https?://[^\s'\"<>)\]]+", re.IGNORECASE)


def _extract_urls(*texts: str | None) -> list[str]:
    """자유 텍스트(이용방법 등)에서 URL 추출 — 예약 링크 발굴용."""
    urls: list[str] = []
    for t in texts:
        if not t:
            continue
        for u in _URL_RE.findall(t):
            u = u.rstrip(".,;")
            if u not in urls:
                urls.append(u)
    return urls


def _reservation_channels(row: dict) -> list[str]:
    """rsvtMthd*Yn 플래그 → 예약 채널 목록."""
    mapping = [
        ("rsvtMthdSiteYn", "site"),
        ("rsvtMthdTelYn", "tel"),
        ("rsvtMthdEmlYn", "email"),
        ("rsvtMthdDocYn", "document"),
        ("rsvtMthdEtcYn", "etc"),
    ]
    return [label for key, label in mapping if row.get(key) == "Y"]


def normalize_facility(row: dict) -> dict:
    """시설 API 응답 1건 → MCP 공통 스키마."""
    site_url = (row.get("siteUrl") or "").strip() or None
    extracted = _extract_urls(row.get("utztnMthdExpln"), row.get("rsvtMthdExpln"))
    booking_links = list(dict.fromkeys(([site_url] if site_url else []) + extracted))
    hours = {
        "weekdays": row.get("weekdaysTmExpln"),
        "saturday": row.get("satTmExpln"),
        "holiday": row.get("hldyTmExpln"),
        "closed": row.get("tcbizDayInfo"),
    }
    files = row.get("files") or []
    return {
        "facility_sn": row.get("fcltSn"),
        "org_code": row.get("mngInstCd"),
        "org_name": row.get("instNm"),
        "name": row.get("fcltNm"),
        "type": row.get("fcltTypeNm"),
        "type_full": row.get("fcltTypeFullNm"),
        "type_code": row.get("fcltTypeCd"),
        "location": " ".join(
            x for x in ((row.get("ctpvNm") or "").strip(), (row.get("sggNm") or "").strip()) if x
        ),
        "address": row.get("roadNmAddr") or row.get("lotnoAddr"),
        "address_detail": row.get("daddr"),
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "indoor_outdoor": row.get("indrSeExpln") or row.get("indrSe"),
        "fee_yn": row.get("chagfeeYn"),
        "fee_info": row.get("utztnPayExpln"),
        "capacity": row.get("acptNopeExpln"),
        "hours": {k: v for k, v in hours.items() if v},
        "reservation": {
            "available_yn": row.get("rsvtPsbltyYn"),
            "channels": _reservation_channels(row),
            "how_to": row.get("rsvtMthdExpln"),
            "links": booking_links,
        },
        "contact": row.get("picTelno"),
        "contact_email": row.get("picEml"),
        "site_url": site_url,
        "usage_target": row.get("utztnTrgtExpln"),
        "usage_method": row.get("utztnMthdExpln"),
        "images": [
            f.get("url") for f in files if isinstance(f, dict) and f.get("fileSe") == "I"
        ],
    }


def normalize_institution(row: dict) -> dict:
    """API 응답 1건 → MCP 공통 스키마."""
    ctpv = (row.get("ctpvNm") or "").strip()
    sgg = (row.get("sggNm") or "").strip()
    location = " ".join(x for x in (ctpv, sgg) if x)
    return {
        "org_code": row.get("instCd"),
        "std_org_code": row.get("pbadmsStdInstCd"),
        "name": row.get("instNm"),
        "org_type": row.get("instTypeNm") or row.get("instType"),
        "ministry": row.get("sprvsnInstNm"),
        "location": location,
        "address": row.get("roadNmAddr") or row.get("lotnoAddr"),
        "homepage": row.get("siteUrl"),
        "phone": row.get("rprsTelno"),
        "founded": row.get("fndnYmd"),
    }

"""KONEPS (나라장터, Korea Public Procurement Service) construction bid notices via data.go.kr.

Uses 조달청_나라장터 입찰공고정보서비스 (BidPublicInfoService), the ``ad/`` endpoint
that replaced the retired ``BidPublicInfoService04`` (which now returns code 12).
The API accepts at most about one month per request, so longer ranges are split.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ._common import ApiError, data_go_kr_error, data_go_kr_key, http_get, today

BID_SEARCH_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwkPPSSrch"
WINDOW_DAYS = 28
PAGE_ROWS = 100
MAX_DAYS = 92


def _parse_day(s: str) -> date:
    s = s.replace("-", "").replace(".", "").strip()
    try:
        return datetime.strptime(s[:8], "%Y%m%d").date()
    except ValueError as e:
        raise ApiError(f"Dates must be YYYY-MM-DD or YYYYMMDD, got '{s}'") from e


def windows(start: date, end: date, size: int = WINDOW_DAYS) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive windows of at most `size` days, newest first."""
    if end < start:
        raise ApiError("end_date is before start_date")
    if (end - start).days > MAX_DAYS:
        raise ApiError(f"Date range is limited to {MAX_DAYS} days per call to protect the daily quota")
    out = []
    cur_end = end
    while cur_end >= start:
        cur_start = max(start, cur_end - timedelta(days=size - 1))
        out.append((cur_start, cur_end))
        cur_end = cur_start - timedelta(days=1)
    return out


def _won(v: Any) -> int | None:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def summarize(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "notice_no": f"{item.get('bidNtceNo')}-{item.get('bidNtceOrd')}",
        "title": item.get("bidNtceNm"),
        "notice_agency": item.get("ntceInsttNm"),
        "demand_agency": item.get("dminsttNm"),
        "site_region": item.get("cnstrtsiteRgnNm"),
        "posted": item.get("bidNtceDt"),
        "bid_close": item.get("bidClseDt"),
        "opening": item.get("opengDt"),
        "estimated_price_krw": _won(item.get("presmptPrce")),
        "budget_krw": _won(item.get("bdgtAmt")),
        "contract_method": item.get("cntrctCnclsMthdNm"),
        "award_method": item.get("sucsfbidMthdNm"),
        "kind": item.get("ntceKindNm"),
        "url": item.get("bidNtceDtlUrl") or item.get("bidNtceUrl"),
    }


def _fetch_window(keyword: str, start: date, end: date, rows: int) -> tuple[list[dict], int]:
    params = {
        "serviceKey": data_go_kr_key(), "type": "json", "numOfRows": rows, "pageNo": 1,
        "inqryDiv": "1",  # by notice registration date
        "inqryBgnDt": start.strftime("%Y%m%d") + "0000",
        "inqryEndDt": end.strftime("%Y%m%d") + "2359",
        "bidNtceNm": keyword,
    }
    resp = http_get(BID_SEARCH_URL, params)
    try:
        data = resp.json()
    except ValueError as e:
        raise ApiError(f"KONEPS returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}") from e
    if "OpenAPI_ServiceResponse" in data:
        h = data["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        raise data_go_kr_error(h.get("returnReasonCode"), h.get("returnAuthMsg") or h.get("errMsg"))
    if "response" not in data:  # e.g. {"nkoneps.com.response.ResponseError": {...}}
        err = next(iter(data.values()), {}).get("header", {}) if data else {}
        raise data_go_kr_error(err.get("resultCode"), err.get("resultMsg"))
    header = data["response"].get("header", {})
    if header.get("resultCode") not in ("00", None):
        raise data_go_kr_error(header.get("resultCode"), header.get("resultMsg"))
    body = data["response"].get("body", {}) or {}
    items = body.get("items") or []
    if isinstance(items, dict):  # some gateways wrap a single item
        items = items.get("item", [])
        items = items if isinstance(items, list) else [items]
    return items, int(body.get("totalCount") or 0)


def search_construction_bids(keyword: str, start_date: str = "", end_date: str = "",
                             region: str = "", max_results: int = 20) -> dict[str, Any]:
    if not keyword.strip():
        raise ApiError("keyword is required (공고명에 들어갈 낱말)")
    end = _parse_day(end_date) if end_date else date.today()
    start = _parse_day(start_date) if start_date else end - timedelta(days=29)
    max_results = max(1, min(int(max_results), 100))
    found: list[dict[str, Any]] = []
    total = 0
    for ws, we in windows(start, end):
        items, n = _fetch_window(keyword, ws, we, rows=PAGE_ROWS)
        total += n
        found.extend(summarize(i) for i in items)
    scanned = len(found)
    if region:
        found = [f for f in found if region in (f.get("site_region") or "") or region in (f.get("demand_agency") or "")]
    found.sort(key=lambda f: f.get("posted") or "", reverse=True)
    result: dict[str, Any] = {
        "keyword": keyword, "from": start.isoformat(), "to": end.isoformat(), "region_filter": region or None,
        "total_matching_notices": total, "returned": min(len(found), max_results),
        "notices": found[:max_results],
        "source": f"조달청 나라장터 입찰공고정보서비스(공공데이터포털), 조회일 {today()}",
    }
    if total > scanned:
        result["note"] = (f"{total} notices matched but only the first {PAGE_ROWS} per ~4-week window "
                          f"({scanned}) were scanned. Use a more specific keyword or a shorter range.")
    return result

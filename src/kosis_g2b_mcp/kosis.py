"""KOSIS (Korean Statistical Information Service, 국가통계포털) Open API client.

Three generic calls cover any KOSIS table:
  search_tables  -> find a table (org_id, tbl_id)
  table_meta     -> list its item and classification codes and available periods
  get_series     -> fetch the actual values

Two presets sit on top for the series public-investment analysts use most:
consumer price index (by region) and construction cost index (by sector).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ._common import ApiError, http_get, kosis_key, today

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL = "https://kosis.kr/openapi/statisticsData.do"
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# Presets (verified 2026-10)
CPI_TABLE = ("101", "DT_1J22003", "T")            # 소비자물가지수(2020=100), 총지수, 시도별
CCI_TABLE = ("397", "DT_39701_A003", "16397AAA0")  # 건설공사비지수(2020=100), 업종별

PERIOD_TYPES = {"M": "monthly", "Q": "quarterly", "Y": "yearly"}


def _call(url: str, params: dict[str, Any]) -> Any:
    resp = http_get(url, {**params, "apiKey": kosis_key(), "format": "json", "jsonVD": "Y"})
    text = resp.text.strip()
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ApiError(f"KOSIS returned non-JSON (HTTP {resp.status_code}): {text[:200]}") from e
    if isinstance(data, dict) and data.get("err"):
        raise ApiError(f"KOSIS error {data.get('err')}: {data.get('errMsg')}")
    return data


def search_tables(keyword: str, max_results: int = 10) -> list[dict[str, Any]]:
    rows = _call(SEARCH_URL, {"method": "getList", "searchNm": keyword, "resultCount": str(max_results)})
    out = []
    for r in rows[:max_results]:
        out.append({
            "org_id": r.get("ORG_ID"), "org_name": r.get("ORG_NM"),
            "tbl_id": r.get("TBL_ID"), "tbl_name": r.get("TBL_NM"),
            "period": f"{r.get('STRT_PRD_DE')}~{r.get('END_PRD_DE')}",
            "path": r.get("MT_ATITLE"),
        })
    return out


def table_meta(org_id: str, tbl_id: str, name_filter: str = "", max_codes: int = 60) -> dict[str, Any]:
    items = _call(META_URL, {"method": "getMeta", "type": "ITM", "orgId": org_id, "tblId": tbl_id})
    periods = _call(META_URL, {"method": "getMeta", "type": "PRD", "orgId": org_id, "tblId": tbl_id})
    groups: dict[str, dict[str, Any]] = {}
    want = name_filter.replace(" ", "")
    for r in items:
        if want and r.get("OBJ_ID") != "ITEM" and want not in (r.get("ITM_NM") or "").replace(" ", ""):
            continue
        g = groups.setdefault(r.get("OBJ_ID"), {"obj_id": r.get("OBJ_ID"), "obj_name": r.get("OBJ_NM"), "codes": []})
        g["codes"].append({"code": r.get("ITM_ID"), "name": r.get("ITM_NM"), "parent": r.get("UP_ITM_ID")})
    dims = []
    for g in groups.values():
        total = len(g["codes"])
        g["codes"] = g["codes"][:max_codes]
        g["total_codes"] = total
        dims.append(g)
    return {
        "org_id": org_id, "tbl_id": tbl_id,
        "dimensions": dims,
        "periods": [{"type": p.get("PRD_SE"), "from": p.get("STRT_PRD_DE"), "to": p.get("END_PRD_DE")} for p in periods],
        "note": "The dimension with obj_id 'ITEM' gives item_id; the others, in order, give obj_l1, obj_l2, ... "
                "If a dimension shows fewer codes than total_codes, call again with name_filter.",
    }


def _default_range(period_type: str) -> tuple[str, str]:
    d = date.today()
    if period_type == "Y":
        return str(d.year - 5), str(d.year)
    if period_type == "Q":
        return f"{d.year - 2}1", f"{d.year}4"
    start = date(d.year - 1, d.month, 1)
    return start.strftime("%Y%m"), d.strftime("%Y%m")


def get_series(org_id: str, tbl_id: str, item_id: str, obj_l1: str = "", obj_l2: str = "", obj_l3: str = "",
               period_type: str = "M", start: str = "", end: str = "") -> dict[str, Any]:
    period_type = (period_type or "M").upper()
    if period_type not in PERIOD_TYPES:
        raise ApiError(f"period_type must be one of {list(PERIOD_TYPES)}")
    if not start or not end:
        ds, de = _default_range(period_type)
        start, end = start or ds, end or de
    params = {"method": "getList", "orgId": org_id, "tblId": tbl_id, "itmId": item_id,
              "prdSe": period_type, "startPrdDe": start, "endPrdDe": end}
    for i, v in enumerate([obj_l1, obj_l2, obj_l3], start=1):
        if v:
            params[f"objL{i}"] = v
    rows = _call(DATA_URL, params)
    if not rows:
        raise ApiError("KOSIS returned no rows. Check codes with kosis_table_meta and the period format "
                       "(M: YYYYMM, Q: YYYYQ, Y: YYYY).")
    first = rows[0]
    series = []
    for r in rows:
        labels = [r.get(f"C{i}_NM") for i in range(1, 5) if r.get(f"C{i}_NM")]
        series.append({"period": r.get("PRD_DE"), "value": _num(r.get("DT")), "labels": labels})
    return {
        "table": first.get("TBL_NM"), "item": first.get("ITM_NM"), "unit": first.get("UNIT_NM"),
        "period_type": PERIOD_TYPES[period_type],
        "series": series,
        "last_updated": max((r.get("LST_CHN_DE") or "" for r in rows), default=None),
        "source": f"KOSIS 국가통계포털, {first.get('TBL_NM')} (orgId {org_id}, tblId {tbl_id}), 조회일 {today()}",
    }


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _match_code(org_id: str, tbl_id: str, name: str, obj_id: str | None = None) -> tuple[str, str]:
    meta = _call(META_URL, {"method": "getMeta", "type": "ITM", "orgId": org_id, "tblId": tbl_id})
    cands = [r for r in meta if r.get("OBJ_ID") != "ITEM" and (obj_id is None or r.get("OBJ_ID") == obj_id)]
    want = name.replace(" ", "")
    for exact in (True, False):
        for r in cands:
            nm = (r.get("ITM_NM") or "").replace(" ", "")
            if (nm == want) if exact else (want in nm):
                return r.get("ITM_ID"), r.get("ITM_NM")
    choices = ", ".join(sorted({r.get("ITM_NM") for r in cands})[:40])
    raise ApiError(f"'{name}' not found. Choices: {choices}")


def cpi(region: str = "전국", start: str = "", end: str = "", period_type: str = "M") -> dict[str, Any]:
    org, tbl, item = CPI_TABLE
    code, nm = _match_code(org, tbl, region)
    out = get_series(org, tbl, item, obj_l1=code, period_type=period_type, start=start, end=end)
    out["region"] = nm
    return out


def construction_cost_index(sector: str = "건설", start: str = "", end: str = "") -> dict[str, Any]:
    org, tbl, item = CCI_TABLE
    code, nm = _match_code(org, tbl, sector)
    out = get_series(org, tbl, item, obj_l1=code, period_type="M", start=start, end=end)
    out["sector"] = nm
    return out

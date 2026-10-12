"""MCP server exposing Korean public statistics (KOSIS) and procurement bids (KONEPS).

Run:  kosis-g2b-mcp            (stdio transport)
      python -m kosis_g2b_mcp
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__, g2b, kosis
from ._common import ApiError, load_env

load_env()

mcp = FastMCP(
    "kosis-g2b",
    instructions=(
        "Korean public data for public-investment analysis. "
        "Use kosis_cpi / kosis_construction_cost_index for the two most common series; "
        "for any other KOSIS table: kosis_search_tables -> kosis_table_meta -> kosis_get_series. "
        "Use g2b_search_construction_bids for recent construction bid notices on 나라장터. "
        "Every result carries a 'source' line; quote it when you cite a number."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _run(fn: Callable[..., Any], **kwargs: Any) -> str:
    try:
        return json.dumps(fn(**kwargs), ensure_ascii=False, indent=1)
    except ApiError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------- KOSIS

@mcp.tool(annotations=READ_ONLY)
def kosis_search_tables(
    keyword: Annotated[str, Field(description="Statistic name in Korean, e.g. '소비자물가지수', '건설공사비지수', '주민등록인구'")],
    max_results: Annotated[int, Field(ge=1, le=50)] = 10,
) -> str:
    """Search KOSIS (국가통계포털) for statistical tables. Returns org_id/tbl_id to use with kosis_table_meta."""
    return _run(kosis.search_tables, keyword=keyword, max_results=max_results)


@mcp.tool(annotations=READ_ONLY)
def kosis_table_meta(
    org_id: Annotated[str, Field(description="KOSIS organization id, e.g. '101' (통계청)")],
    tbl_id: Annotated[str, Field(description="KOSIS table id, e.g. 'DT_1J22003'")],
    name_filter: Annotated[str, Field(description="Keep only classification codes whose name contains this, e.g. '부산'")] = "",
) -> str:
    """List a KOSIS table's item codes, classification codes (obj_l1, obj_l2, ...) and available periods."""
    return _run(kosis.table_meta, org_id=org_id, tbl_id=tbl_id, name_filter=name_filter)


@mcp.tool(annotations=READ_ONLY)
def kosis_get_series(
    org_id: str,
    tbl_id: str,
    item_id: Annotated[str, Field(description="Code from the 'ITEM' dimension of kosis_table_meta")],
    obj_l1: Annotated[str, Field(description="Code of the 1st classification dimension")] = "",
    obj_l2: Annotated[str, Field(description="Code of the 2nd classification dimension, if any")] = "",
    obj_l3: Annotated[str, Field(description="Code of the 3rd classification dimension, if any")] = "",
    period_type: Annotated[str, Field(description="M (monthly), Q (quarterly) or Y (yearly)")] = "M",
    start: Annotated[str, Field(description="M: YYYYMM, Q: YYYYQ, Y: YYYY. Default: last 12 months / 2 years / 5 years")] = "",
    end: str = "",
) -> str:
    """Fetch actual values from any KOSIS table as a time series, with unit and a citation line."""
    return _run(kosis.get_series, org_id=org_id, tbl_id=tbl_id, item_id=item_id, obj_l1=obj_l1,
                obj_l2=obj_l2, obj_l3=obj_l3, period_type=period_type, start=start, end=end)


@mcp.tool(annotations=READ_ONLY)
def kosis_cpi(
    region: Annotated[str, Field(description="'전국' or a province/city name, e.g. '부산광역시', '서울'")] = "전국",
    start: Annotated[str, Field(description="YYYYMM (monthly) or YYYY (yearly). Default: last 12 months")] = "",
    end: str = "",
    period_type: Annotated[str, Field(description="M or Y")] = "M",
) -> str:
    """Consumer price index (소비자물가지수, 2020=100, all items) by region from Statistics Korea."""
    return _run(kosis.cpi, region=region, start=start, end=end, period_type=period_type)


@mcp.tool(annotations=READ_ONLY)
def kosis_construction_cost_index(
    sector: Annotated[str, Field(description="'건설' (all), '건물건설 및 건축보수', '토목건설', '도로시설', '철도시설', '상하수도시설' ...")] = "건설",
    start: Annotated[str, Field(description="YYYYMM. Default: last 12 months")] = "",
    end: str = "",
) -> str:
    """Construction cost index (건설공사비지수, 2020=100, KICT) by sector, monthly. Used for cost escalation."""
    return _run(kosis.construction_cost_index, sector=sector, start=start, end=end)


# ---------------------------------------------------------------- KONEPS (나라장터)

@mcp.tool(annotations=READ_ONLY)
def g2b_search_construction_bids(
    keyword: Annotated[str, Field(description="Word in the notice title, e.g. '하수처리', '도시철도', '터널'")],
    start_date: Annotated[str, Field(description="YYYY-MM-DD. Default: 30 days before end_date")] = "",
    end_date: Annotated[str, Field(description="YYYY-MM-DD. Default: today. Range up to 92 days")] = "",
    region: Annotated[str, Field(description="Optional filter on site region or demand agency, e.g. '부산'")] = "",
    max_results: Annotated[int, Field(ge=1, le=100)] = 20,
) -> str:
    """Search construction bid notices (공사 입찰공고) on KONEPS/나라장터 by title keyword and date.

    Returns agency, site region, estimated price and budget (KRW), bid close/opening dates and the notice URL.
    """
    return _run(g2b.search_construction_bids, keyword=keyword, start_date=start_date, end_date=end_date,
                region=region, max_results=max_results)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

__all__ = ["mcp", "main", "__version__"]

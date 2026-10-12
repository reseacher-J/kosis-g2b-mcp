"""Offline tests: no API keys or network needed.  Run: python -m unittest discover tests"""

import json
import os
import unittest
from datetime import date
from unittest import mock

os.environ.setdefault("KOSIS_API_KEY", "test-key")
os.environ.setdefault("DATA_GO_KR_KEY", "abc%2Bdef%3D%3D")

from kosis_g2b_mcp import _common, g2b, kosis, server  # noqa: E402


class FakeResp:
    def __init__(self, payload, status=200):
        self.text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        self.status_code = status

    def json(self):
        return json.loads(self.text)


class KeyTests(unittest.TestCase):
    def test_encoded_service_key_is_decoded(self):
        self.assertEqual(_common.data_go_kr_key(), "abc+def==")

    def test_missing_key_message(self):
        with mock.patch.dict(os.environ, {"KOSIS_API_KEY": "your_kosis_api_key_here"}):
            with self.assertRaises(_common.ApiError):
                _common.kosis_key()


class KosisTests(unittest.TestCase):
    ROWS = [
        {"PRD_DE": "202607", "DT": "119.58", "C1_NM": "부산광역시", "TBL_NM": "소비자물가지수(2020＝100)",
         "ITM_NM": "소비자물가지수(총지수)", "UNIT_NM": "2020＝100", "LST_CHN_DE": "2026-08-03"},
        {"PRD_DE": "202608", "DT": "119.8", "C1_NM": "부산광역시", "TBL_NM": "소비자물가지수(2020＝100)",
         "ITM_NM": "소비자물가지수(총지수)", "UNIT_NM": "2020＝100", "LST_CHN_DE": "2026-09-02"},
    ]

    def test_series_parsing(self):
        with mock.patch.object(kosis, "http_get", return_value=FakeResp(self.ROWS)):
            out = kosis.get_series("101", "DT_1J22003", "T", obj_l1="T12", start="202607", end="202608")
        self.assertEqual([p["value"] for p in out["series"]], [119.58, 119.8])
        self.assertEqual(out["last_updated"], "2026-09-02")
        self.assertIn("tblId DT_1J22003", out["source"])

    def test_kosis_error_payload(self):
        with mock.patch.object(kosis, "http_get", return_value=FakeResp({"err": "21", "errMsg": "잘못된 요청 변수"})):
            with self.assertRaises(_common.ApiError) as cm:
                kosis.get_series("101", "X", "T", start="202601", end="202602")
        self.assertIn("21", str(cm.exception))

    def test_region_matching_prefers_exact_then_partial(self):
        meta = [{"OBJ_ID": "ITEM", "ITM_ID": "T", "ITM_NM": "총지수"},
                {"OBJ_ID": "C", "ITM_ID": "T10", "ITM_NM": "전국"},
                {"OBJ_ID": "C", "ITM_ID": "T12", "ITM_NM": "부산광역시"}]
        with mock.patch.object(kosis, "http_get", return_value=FakeResp(meta)):
            self.assertEqual(kosis._match_code("101", "t", "부산"), ("T12", "부산광역시"))
            self.assertEqual(kosis._match_code("101", "t", "전국"), ("T10", "전국"))
            with self.assertRaises(_common.ApiError):
                kosis._match_code("101", "t", "화성시")


class G2bTests(unittest.TestCase):
    def test_windows_cover_range_without_gaps(self):
        ws = g2b.windows(date(2026, 8, 1), date(2026, 10, 12))
        self.assertEqual(ws[0][1], date(2026, 10, 12))
        self.assertEqual(ws[-1][0], date(2026, 8, 1))
        for (a_start, _), (_, b_end) in zip(ws, ws[1:]):
            self.assertEqual((a_start - b_end).days, 1)
        self.assertTrue(all((e - s).days < g2b.WINDOW_DAYS for s, e in ws))

    def test_range_limit(self):
        with self.assertRaises(_common.ApiError):
            g2b.windows(date(2026, 1, 1), date(2026, 10, 12))

    def test_code_30_is_explained(self):
        payload = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
            "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "returnAuthMsg": "등록되지 않은 서비스키",
            "returnReasonCode": "30"}}}
        with mock.patch.object(g2b, "http_get", return_value=FakeResp(payload, 403)):
            with self.assertRaises(_common.ApiError) as cm:
                g2b._fetch_window("터널", date(2026, 10, 1), date(2026, 10, 12), 10)
        self.assertIn("활용신청", str(cm.exception))

    def test_search_summarizes_and_filters_region(self):
        payload = {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 2, "items": [
            {"bidNtceNo": "A1", "bidNtceOrd": "000", "bidNtceNm": "하수관로 신설", "cnstrtsiteRgnNm": "부산광역시",
             "dminsttNm": "부산광역시 건설본부", "bidNtceDt": "2026-09-17 09:42:05", "presmptPrce": "30032053637"},
            {"bidNtceNo": "A2", "bidNtceOrd": "000", "bidNtceNm": "하수처리장 개량", "cnstrtsiteRgnNm": "경기도",
             "dminsttNm": "수원시", "bidNtceDt": "2026-09-20 10:00:00", "presmptPrce": "1000"}]}}}
        with mock.patch.object(g2b, "http_get", return_value=FakeResp(payload)):
            out = json.loads(server.g2b_search_construction_bids(
                "하수", start_date="2026-09-15", end_date="2026-10-12", region="부산"))
        self.assertEqual(out["returned"], 1)
        self.assertEqual(out["notices"][0]["estimated_price_krw"], 30032053637)
        self.assertEqual(out["notices"][0]["notice_no"], "A1-000")

    def test_tool_returns_error_json_instead_of_raising(self):
        out = json.loads(server.g2b_search_construction_bids("  "))
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()

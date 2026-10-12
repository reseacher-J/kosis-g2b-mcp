# kosis-g2b-mcp

**공공투자 분석을 위한 MCP 서버** — Claude 같은 AI가 국가통계포털(KOSIS)의 물가·공사비 통계와
조달청 나라장터의 공사 입찰공고를 **직접 조회**하게 해 줍니다.

[![test](https://github.com/reseacher-J/kosis-g2b-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/reseacher-J/kosis-g2b-mcp/actions/workflows/test.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

> *An MCP server that lets AI assistants query Korean public data for public-investment analysis:
> KOSIS statistics (CPI, construction cost index, or any KOSIS table) and construction bid notices on KONEPS (나라장터).
> English summary [below](#english).*

---

## 왜 만들었나

타당성조사·투자심사·민간투자사업 검토를 하다 보면 같은 숫자를 계속 찾습니다.

- 사업비를 현재가로 바꿀 **건설공사비지수**와 **소비자물가지수**
- 비슷한 시설이 **얼마에 발주됐는지**(나라장터 추정가격·배정예산)

매번 사이트에 들어가 표를 내려받는 대신, AI에게 *「부산 소비자물가지수 최근 1년」*,
*「최근 두 달 부산 하수관로 공사 입찰공고」*라고 물으면 **출처가 붙은 값**이 바로 돌아오게 만든 도구입니다.

## 도구 (Tools)

| 도구 | 하는 일 | 필요한 키 |
|---|---|---|
| `kosis_cpi` | 소비자물가지수(2020=100, 총지수) — 전국·시도별, 월·연 | KOSIS |
| `kosis_construction_cost_index` | 건설공사비지수(2020=100, 한국건설기술연구원) — 건설 전체·토목·도로·철도·상하수도 등 업종별, 월 | KOSIS |
| `kosis_search_tables` | KOSIS 통계표 검색 → `org_id`·`tbl_id` | KOSIS |
| `kosis_table_meta` | 그 표의 항목·분류 코드와 수록 기간 | KOSIS |
| `kosis_get_series` | **어떤 KOSIS 표든** 실제 값을 시계열로 | KOSIS |
| `g2b_search_construction_bids` | 나라장터 **공사 입찰공고** 검색 — 공고명 낱말·기간·지역, 추정가격·배정예산·개찰일·공고 주소 | 공공데이터포털 |

모든 결과에는 `source` 한 줄이 붙습니다. 예 : `KOSIS 국가통계포털, 소비자물가지수(2020＝100) (orgId 101, tblId DT_1J22003), 조회일 2026-10-12`.
**숫자를 인용할 때 출처를 함께 적을 수 있게** 하려는 설계입니다.

### 이렇게 물어보면 됩니다

```text
부산 소비자물가지수를 2025년 1월부터 최근까지 보여 줘
철도시설 건설공사비지수가 최근 12개월 동안 몇 % 올랐어?
최근 60일 동안 부산에서 나온 '하수' 공사 입찰공고를 추정가격 큰 순으로 정리해 줘
KOSIS에서 '주민등록인구' 표를 찾아서 부산광역시 연도별 인구를 가져와 줘
```

## 설치

### 1) API 키 받기 (둘 다 무료)

| 키 | 어디서 | 메모 |
|---|---|---|
| `KOSIS_API_KEY` | [KOSIS 공유서비스](https://kosis.kr/openapi/) | 회원가입 → 인증키 신청 |
| `DATA_GO_KR_KEY` | [공공데이터포털](https://www.data.go.kr/) | **「조달청_나라장터 입찰공고정보서비스」 활용신청** · Encoding·Decoding 키 어느 쪽이든 됩니다 |

### 2) Claude Code

```bash
claude mcp add kosis-g2b \
  -e KOSIS_API_KEY=발급받은키 -e DATA_GO_KR_KEY=발급받은키 \
  -- uvx --from git+https://github.com/reseacher-J/kosis-g2b-mcp kosis-g2b-mcp
```

### 3) Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "kosis-g2b": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/reseacher-J/kosis-g2b-mcp", "kosis-g2b-mcp"],
      "env": { "KOSIS_API_KEY": "발급받은키", "DATA_GO_KR_KEY": "발급받은키" }
    }
  }
}
```

> [`uv`](https://docs.astral.sh/uv/)가 없으면 `git clone` 뒤 `pip install .` 하고 `command`를 `kosis-g2b-mcp`로 두면 됩니다.
> 키는 환경 변수 대신 저장소 폴더의 `.env`에 둘 수도 있습니다(`.env.example` 참고).

## 알아 두면 좋은 것 (실측)

- **나라장터 API는 한 번에 약 한 달까지만 받습니다.** 기간이 길면 서버가 4주씩 나눠 부르고, 하루 호출량을 아끼려고 **최대 92일**로 막았습니다.
- 옛 주소 `BidPublicInfoService04`는 이제 **오류 12(서비스 없음)** 를 돌려줍니다. 이 서버는 바뀐 `ad/BidPublicInfoService`를 씁니다.
- 공공데이터포털 **Encoding 키를 그대로 넘기면 이중 인코딩되어 「등록되지 않은 서비스키」(오류 30)** 가 납니다. 서버가 알아서 디코딩합니다.
  오류 30이 계속되면 그 서비스를 **활용신청**했는지 확인하십시오.
- 오류 메시지는 공공데이터포털 공통 코드를 풀어 **무엇을 고치면 되는지** 함께 돌려줍니다.

## 개발

```bash
git clone https://github.com/reseacher-J/kosis-g2b-mcp && cd kosis-g2b-mcp
pip install -e .
python -m unittest discover -s tests -v     # 키·네트워크 없이 도는 시험
npx @modelcontextprotocol/inspector kosis-g2b-mcp   # 도구를 화면에서 눌러 보기
```

```
src/kosis_g2b_mcp/
├─ server.py    MCP 도구 정의(FastMCP · 모두 읽기 전용)
├─ kosis.py     KOSIS : 검색 → 메타 → 값, 물가·공사비 프리셋
├─ g2b.py       나라장터 : 기간 나누기 · 요약 · 지역 필터
└─ _common.py   키 · HTTP · 오류 코드 풀이 · 출처 줄
```

### 다음에 넣을 것

- 나라장터 **낙찰·계약 정보**(`ScsbidInfoService`·`CntrctInfoService`) — 주소는 살아 있음을 확인했고, 별도 활용신청 뒤 붙입니다
- 한국은행 ECOS(금리·생산자물가) 도구

## 만든 사람

**정박사의 공공투자연구소** — 타당성조사·투자심사·민간투자사업을 다루는 공공투자 분야 연구자의 작업 공간입니다.
블로그 : <https://blog.naver.com/pmisjeong>
· 이 도구를 만든 과정 : [「kosis-g2b-mcp : 통계청·나라장터 조회 MCP」](https://blog.naver.com/pmisjeong/224439265268)

이 도구는 공개 API를 부르는 개인 프로젝트이며, 통계청·조달청·한국건설기술연구원과 무관합니다.
값을 보고서에 쓸 때는 원 통계표에서 한 번 더 확인하십시오.

---

## English

**kosis-g2b-mcp** is a Model Context Protocol server for Korean public-investment analysis.

- **KOSIS** (Statistics Korea portal): consumer price index by region, construction cost index by sector,
  plus generic `search → meta → series` tools that reach any KOSIS table.
- **KONEPS / 나라장터** (Public Procurement Service): search construction bid notices by title keyword,
  date range (auto-split into 4-week windows, max 92 days) and region; returns agency, estimated price,
  budget, bid dates and notice URL.
- Every result includes a `source` citation line. All tools are read-only.
- Free API keys: [KOSIS](https://kosis.kr/openapi/) and [data.go.kr](https://www.data.go.kr/)
  (apply for *조달청_나라장터 입찰공고정보서비스*).

```bash
claude mcp add kosis-g2b -e KOSIS_API_KEY=... -e DATA_GO_KR_KEY=... \
  -- uvx --from git+https://github.com/reseacher-J/kosis-g2b-mcp kosis-g2b-mcp
```

Background story (Korean): <https://blog.naver.com/pmisjeong/224439265268>

MIT License.

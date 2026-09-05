"""국내주식/지수 KIS API 연동 (해외주식과 별개 API 패밀리).

해외주식 API(kis_client.py)는 BYMD 커서 기반 페이지네이션을 쓰지만, 국내
API는 날짜범위(FID_INPUT_DATE_1/2)로 조회하고 1회 최대 100건을 "최신순"으로
반환한다(2026-09 실제 호출로 확인: 1년 범위를 요청해도 최근 100건만 오고
더 과거는 잘림) - 그래서 "가장 오래된 응답일의 전날"을 다음 요청의 종료일로
옮기며 페이지네이션한다.

인증/레이트리미터는 kis_client.py 것을 그대로 재사용한다(국내/해외 API를
합쳐서 전체 호출속도를 안전선 아래로 유지해야 하므로 리미터 인스턴스를
공유해야 함).
"""

import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

import kis_auth as ka
from signal_bot import kis_client as kc

ITEM_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
ITEM_TR = "FHKST03010100"
INDEX_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
INDEX_TR = "FHKUP03500100"

MAX_PAGES = 60
FAR_PAST_DATE = "19900101"

# KOSPI200 = 업종코드 "2001" (2026-09 API 호출로 hts_kor_isnm="KOSPI200" 확인됨,
# FID_COND_MRKT_DIV_CODE="U" 기준. 참고: "0001"=코스피종합, "1001"=코스닥종합).
KR_INDEX_CODES = {"KOSPI200": "2001"}

_ITEM_COLUMN_MAP = {
    "stck_bsop_date": "date", "stck_clpr": "close", "stck_oprc": "open",
    "stck_hgpr": "high", "stck_lwpr": "low", "acml_vol": "volume",
}
_INDEX_COLUMN_MAP = {
    "stck_bsop_date": "date", "bstp_nmix_prpr": "close", "bstp_nmix_oprc": "open",
    "bstp_nmix_hgpr": "high", "bstp_nmix_lwpr": "low", "acml_vol": "volume",
}
_NUMERIC_COLS = ["close", "open", "high", "low", "volume"]


def _fetch_pages_kr(kind: str, symb: str, min_rows: int) -> Optional[pd.DataFrame]:
    rows: list[dict] = []
    date2 = datetime.now().strftime("%Y%m%d")

    # 종목(item) API는 1회 최대 100건, 지수(index) API는 1회 최대 50건 반환한다
    # (2026-09 실제 호출로 확인 - 문서상 "최대 100건"은 item 기준이고 index는
    # 더 적게 온다). 이 값보다 적게 오면 더 과거 데이터가 없다는 뜻으로 간주.
    page_cap = 100 if kind == "item" else 50

    for _ in range(MAX_PAGES):
        if kind == "index":
            params = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": KR_INDEX_CODES.get(symb, symb),
                "FID_INPUT_DATE_1": FAR_PAST_DATE, "FID_INPUT_DATE_2": date2,
                "FID_PERIOD_DIV_CODE": "D",
            }
            url, tr_id, col_map = INDEX_URL, INDEX_TR, _INDEX_COLUMN_MAP
        else:
            params = {
                "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symb,
                "FID_INPUT_DATE_1": FAR_PAST_DATE, "FID_INPUT_DATE_2": date2,
                "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0",
            }
            url, tr_id, col_map = ITEM_URL, ITEM_TR, _ITEM_COLUMN_MAP

        kc._rate_limiter.wait()
        res = ka._url_fetch(url, tr_id, "", params)
        if not res.isOK():
            return None
        output2 = getattr(res.getBody(), "output2", None)
        if not output2:
            break
        rows.extend(output2)
        if len(rows) >= min_rows:
            break
        if len(output2) < page_cap:
            break  # 상장일/지수 시작일 이전이라 더 이상 데이터 없음

        dates = [r["stck_bsop_date"] for r in output2 if r.get("stck_bsop_date")]
        oldest = min(dates)
        date2 = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        ka.smart_sleep()

    if not rows:
        return None

    df = pd.DataFrame(rows).rename(columns=col_map)
    for c in _NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    return df[["date"] + [c for c in _NUMERIC_COLS if c in df.columns]]


def fetch_ohlcv_kr(symb: str, kind: str, min_rows: int) -> pd.DataFrame:
    """symb: 종목코드("005930") 또는 지수명("KOSPI200"). kind: "item" 또는 "index"."""
    kc.ensure_auth()
    for attempt in range(2):
        df = _fetch_pages_kr(kind, symb, min_rows)
        if df is not None and not df.empty:
            return df
        if attempt == 0:
            time.sleep(1.0)
    raise RuntimeError(f"{symb}: 국내주식 API 조회 실패")

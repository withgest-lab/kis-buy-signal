"""KIS 해외주식 기간별시세 조회 래퍼.

examples_llm/kis_auth.py를 그대로 사용해 인증/호출한다.
거래소 코드(NAS/NYS/AMS)를 몰라도 자동으로 순서대로 시도해서 찾아준다.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

_EXAMPLES_LLM = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "examples_llm")
)
if _EXAMPLES_LLM not in sys.path:
    sys.path.insert(0, _EXAMPLES_LLM)

import kis_auth as ka  # noqa: E402

logger = logging.getLogger(__name__)

API_URL = "/uapi/overseas-price/v1/quotations/dailyprice"
TR_ID = "HHDFS76240000"
EXCHANGE_CANDIDATES = ["NAS", "NYS", "AMS"]
MAX_PAGES = 15

_COLUMN_MAP = {
    "xymd": "date",
    "clos": "close",
    "open": "open",
    "high": "high",
    "low": "low",
    "tvol": "volume",
}
_NUMERIC_COLS = ["close", "open", "high", "low", "volume"]

_exchange_cache: dict[str, str] = {}
_exchange_cache_lock = threading.Lock()
_authed = False
_auth_lock = threading.Lock()

MAX_REQUESTS_PER_SECOND = 8  # KIS 실전투자 호출제한(대략 초당 20건선) 대비 여유있게 설정
MAX_CONCURRENCY = 5


class _RateLimiter:
    """스레드 여러 개가 동시에 호출해도 전체 초당 요청 수를 상한선 아래로 유지."""

    def __init__(self, max_per_second: float):
        self._min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            sleep_for = self._min_interval - (now - self._last_call)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_call = time.monotonic()


_rate_limiter = _RateLimiter(MAX_REQUESTS_PER_SECOND)


def ensure_auth(svr: str = "prod") -> None:
    global _authed
    with _auth_lock:
        if not _authed:
            ka.auth(svr=svr)
            _authed = True


def _fetch_pages(excd: str, symb: str, gubn: str, min_rows: int) -> Optional[pd.DataFrame]:
    """이 API는 tr_cont가 아니라 BYMD(기준일자)를 커서로 사용한다.
    한 번에 최대 100건을 반환하며, 다음 페이지를 받으려면 BYMD를 직전 페이지의
    가장 오래된 날짜의 전날로 설정해서 재요청해야 한다."""
    rows = []
    bymd = ""
    for _ in range(MAX_PAGES):
        params = {"AUTH": "", "EXCD": excd, "SYMB": symb, "GUBN": gubn, "BYMD": bymd, "MODP": "1"}
        _rate_limiter.wait()
        res = ka._url_fetch(API_URL, TR_ID, "", params)
        if not res.isOK():
            return None
        output2 = getattr(res.getBody(), "output2", None)
        if not output2:
            break
        rows.extend(output2)
        if len(rows) >= min_rows:
            break
        if len(output2) < 100:
            break  # 상장일 이전이라 더 이상 데이터 없음

        dates = [r["xymd"] for r in output2 if r.get("xymd")]
        oldest = min(dates)
        bymd = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        ka.smart_sleep()

    if not rows:
        return None
    return pd.DataFrame(rows)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=_COLUMN_MAP)
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.drop_duplicates(subset="date").sort_values("date").reset_index(drop=True)
    keep = ["date"] + [c for c in _NUMERIC_COLS if c in df.columns]
    return df[keep]


def fetch_ohlcv(symb: str, gubn: str, min_rows: int) -> pd.DataFrame:
    """gubn: '0' 일봉, '1' 주봉. 종목별로 맞는 거래소를 찾으면 캐시해서 재사용한다."""
    ensure_auth()

    with _exchange_cache_lock:
        cached = _exchange_cache.get(symb)
    candidates = [cached] if cached else EXCHANGE_CANDIDATES

    for excd in candidates:
        for attempt in range(2):  # 일시적 서버 오류(EGW00316 등) 대비 1회 재시도
            df = _fetch_pages(excd, symb, gubn, min_rows)
            if df is not None and not df.empty:
                with _exchange_cache_lock:
                    _exchange_cache[symb] = excd
                return _normalize(df)
            if attempt == 0:
                time.sleep(1.0)
        ka.smart_sleep()

    raise RuntimeError(f"{symb}: 조회 실패 (거래소 후보 {EXCHANGE_CANDIDATES} 모두 실패)")


def exchange_of(symb: str) -> Optional[str]:
    with _exchange_cache_lock:
        return _exchange_cache.get(symb)

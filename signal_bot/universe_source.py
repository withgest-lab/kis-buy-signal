"""STEP 12 전제조건 1: S&P500 + 나스닥100 구성종목 리스트 확보 (PROJECT_PLAN.md 섹션 13).

외부 페이지 구조가 바뀌면 파이프라인이 깨질 위험이 있으므로:
  - 지수당 소스를 2개씩 순서대로 시도(1차 실패 시 2차)
  - 성공하면 결과를 signal_bot/data/universe_cache.json에 캐시
  - 캐시가 REFRESH_INTERVAL_DAYS(기본 30일)보다 새것이면 재조회 없이 캐시 사용
  - 갱신 시도가 모두 실패해도 기존 캐시가 있으면 그걸 그대로 사용(자동 fallback)
"""

import json
import logging
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CACHE_PATH = DATA_DIR / "universe_cache.json"

REFRESH_INTERVAL_DAYS = 30
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
REQUEST_TIMEOUT = 20


def _normalize_symbol(raw: str) -> str:
    """BRK.B -> BRK-B 처럼 클래스주 표기를 KIS/일반 표준 표기로 맞춘다."""
    return raw.strip().upper().replace(".", "-")


def _fetch_wikipedia_sp500() -> list[dict]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Security"]).strip()}
        for _, r in table.iterrows()
    ]


def _fetch_slickcharts_sp500() -> list[dict]:
    url = "https://www.slickcharts.com/sp500"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company"]).strip()}
        for _, r in table.iterrows()
    ]


def _fetch_slickcharts_nasdaq100() -> list[dict]:
    url = "https://www.slickcharts.com/nasdaq100"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company"]).strip()}
        for _, r in table.iterrows()
    ]


def _fetch_stockanalysis_nasdaq100() -> list[dict]:
    url = "https://stockanalysis.com/list/nasdaq-100-stocks/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company Name"]).strip()}
        for _, r in table.iterrows()
    ]


# 지수별로 시도할 소스(1차 실패 시 다음 소스로) - 위키피디아는 나스닥100 구성종목
# 테이블을 더 이상 제공하지 않아(2026-07 확인) 나스닥100은 slickcharts를 1차로 둔다.
_SOURCES: dict[str, list[Callable[[], list[dict]]]] = {
    "sp500": [_fetch_wikipedia_sp500, _fetch_slickcharts_sp500],
    "nasdaq100": [_fetch_slickcharts_nasdaq100, _fetch_stockanalysis_nasdaq100],
}

_MIN_EXPECTED_ROWS = {"sp500": 400, "nasdaq100": 80}


def _try_sources(index_key: str) -> Optional[list[dict]]:
    for fetch_fn in _SOURCES[index_key]:
        try:
            rows = fetch_fn()
            if len(rows) >= _MIN_EXPECTED_ROWS[index_key]:
                logger.info("%s: %s에서 %d개 종목 확보", index_key, fetch_fn.__name__, len(rows))
                return rows
            logger.warning(
                "%s: %s가 %d개만 반환(최소 기대치 %d) - 페이지 구조 변경 의심, 다음 소스 시도",
                index_key, fetch_fn.__name__, len(rows), _MIN_EXPECTED_ROWS[index_key],
            )
        except Exception as e:
            logger.warning("%s: %s 실패 (%s) - 다음 소스 시도", index_key, fetch_fn.__name__, e)
    return None


def load_cache() -> Optional[dict]:
    if not CACHE_PATH.exists():
        return None
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _is_stale(cache: dict) -> bool:
    updated_at = datetime.strptime(cache["updated_at"], "%Y-%m-%d").date()
    return date.today() - updated_at > timedelta(days=REFRESH_INTERVAL_DAYS)


def refresh(force: bool = False) -> dict:
    """캐시가 충분히 최신이면 그대로 반환, 아니면 갱신 시도 후 실패하면 캐시로 fallback."""
    cache = load_cache()
    if not force and cache and not _is_stale(cache):
        logger.info("universe_cache.json이 최신(%s)이라 재조회 생략", cache["updated_at"])
        return cache

    sp500 = _try_sources("sp500")
    nasdaq100 = _try_sources("nasdaq100")

    if sp500 is None or nasdaq100 is None:
        if cache:
            logger.warning("종목 리스트 갱신 실패 - 기존 캐시(%s)를 그대로 사용", cache["updated_at"])
            return cache
        raise RuntimeError(
            "S&P500/나스닥100 종목 리스트를 모든 소스에서 가져오지 못했고, 사용할 기존 캐시도 없습니다."
        )

    new_cache = {
        "updated_at": date.today().strftime("%Y-%m-%d"),
        "sp500": sp500,
        "nasdaq100": nasdaq100,
    }
    save_cache(new_cache)
    return new_cache


def get_combined_universe(force_refresh: bool = False) -> list[dict]:
    """S&P500 ∪ 나스닥100, 중복 제거. 반환: [{"symb", "name", "category"}, ...]"""
    cache = refresh(force=force_refresh)
    sp500_symbs = {r["symb"]: r["name"] for r in cache["sp500"]}
    ndx_symbs = {r["symb"]: r["name"] for r in cache["nasdaq100"]}

    merged: dict[str, dict] = {}
    for symb, name in sp500_symbs.items():
        merged[symb] = {"symb": symb, "name": name, "category": "S&P500"}
    for symb, name in ndx_symbs.items():
        if symb in merged:
            merged[symb]["category"] = "S&P500+나스닥100"
        else:
            merged[symb] = {"symb": symb, "name": name, "category": "나스닥100"}

    return sorted(merged.values(), key=lambda r: r["symb"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    universe = get_combined_universe(force_refresh=True)
    cache = load_cache()
    overlap = sum(1 for r in universe if r["category"] == "S&P500+나스닥100")
    print(f"S&P500 {len(cache['sp500'])}개 + 나스닥100 {len(cache['nasdaq100'])}개 "
          f"-> 중복제거 후 {len(universe)}개 (중복 {overlap}개)")
    print(f"캐시 저장 위치: {CACHE_PATH} (기준일 {cache['updated_at']})")

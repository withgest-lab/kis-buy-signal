"""S&P500 + 나스닥100 시가총액 상위 N종목 랭킹 확보 (MDD 우량주 유니버스용).

외부 페이지 구조가 바뀌면 파이프라인이 깨질 위험이 있으므로:
  - 지수당 소스를 2개씩 순서대로 시도(1차 실패 시 2차)
  - 성공하면 결과를 signal_bot/data/universe_cache.json에 캐시
  - 캐시가 REFRESH_INTERVAL_DAYS(기본 30일)보다 새것이면 재조회 없이 캐시 사용
  - 갱신 시도가 모두 실패해도 기존 캐시가 있으면 그걸 그대로 사용(자동 fallback)

랭킹(시가총액 상위 N) 추출을 위해서는 소스 테이블이 시가총액/지수비중 순으로
정렬돼 있어야 한다. 위키피디아 S&P500 표는 알파벳(Symbol)순이라 랭킹 정보가
없어서 제외했고, slickcharts.com(sp500/nasdaq100)은 지수 내 비중(Weight) 순
= 시가총액 순이라 1차 소스로 쓴다. stockanalysis.com도 시가총액 내림차순
정렬이라 2차 fallback으로 쓴다.
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


def _fetch_slickcharts_sp500() -> list[dict]:
    url = "https://www.slickcharts.com/sp500"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company"]).strip(), "rank": i + 1}
        for i, (_, r) in enumerate(table.iterrows())
    ]


def _fetch_stockanalysis_sp500() -> list[dict]:
    url = "https://stockanalysis.com/list/sp500-stocks/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company Name"]).strip(), "rank": i + 1}
        for i, (_, r) in enumerate(table.iterrows())
    ]


def _fetch_slickcharts_nasdaq100() -> list[dict]:
    url = "https://www.slickcharts.com/nasdaq100"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company"]).strip(), "rank": i + 1}
        for i, (_, r) in enumerate(table.iterrows())
    ]


def _fetch_stockanalysis_nasdaq100() -> list[dict]:
    url = "https://stockanalysis.com/list/nasdaq-100-stocks/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    table = pd.read_html(StringIO(resp.text))[0]
    return [
        {"symb": _normalize_symbol(r["Symbol"]), "name": str(r["Company Name"]).strip(), "rank": i + 1}
        for i, (_, r) in enumerate(table.iterrows())
    ]


# 지수별로 시도할 소스(1차 실패 시 다음 소스로) - 랭킹(시가총액 상위 N) 추출이
# 목적이라 둘 다 시가총액/비중 순 정렬 소스만 사용(위키피디아는 알파벳순이라 제외).
_SOURCES: dict[str, list[Callable[[], list[dict]]]] = {
    "sp500": [_fetch_slickcharts_sp500, _fetch_stockanalysis_sp500],
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


def get_top_n_targets(sp500_n: int = 30, ndx100_n: int = 20,
                       force_refresh: bool = False) -> list[dict]:
    """S&P500 시가총액 상위 sp500_n + 나스닥100 상위 ndx100_n, 중복 제거.
    반환: [{"symb", "name", "category", "rank"}, ...] (rank는 소속 지수 내 순위,
    두 지수에 모두 있으면 더 높은(작은) 랭크를 우선)."""
    cache = refresh(force=force_refresh)
    sp_top = sorted(cache["sp500"], key=lambda r: r["rank"])[:sp500_n]
    ndx_top = sorted(cache["nasdaq100"], key=lambda r: r["rank"])[:ndx100_n]

    merged: dict[str, dict] = {}
    for r in sp_top:
        merged[r["symb"]] = {**r, "category": "S&P500"}
    for r in ndx_top:
        if r["symb"] in merged:
            merged[r["symb"]]["category"] = "S&P500+나스닥100"
            merged[r["symb"]]["rank"] = min(merged[r["symb"]]["rank"], r["rank"])
        else:
            merged[r["symb"]] = {**r, "category": "나스닥100"}

    return sorted(merged.values(), key=lambda r: r["rank"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    targets = get_top_n_targets(force_refresh=True)
    cache = load_cache()
    overlap = sum(1 for r in targets if r["category"] == "S&P500+나스닥100")
    print(f"S&P500 상위30 + 나스닥100 상위20 -> 중복제거 후 {len(targets)}개 (중복 {overlap}개)")
    for r in targets:
        print(f"  {r['rank']:>3d}  {r['symb']:6s} {r['category']:14s} {r['name']}")
    print(f"캐시 저장 위치: {CACHE_PATH} (기준일 {cache['updated_at']})")

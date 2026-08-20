"""매수신호 알림용 종목 소개 문장 조회 (텔레그램 알림에 '이 회사가 뭐하는 회사인지' 요약 추가).

위키백과 REST 요약 API에서 회사 소개를 가져와 로컬에 영구 캐시한다. 알림 대상(하루 신규
강한매수 종목, 보통 0~5개)에 대해서만 호출되므로 전체 유니버스(500여 종목)를 매일 조회하는
부담은 없다.
"""

import json
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

from signal_bot.config import CURATED_ETF_DESCRIPTIONS

DATA_DIR = Path("signal_bot/data")
CACHE_PATH = DATA_DIR / "business_summary_cache.json"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
REQUEST_TIMEOUT = 20

SUMMARY_MAX_SENTENCES = 2
SUMMARY_MAX_CHARS = 150

# 한국어 위키백과는 "NVIDIA Corporation" 같은 정식 법인명 대신 "NVIDIA"처럼 약칭
# 문서/리다이렉트만 있는 경우가 많아, 흔한 법인 접미사를 뗀 이름으로도 시도한다.
_LEGAL_SUFFIXES = [
    " Corporation", " Incorporated", " Inc.", " Inc", " Co.", " Ltd.", " Ltd",
    " Company", " Group", " Holdings", " plc", " PLC",
]


def _strip_legal_suffix(name: str) -> Optional[str]:
    for suffix in _LEGAL_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)].strip()
    return None


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _truncate(text: str) -> str:
    sentences = text.replace("\n", " ").split(". ")
    truncated = ". ".join(sentences[:SUMMARY_MAX_SENTENCES]).strip()
    if not truncated.endswith((".", "!", "?", "다")):
        truncated += "."
    if len(truncated) > SUMMARY_MAX_CHARS:
        truncated = truncated[:SUMMARY_MAX_CHARS].rstrip() + "..."
    return truncated


def _fetch_wikipedia_summary(host: str, title: str) -> Optional[str]:
    url = f"https://{host}/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract", "").strip()
        return extract or None
    except Exception:
        return None


def _search_wikipedia_title(host: str, query: str) -> Optional[str]:
    url = f"https://{host}/w/api.php"
    params = {"action": "opensearch", "search": query, "limit": 1, "format": "json"}
    try:
        resp = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


def _fetch_business_summary(name: str) -> Optional[str]:
    short_name = _strip_legal_suffix(name)

    extract = _fetch_wikipedia_summary("ko.wikipedia.org", name)
    if not extract and short_name:
        extract = _fetch_wikipedia_summary("ko.wikipedia.org", short_name)
    if not extract:
        alt_title = _search_wikipedia_title("ko.wikipedia.org", short_name or name)
        if alt_title:
            extract = _fetch_wikipedia_summary("ko.wikipedia.org", alt_title)
    if not extract:
        extract = _fetch_wikipedia_summary("en.wikipedia.org", name)
    return _truncate(extract) if extract else None


def get_business_summary(symb: str, name: str) -> str:
    cache = _load_cache()
    if symb in cache:
        return cache[symb]

    if symb in CURATED_ETF_DESCRIPTIONS:
        summary = CURATED_ETF_DESCRIPTIONS[symb]
        cache[symb] = summary
        _save_cache(cache)
        return summary

    summary = _fetch_business_summary(name)
    if summary is None:
        return f"{name}에 대한 기업 설명을 찾지 못했습니다."

    cache[symb] = summary
    _save_cache(cache)
    return summary

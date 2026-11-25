"""타겟 종목 전체 일봉 데이터 조회 후 signal_bot/data/에 저장.

MDD는 일봉 종가만 필요하고 주/월봉 RSI/MFI/다이버전스는 일봉을 리샘플링해서
계산하므로(signal_bot/timeframe_signals.py), 주봉은 더 이상 별도로 받지 않는다.

종목별 조회를 스레드풀로 동시에 처리한다(kis_client의 레이트리미터가 전체
호출 속도를 안전선 아래로 유지해주므로, 동시 실행 개수를 늘려도 API
호출제한을 넘지 않는다). 미국·일본 종목은 kis_client, 한국 종목(KR_TARGETS)은
kis_client_kr, 비트코인 현물(CRYPTO_SPOT)은 crypto_client(코인베이스)로 분기.
"""

import datetime as dt
import logging
import zoneinfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from signal_bot import crypto_client as cc
from signal_bot import kis_client as kc
from signal_bot import kis_client_kr as kc_kr
from signal_bot.config import CRYPTO_SPOT, TICKERS, DAILY_MIN_ROWS, is_jp, is_kr, kr_kind

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

DATA_DIR = Path(__file__).parent / "data"

# 아직 열려 있는 장의 '오늘' 봉(장중 값)은 버린다 — 신호·화면은 끝난 날의 종가로만 계산한다(2026-11-25).
# 미국 종가 확정 보정 실행(20:30 ET = 한국 10:30, 여름 09:30)이 한국·일본 장중 값을 끌어오지 않게 하려는 것.
# 미국은 16:00 ET 전이면 오늘 봉을 뺀다(마감 직후 실행은 wait_us_close가 16:04 ET 뒤에 시작). 비트코인(24시간)은 그대로.
MARKET_CLOSE = {
    "US": ("America/New_York", dt.time(16, 0)),
    "KR": ("Asia/Seoul", dt.time(15, 30)),
    "JP": ("Asia/Tokyo", dt.time(15, 30)),
}


def market_of(category: str, symb: str) -> str | None:
    if symb in CRYPTO_SPOT:
        return None
    return "KR" if is_kr(category) else "JP" if is_jp(category) else "US"


def drop_unfinished_bar(daily: pd.DataFrame, market: str | None, now: dt.datetime | None = None) -> pd.DataFrame:
    """그 장이 아직 안 끝났으면(현지 오늘 날짜 봉 + 마감 전) 오늘 봉을 뺀다. now는 시험용(시간대 있는 시각)."""
    if market is None or daily.empty:
        return daily
    tz_name, close = MARKET_CLOSE[market]
    local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(zoneinfo.ZoneInfo(tz_name))
    today = pd.Timestamp(local.date())
    dates = pd.to_datetime(daily["date"])
    if dates.max().normalize() == today and local.time() < close:
        return daily[dates < today].reset_index(drop=True)
    return daily

# 종목 수가 늘수록 일시적 조회 실패 확률이 통계적으로 올라가므로, 1차 실패분만
# 모아 2차로 재시도한다. 그래도 전체 성공률이 이 아래로 떨어지면 실행 기록에
# 경고(::warning::)를 남긴다 (섹션 13-4, 텔레그램 경고는 2026-11-25 삭제).
SUCCESS_RATE_WARNING_THRESHOLD = 0.9


def _fetch_one(category: str, symb: str) -> dict:
    try:
        if symb in CRYPTO_SPOT:
            daily = cc.fetch_ohlcv_crypto(CRYPTO_SPOT[symb], min_rows=DAILY_MIN_ROWS)
            excd = "COINBASE"
        elif is_kr(category):
            daily = kc_kr.fetch_ohlcv_kr(symb, kind=kr_kind(symb), min_rows=DAILY_MIN_ROWS)
            excd = "KRX"
        else:
            daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS)
            excd = kc.exchange_of(symb)
        daily = drop_unfinished_bar(daily, market_of(category, symb))
        daily.to_csv(DATA_DIR / f"{symb}_daily.csv", index=False)
        return {
            "category": category,
            "symb": symb,
            "ok": True,
            "excd": excd,
            "daily_rows": len(daily),
            "error": None,
        }
    except Exception as e:
        return {
            "category": category,
            "symb": symb,
            "ok": False,
            "excd": None,
            "daily_rows": 0,
            "error": str(e),
        }


def _fetch_all(tickers: list[tuple[str, str]]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in tickers}
        for future in as_completed(futures):
            results.append(future.result())

    order = {symb: i for i, (_category, symb) in enumerate(tickers)}
    results.sort(key=lambda r: order[r["symb"]])
    return results


def _warn_low_success(results: list[dict]) -> None:
    """성공률이 기준 미만이면 GitHub Actions 경고(실행 요약에 노란 표시)로 남긴다(텔레그램은 2026-11-25 삭제)."""
    ok_count = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    success_rate = ok_count / len(results) if results else 1.0
    if success_rate >= SUCCESS_RATE_WARNING_THRESHOLD:
        return

    failed_list = ", ".join(r["symb"] for r in failed[:20])
    if len(failed) > 20:
        failed_list += f" 외 {len(failed) - 20}개"
    print(f"::warning title=KIS 데이터 품질::{ok_count}/{len(results)}개 종목만 조회 성공 "
          f"({success_rate * 100:.1f}%, 기준 {SUCCESS_RATE_WARNING_THRESHOLD * 100:.0f}% 미만) - 실패: {failed_list}")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    kc.ensure_auth()

    results = _fetch_all(TICKERS)

    failed_tickers = [(r["category"], r["symb"]) for r in results if not r["ok"]]
    if failed_tickers:
        print(f"\n1차 조회 실패 {len(failed_tickers)}종목 재시도 중...")
        retry_results = {r["symb"]: r for r in _fetch_all(failed_tickers)}
        results = [retry_results[r["symb"]] if r["symb"] in retry_results else r for r in results]

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{ok_count}/{len(results)} 성공\n")

    for r in results:
        if r["ok"]:
            flag = "OK  "
            daily_flag = "" if r["daily_rows"] >= DAILY_MIN_ROWS else f" (요청 {DAILY_MIN_ROWS} 미달)"
            print(f"{flag}{r['category']:6s} {r['symb']:6s} ({r['excd']})  daily={r['daily_rows']}{daily_flag}")
        else:
            print(f"FAIL {r['category']:6s} {r['symb']:6s}  {r['error']}")

    _warn_low_success(results)

    return results


if __name__ == "__main__":
    main()

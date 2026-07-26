"""백테스트 전용 장기 시세 확보 (약 10~12년치).

운영용 일일 파이프라인이 쓰는 signal_bot/data/*.csv(250거래일치)와는 완전히
분리된 signal_bot/data/backtest/ 폴더에 저장한다. 이 스크립트는 1회성(또는
가끔) 실행 용도이며, 매일 도는 GitHub Actions 워크플로우와는 무관하다.

기간을 넓게 잡는 이유: 최근 1년치만으로는 최근 상승장 위주로만 검증하게
되어, 2022년 하락장/2020년 코로나 급락 같은 다른 국면에서도 로직이
유효한지 확인할 수 없었다 (PROJECT_PLAN.md 섹션 3-4).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from signal_bot import kis_client as kc
from signal_bot.config import TICKERS

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

BACKTEST_DIR = Path(__file__).parent / "data" / "backtest"
DAILY_MIN_ROWS = 3000   # 약 12년
WEEKLY_MIN_ROWS = 700    # 약 13.5년 (20주선 워밍업 버퍼 포함)


def _fetch_one(category: str, symb: str) -> dict:
    try:
        daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS)
        weekly = kc.fetch_ohlcv(symb, gubn="1", min_rows=WEEKLY_MIN_ROWS)
        daily.to_csv(BACKTEST_DIR / f"{symb}_daily.csv", index=False)
        weekly.to_csv(BACKTEST_DIR / f"{symb}_weekly.csv", index=False)
        return {
            "category": category, "symb": symb, "ok": True,
            "daily_rows": len(daily), "weekly_rows": len(weekly),
            "earliest": daily["date"].min().strftime("%Y-%m-%d"),
            "error": None,
        }
    except Exception as e:
        return {
            "category": category, "symb": symb, "ok": False,
            "daily_rows": 0, "weekly_rows": 0, "earliest": None, "error": str(e),
        }


def main():
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    kc.ensure_auth()
    kc.MAX_PAGES = 35  # 3000행 확보하려면 기존 15(=1500행)로는 부족해서 늘림

    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in TICKERS}
        for future in as_completed(futures):
            results.append(future.result())
            done = len(results)
            if done % 50 == 0 or done == len(TICKERS):
                print(f"진행: {done}/{len(TICKERS)}", flush=True)

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    print(f"\n{len(ok)}/{len(results)} 성공")
    if ok:
        earliest_dates = sorted(r["earliest"] for r in ok)
        print(f"가장 긴 종목: {earliest_dates[0]}부터, 가장 짧은 종목: {earliest_dates[-1]}부터")
    if fail:
        print(f"실패 {len(fail)}종목: {[r['symb'] for r in fail]}")


if __name__ == "__main__":
    main()

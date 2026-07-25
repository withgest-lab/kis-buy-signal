"""STEP 3: 타겟 종목 전체 일봉/주봉 데이터 조회 후 signal_bot/data/에 저장.

종목별 조회를 스레드풀로 동시에 처리한다(kis_client의 레이트리미터가 전체
호출 속도를 안전선 아래로 유지해주므로, 동시 실행 개수를 늘려도 API
호출제한을 넘지 않는다).
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from signal_bot import kis_client as kc
from signal_bot.config import TICKERS, DAILY_MIN_ROWS, WEEKLY_MIN_ROWS

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

DATA_DIR = Path(__file__).parent / "data"


def _fetch_one(category: str, symb: str) -> dict:
    try:
        daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS)
        weekly = kc.fetch_ohlcv(symb, gubn="1", min_rows=WEEKLY_MIN_ROWS)
        daily.to_csv(DATA_DIR / f"{symb}_daily.csv", index=False)
        weekly.to_csv(DATA_DIR / f"{symb}_weekly.csv", index=False)
        return {
            "category": category,
            "symb": symb,
            "ok": True,
            "excd": kc.exchange_of(symb),
            "daily_rows": len(daily),
            "weekly_rows": len(weekly),
            "error": None,
        }
    except Exception as e:
        return {
            "category": category,
            "symb": symb,
            "ok": False,
            "excd": None,
            "daily_rows": 0,
            "weekly_rows": 0,
            "error": str(e),
        }


def main():
    DATA_DIR.mkdir(exist_ok=True)
    kc.ensure_auth()

    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in TICKERS}
        for future in as_completed(futures):
            results.append(future.result())

    order = {symb: i for i, (_category, symb) in enumerate(TICKERS)}
    results.sort(key=lambda r: order[r["symb"]])

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{ok_count}/{len(results)} 성공\n")

    for r in results:
        if r["ok"]:
            flag = "OK  "
            daily_flag = "" if r["daily_rows"] >= DAILY_MIN_ROWS else f" (요청 {DAILY_MIN_ROWS} 미달)"
            weekly_flag = "" if r["weekly_rows"] >= WEEKLY_MIN_ROWS else f" (요청 {WEEKLY_MIN_ROWS} 미달)"
            print(
                f"{flag}{r['category']:6s} {r['symb']:6s} ({r['excd']})  "
                f"daily={r['daily_rows']}{daily_flag}  weekly={r['weekly_rows']}{weekly_flag}"
            )
        else:
            print(f"FAIL {r['category']:6s} {r['symb']:6s}  {r['error']}")

    return results


if __name__ == "__main__":
    main()

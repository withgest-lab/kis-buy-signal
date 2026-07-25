"""STEP 3: 타겟 종목 32개 일봉/주봉 데이터 조회 후 signal_bot/data/에 저장."""

import logging
import time
from pathlib import Path

from signal_bot import kis_client as kc
from signal_bot.config import TICKERS, DAILY_MIN_ROWS, WEEKLY_MIN_ROWS

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

DATA_DIR = Path(__file__).parent / "data"


def main():
    DATA_DIR.mkdir(exist_ok=True)
    kc.ensure_auth()

    results = []
    for category, symb in TICKERS:
        try:
            daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS)
            time.sleep(0.3)
            weekly = kc.fetch_ohlcv(symb, gubn="1", min_rows=WEEKLY_MIN_ROWS)
            daily.to_csv(DATA_DIR / f"{symb}_daily.csv", index=False)
            weekly.to_csv(DATA_DIR / f"{symb}_weekly.csv", index=False)
            results.append(
                {
                    "category": category,
                    "symb": symb,
                    "ok": True,
                    "excd": kc.exchange_of(symb),
                    "daily_rows": len(daily),
                    "weekly_rows": len(weekly),
                    "error": None,
                }
            )
        except Exception as e:
            results.append(
                {
                    "category": category,
                    "symb": symb,
                    "ok": False,
                    "excd": None,
                    "daily_rows": 0,
                    "weekly_rows": 0,
                    "error": str(e),
                }
            )
        time.sleep(0.3)

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

"""장기 백테스트용 지표/신호 컴포넌트 캐시 생성.

signal_bot/data/backtest/*.csv(10~13년치)로 지표 계산은 한 번만 하고,
그 결과(가중치 곱하기 전 0~1 점수들)를 signal_bot/data/backtest/components/
에 저장해둔다. 이후 가중치 실험(backtest_experiments.py)은 이 캐시를 읽어서
가중합만 다시 계산하면 되므로 매번 지표를 재계산하지 않아도 된다.
"""

from pathlib import Path

import pandas as pd

from signal_bot.config import TICKERS
from signal_bot.scoring import compute_components

BACKTEST_DIR = Path("signal_bot/data/backtest")
COMPONENTS_DIR = BACKTEST_DIR / "components"

KEEP_COLS = [
    "date", "close", "adx", "plus_di", "minus_di",
    "s_weekly_trend", "s_percent_b", "s_rsi_divergence",
    "s_mfi_lead", "s_squeeze_expansion", "s_volume_exhaustion",
]


def main():
    COMPONENTS_DIR.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, []
    for i, (_cat, symb) in enumerate(TICKERS, 1):
        daily_path = BACKTEST_DIR / f"{symb}_daily.csv"
        weekly_path = BACKTEST_DIR / f"{symb}_weekly.csv"
        if not daily_path.exists() or not weekly_path.exists():
            fail.append(symb)
            continue
        try:
            daily = pd.read_csv(daily_path, parse_dates=["date"])
            weekly = pd.read_csv(weekly_path, parse_dates=["date"])
            df = compute_components(daily, weekly)
            df[KEEP_COLS].to_csv(COMPONENTS_DIR / f"{symb}.csv", index=False)
            ok += 1
        except Exception as e:
            fail.append(f"{symb}({e})")
        if i % 100 == 0:
            print(f"진행: {i}/{len(TICKERS)}", flush=True)

    print(f"\n{ok}/{len(TICKERS)} 성공")
    if fail:
        print(f"실패: {fail}")


if __name__ == "__main__":
    main()

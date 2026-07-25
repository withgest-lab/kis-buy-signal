"""STEP 4 검증: NVDA로 기본 지표 계산 후 상식적 범위인지 확인."""

import numpy as np
import pandas as pd

from signal_bot import indicators as ind

DATA_DIR = "signal_bot/data"


def main():
    daily = pd.read_csv(f"{DATA_DIR}/NVDA_daily.csv", parse_dates=["date"])
    weekly = pd.read_csv(f"{DATA_DIR}/NVDA_weekly.csv", parse_dates=["date"])

    daily["rsi"] = ind.rsi(daily["close"])
    daily["mfi"] = ind.mfi(daily["high"], daily["low"], daily["close"], daily["volume"])
    daily = pd.concat([daily, ind.bollinger(daily["close"])], axis=1)
    daily = pd.concat([daily, ind.adx(daily["high"], daily["low"], daily["close"])], axis=1)

    weekly = pd.concat([weekly, ind.weekly_ma(weekly["close"])], axis=1)

    print("=== 일봉 최근 5일 ===")
    cols = ["date", "close", "rsi", "mfi", "percent_b", "bandwidth", "plus_di", "minus_di", "adx"]
    print(daily[cols].tail(5).to_string(index=False))

    print("\n=== 주봉 최근 5주 (20주선) ===")
    print(weekly[["date", "close", "ma20w", "ma20w_slope"]].tail(5).to_string(index=False))

    # 범위 검증 (워밍업 구간 이후)
    print("\n=== 범위/NaN 점검 (워밍업 이후 구간) ===")
    checks = [
        ("RSI 0~100", daily["rsi"].dropna(), 0, 100),
        ("MFI 0~100", daily["mfi"].dropna(), 0, 100),
        ("+DI 0~100", daily["plus_di"].dropna(), 0, 100),
        ("-DI 0~100", daily["minus_di"].dropna(), 0, 100),
        ("ADX 0~100", daily["adx"].dropna(), 0, 100),
    ]
    all_ok = True
    for name, series, lo, hi in checks:
        out_of_range = ((series < lo) | (series > hi)).sum()
        has_inf = np.isinf(series).sum()
        ok = out_of_range == 0 and has_inf == 0
        all_ok &= ok
        print(f"{'OK ' if ok else 'FAIL'} {name:12s} 범위밖={out_of_range}  inf={has_inf}  개수={len(series)}")

    warmup_tail = daily.iloc[30:]  # 30일 이후는 전부 값이 있어야 함
    nan_after_warmup = warmup_tail[["rsi", "mfi", "percent_b", "bandwidth", "plus_di", "minus_di", "adx"]].isna().sum()
    print("\n30번째 행 이후 NaN 개수 (전부 0이어야 정상):")
    print(nan_after_warmup.to_string())

    print(f"\n최종 판정: {'PASS' if all_ok and nan_after_warmup.sum() == 0 else 'FAIL'}")


if __name__ == "__main__":
    main()

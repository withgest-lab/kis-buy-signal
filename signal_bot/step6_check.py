"""STEP 6 검증: NVDA로 스코어링 함수 실행 후 요약 출력 + 차트용 JSON 저장."""

import json
from pathlib import Path

import pandas as pd

from signal_bot.scoring import compute_scores

DATA_DIR = Path("signal_bot/data")
SIX_MONTHS_TRADING_DAYS = 126


def main():
    daily = pd.read_csv(DATA_DIR / "NVDA_daily.csv", parse_dates=["date"])
    weekly = pd.read_csv(DATA_DIR / "NVDA_weekly.csv", parse_dates=["date"])
    df = compute_scores(daily, weekly)

    print("=== 최근 15거래일 ===")
    print(df[["date", "close", "score", "verdict"]].tail(15).to_string(index=False))

    print("\n=== 점검 ===")
    print(f"score 범위: {df['score'].min():.1f} ~ {df['score'].max():.1f}")
    print(f"score NaN 개수: {df['score'].isna().sum()}")
    print("판정 분포:")
    print(df["verdict"].value_counts().to_string())

    recent = df.tail(SIX_MONTHS_TRADING_DAYS)
    records = [
        {
            "date": r["date"].strftime("%Y-%m-%d"),
            "close": round(float(r["close"]), 2),
            "score": round(float(r["score"]), 1),
            "verdict": r["verdict"],
            "div": bool(r["rsi_div_detected"]),
            "squeeze": bool(r["squeeze_exp_detected"]),
            "mfi_lead": bool(r["mfi_lead_detected"]),
            "vol_ex": bool(r["s_volume_exhaustion"] > 0),
        }
        for _, r in recent.iterrows()
    ]
    out_path = DATA_DIR / "nvda_step6_chart.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"\n차트용 JSON 저장: {out_path} ({len(records)}행)")


if __name__ == "__main__":
    main()

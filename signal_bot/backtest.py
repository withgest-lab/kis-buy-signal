"""STEP 10 확장 백테스트 (PROJECT_PLAN.md 섹션 3-4 / STEP 10).

signal_bot/backtest_fetch.py로 받아둔 약 10~12년치 데이터를 이용해서, 최근
1년치만으로는 볼 수 없었던 상승장/횡보장/하락장 국면별로 스코어링 로직이
무작위 매수 대비 우위가 있는지 따로 확인한다.

국면 구분은 특정 날짜를 손으로 골라 하드코딩하지 않는다(그 자체로 과최적화/
사후확신 편향 위험이 있어서). 대신 SPY 자체 가격으로 객관적으로 나눈다:
SPY 종가가 200일 이동평균 대비 +3% 이상이면 상승장, -3% 이하면 하락장,
그 사이면 횡보장.
"""

from pathlib import Path

import pandas as pd

from signal_bot.config import TICKERS
from signal_bot.scoring import STRONG_BUY_THRESHOLD, compute_scores

BACKTEST_DIR = Path("signal_bot/data/backtest")
HORIZONS = [5, 10, 20]
REGIME_BAND = 0.03

_EMPTY_COLS = ["symb", "date", "regime", "score"] + [f"ret_{h}d" for h in HORIZONS]


def build_regime_series() -> pd.Series:
    """SPY 종가 vs 200일선으로 날짜별 국면(상승장/횡보장/하락장) 분류. index=date"""
    spy = pd.read_csv(BACKTEST_DIR / "SPY_daily.csv", parse_dates=["date"])
    close = spy["close"]
    sma200 = close.rolling(200).mean()
    ratio = close / sma200

    regime = pd.Series("횡보장", index=spy["date"])
    regime[(ratio >= 1 + REGIME_BAND).values] = "상승장"
    regime[(ratio <= 1 - REGIME_BAND).values] = "하락장"
    regime[sma200.isna().values] = None
    return regime


def _forward_returns(close: pd.Series, entry_idx: int) -> dict:
    entry_price = close.iloc[entry_idx]
    out = {}
    for h in HORIZONS:
        idx = entry_idx + h
        out[h] = (close.iloc[idx] / entry_price - 1.0) if idx < len(close) else None
    return out


def backtest_ticker(symb: str, regime_by_date: dict) -> tuple[list, list]:
    daily_path = BACKTEST_DIR / f"{symb}_daily.csv"
    weekly_path = BACKTEST_DIR / f"{symb}_weekly.csv"
    if not daily_path.exists() or not weekly_path.exists():
        return [], []
    try:
        daily = pd.read_csv(daily_path, parse_dates=["date"])
        weekly = pd.read_csv(weekly_path, parse_dates=["date"])
        df = compute_scores(daily, weekly)
    except Exception:
        return [], []

    events = []
    baseline_rows = []
    prev_score = None
    for i in range(len(df)):
        date = df["date"].iloc[i]
        regime = regime_by_date.get(date)
        score = df["score"].iloc[i]
        if regime is None:
            prev_score = score
            continue

        rets = _forward_returns(df["close"], i)
        baseline_rows.append({
            "symb": symb, "date": date, "regime": regime,
            **{f"ret_{h}d": rets[h] for h in HORIZONS},
        })

        if prev_score is not None and prev_score < STRONG_BUY_THRESHOLD <= score:
            events.append({
                "symb": symb, "date": date.strftime("%Y-%m-%d"), "regime": regime,
                "score": round(float(score), 1),
                **{f"ret_{h}d": rets[h] for h in HORIZONS},
            })
        prev_score = score
    return events, baseline_rows


def summarize(df: pd.DataFrame, label: str) -> dict:
    print(f"\n--- {label} (표본 {len(df)}건) ---")
    means = {}
    if len(df) == 0:
        print("표본 없음")
        return means
    for h in HORIZONS:
        valid = df[f"ret_{h}d"].dropna()
        if len(valid) == 0:
            continue
        means[h] = valid.mean()
        win = (valid > 0).mean() * 100
        print(f"{h:>2}일 후: 평균 {valid.mean()*100:+.2f}%  중앙값 {valid.median()*100:+.2f}%  "
              f"승률 {win:.1f}%  (n={len(valid)})")
    return means


def main():
    regime_series = build_regime_series()
    regime_by_date = regime_series.to_dict()

    print("=== SPY 기준 국면 분류(전체 기간 거래일 수) ===")
    print(regime_series.value_counts(dropna=True).to_string())

    all_events = []
    all_baseline = []
    for _cat, symb in TICKERS:
        events, baseline_rows = backtest_ticker(symb, regime_by_date)
        all_events.extend(events)
        all_baseline.extend(baseline_rows)

    events_df = pd.DataFrame(all_events, columns=_EMPTY_COLS) if not all_events else pd.DataFrame(all_events)
    baseline_df = pd.DataFrame(all_baseline) if all_baseline else pd.DataFrame(columns=_EMPTY_COLS)

    n_symbs = events_df["symb"].nunique() if len(events_df) else 0
    print(f"\n전체 신규 70점 진입 이벤트: {len(events_df)}건 ({n_symbs}개 종목)")

    summarize(events_df, "전체 기간 - 신호 진입 후 수익률")
    summarize(baseline_df, "전체 기간 - 아무 날에나 샀을 때(기준선)")

    print("\n" + "=" * 60)
    print("국면별 분석")
    print("=" * 60)

    regime_results = {}
    for regime in ["상승장", "횡보장", "하락장"]:
        sig_sub = events_df[events_df["regime"] == regime] if len(events_df) else events_df
        base_sub = baseline_df[baseline_df["regime"] == regime] if len(baseline_df) else baseline_df
        sig_means = summarize(sig_sub, f"[{regime}] 신호 진입 후 수익률")
        base_means = summarize(base_sub, f"[{regime}] 기준선(아무 날에나)")
        regime_results[regime] = (sig_means, base_means)

    print("\n" + "=" * 60)
    print("요약: 국면별 신호 우위 (신호평균 - 기준선평균, %p, 양수면 신호가 나음)")
    print("=" * 60)
    for regime, (sig_means, base_means) in regime_results.items():
        parts = []
        for h in HORIZONS:
            if h in sig_means and h in base_means:
                edge = (sig_means[h] - base_means[h]) * 100
                parts.append(f"{h}일: {edge:+.2f}%p")
        print(f"{regime}: {'  '.join(parts) if parts else '표본 부족'}")

    if len(events_df):
        out_path = BACKTEST_DIR / "backtest_events_by_regime.csv"
        events_df.to_csv(out_path, index=False)
        print(f"\n상세 내역 저장: {out_path}")


if __name__ == "__main__":
    main()

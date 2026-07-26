"""종합 검증 리포트: 보유기간(5/10/20/63/126일) x 종목군(전체/변동성티어/빅테크)
x 표본(전체/인샘플/OOS) x 가중치(기존/제안)를 한 번에 비교한다.

우량주/성장주 구분은 사용자의 주관적 판단이 아니라, 인샘플(~2022) 구간의
실현 변동성(연율화 일간수익률 표준편차)으로 객관적으로 3등분한다. 변동성이
낮을수록 통상 '우량주/안정주'에 가깝고, 높을수록 '성장주/투기성'에 가깝다는
통념을 그대로 데이터로 검증하는 것이지, 특정 종목을 손으로 골라 나누지 않는다.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

from signal_bot.backtest_experiments import (
    HORIZONS, MEGA_CAP_TECH, TICKERS, get_regime_by_date, run_experiment,
)
from signal_bot.scoring import WEIGHTS

BACKTEST_DIR = Path("signal_bot/data/backtest")
IN_SAMPLE = (pd.Timestamp("2000-01-01"), pd.Timestamp("2022-12-31"))
OUT_SAMPLE = (pd.Timestamp("2023-01-01"), pd.Timestamp("2030-01-01"))

PROPOSED = dict(weekly_trend=15, percent_b=15, rsi_divergence=25,
                mfi_lead=20, squeeze_expansion=15, volume_exhaustion=10)


def compute_volatility_tiers() -> dict:
    """인샘플(~2022) 구간 일간수익률의 연율화 표준편차로 종목을 3등분."""
    vols = {}
    for _cat, symb in TICKERS:
        path = BACKTEST_DIR / f"{symb}_daily.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        df = df[df["date"] <= IN_SAMPLE[1]]
        if len(df) < 100:
            continue
        rets = df["close"].pct_change().dropna()
        vols[symb] = rets.std() * np.sqrt(252)

    sorted_symbs = sorted(vols, key=lambda s: vols[s])
    n = len(sorted_symbs)
    low = set(sorted_symbs[: n // 3])
    mid = set(sorted_symbs[n // 3: 2 * n // 3])
    high = set(sorted_symbs[2 * n // 3:])
    print(f"변동성 3등분: 저변동성(우량주 성격) {len(low)}종목 "
          f"(연율화 변동성 {vols[sorted_symbs[0]]*100:.0f}~{vols[sorted_symbs[n//3-1]]*100:.0f}%), "
          f"고변동성(성장/투기성) {len(high)}종목 "
          f"(연율화 변동성 {vols[sorted_symbs[2*n//3]]*100:.0f}~{vols[sorted_symbs[-1]]*100:.0f}%)")
    return {"저변동성(우량주성격)": low, "중간변동성": mid, "고변동성(성장/투기성)": high}


def compact_line(label: str, result: dict) -> str:
    parts = []
    for h in HORIZONS:
        edge = result.get(f"전체_{h}d_edge")
        n = result.get(f"전체_{h}d_n")
        if edge is not None and not (isinstance(edge, float) and np.isnan(edge)):
            parts.append(f"{h}d:{edge*100:+.2f}%p(n={n})")
    body = "  ".join(parts) if parts else "표본없음"
    return f"{label:45s} {body}"


def main():
    tiers = compute_volatility_tiers()
    universes = {"전체(543종목)": None, "빅테크10": MEGA_CAP_TECH, **tiers}
    samples = {"전체기간": None, "인샘플(~2022)": IN_SAMPLE, "OOS(2023~)": OUT_SAMPLE}
    weight_configs = {
        "기존가중치": dict(weights=None, market_filter=None),
        "제안안(가중치+시장필터)": dict(weights=PROPOSED, market_filter="block"),
    }

    print("\n" + "=" * 100)
    print("보유기간별(5/10/20/63일=3개월/126일=6개월) 신호우위 종합 비교")
    print("=" * 100)

    for sample_label, dr in samples.items():
        print(f"\n--- {sample_label} ---")
        for universe_label, symb_filter in universes.items():
            for weight_label, cfg in weight_configs.items():
                r = run_experiment(weights=cfg["weights"], market_filter=cfg["market_filter"],
                                    date_range=dr, symb_filter=symb_filter)
                print(compact_line(f"[{universe_label}] {weight_label}", r))


if __name__ == "__main__":
    main()

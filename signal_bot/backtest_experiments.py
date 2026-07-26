"""가중치/로직 실험용 빠른 백테스트 러너.

backtest_components.py가 만들어둔 컴포넌트 캐시(지표 계산 완료 상태)를 읽어서
가중치 조합만 바꿔가며 국면별(상승장/횡보장/하락장) 신호 우위를 빠르게 비교한다.
지표 재계산이 없어서 5백여 종목 전체를 몇 초 안에 다시 채점할 수 있다.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from signal_bot.config import TICKERS
from signal_bot.scoring import STRONG_BUY_THRESHOLD, WATCHLIST_THRESHOLD, WEIGHTS, combine_score

BACKTEST_DIR = Path("signal_bot/data/backtest")
COMPONENTS_DIR = BACKTEST_DIR / "components"
HORIZONS = [5, 10, 20, 63, 126]  # 63거래일≈3개월, 126거래일≈6개월

MEGA_CAP_TECH = {"NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "META", "AVGO", "TSLA", "ORCL", "PLTR"}
USER_MENTIONED = {"AAPL", "TSLA", "GOOGL", "MSFT"}

_cache: dict[tuple, pd.DataFrame] = {}
_regime_by_date: dict = None


def _load_components(symb: str, components_dir: Path = COMPONENTS_DIR) -> pd.DataFrame:
    key = (str(components_dir), symb)
    if key not in _cache:
        path = components_dir / f"{symb}.csv"
        if not path.exists():
            _cache[key] = None
        else:
            _cache[key] = pd.read_csv(path, parse_dates=["date"])
    return _cache[key]


def build_regime_series() -> pd.Series:
    spy = pd.read_csv(BACKTEST_DIR / "SPY_daily.csv", parse_dates=["date"])
    close = spy["close"]
    sma200 = close.rolling(200).mean()
    ratio = close / sma200
    regime = pd.Series("횡보장", index=spy["date"])
    regime[(ratio >= 1.03).values] = "상승장"
    regime[(ratio <= 0.97).values] = "하락장"
    regime[sma200.isna().values] = None
    return regime


def get_regime_by_date() -> dict:
    global _regime_by_date
    if _regime_by_date is None:
        _regime_by_date = build_regime_series().to_dict()
    return _regime_by_date


def _forward_returns(close: pd.Series, entry_idx: int) -> dict:
    entry_price = close.iloc[entry_idx]
    out = {}
    for h in HORIZONS:
        idx = entry_idx + h
        out[h] = (close.iloc[idx] / entry_price - 1.0) if idx < len(close) else None
    return out


def run_experiment(weights: dict = None, apply_regime_penalty: bool = True,
                    regime_penalty_factor: float = 0.3,
                    entry_threshold: float = STRONG_BUY_THRESHOLD,
                    market_filter: str = None,
                    market_filter_factor: float = 0.0,
                    date_range: tuple = None,
                    symb_filter: set = None,
                    components_dir: Path = COMPONENTS_DIR) -> dict:
    """주어진 가중치/설정으로 전체 유니버스를 다시 채점하고, 국면별 신호우위(edge)를 반환.

    market_filter: None이면 미적용. "block"이면 SPY 자체가 하락장인 날은 그
    날짜의 모든 종목 점수를 market_filter_factor배로 깎는다(개별종목 ADX와
    무관하게 시장 전체 국면을 반영하는 필터 실험용).
    symb_filter: 지정하면 이 종목들만 대상으로 계산(예: 빅테크만)."""
    regime_by_date = get_regime_by_date()
    all_events = []
    all_baseline = []

    universe = TICKERS if symb_filter is None else [(c, s) for c, s in TICKERS if s in symb_filter]
    for _cat, symb in universe:
        comp = _load_components(symb, components_dir)
        if comp is None:
            continue
        df = combine_score(comp, weights=weights, apply_regime_penalty=apply_regime_penalty,
                            regime_penalty_factor=regime_penalty_factor)

        if market_filter == "block":
            dates = df["date"]
            market_bear = dates.map(lambda d: regime_by_date.get(d) == "하락장")
            df["score"] = df["score"].where(~market_bear.values, df["score"] * market_filter_factor)

        prev_score = None
        for i in range(len(df)):
            date = df["date"].iloc[i]
            regime = regime_by_date.get(date)
            if regime is None:
                prev_score = df["score"].iloc[i]
                continue
            score = df["score"].iloc[i]
            in_range = date_range is None or (date_range[0] <= date <= date_range[1])
            if in_range:
                rets = _forward_returns(df["close"], i)
                all_baseline.append({"regime": regime, **{f"ret_{h}d": rets[h] for h in HORIZONS}})
                if prev_score is not None and prev_score < entry_threshold <= score:
                    all_events.append({"symb": symb, "regime": regime,
                                        **{f"ret_{h}d": rets[h] for h in HORIZONS}})
            prev_score = score

    events_df = pd.DataFrame(all_events) if all_events else pd.DataFrame(columns=["symb", "regime"])
    baseline_df = pd.DataFrame(all_baseline) if all_baseline else pd.DataFrame(columns=["regime"])

    result = {"n_events": len(events_df), "n_symbs": events_df["symb"].nunique() if len(events_df) else 0}
    for regime in ["전체", "상승장", "횡보장", "하락장"]:
        sig_sub = events_df if regime == "전체" else events_df[events_df["regime"] == regime]
        base_sub = baseline_df if regime == "전체" else baseline_df[baseline_df["regime"] == regime]
        for h in HORIZONS:
            sig_valid = sig_sub[f"ret_{h}d"].dropna() if len(sig_sub) else pd.Series(dtype=float)
            base_valid = base_sub[f"ret_{h}d"].dropna() if len(base_sub) else pd.Series(dtype=float)
            sig_mean = sig_valid.mean() if len(sig_valid) else np.nan
            base_mean = base_valid.mean() if len(base_valid) else np.nan
            result[f"{regime}_{h}d_n"] = len(sig_valid)
            result[f"{regime}_{h}d_signal"] = sig_mean
            result[f"{regime}_{h}d_baseline"] = base_mean
            result[f"{regime}_{h}d_edge"] = (sig_mean - base_mean) if pd.notna(sig_mean) and pd.notna(base_mean) else np.nan
    return result


def print_result(label: str, result: dict) -> None:
    print(f"\n### {label} ###  (이벤트 {result['n_events']}건, {result['n_symbs']}종목)")
    for regime in ["전체", "상승장", "횡보장", "하락장"]:
        parts = []
        for h in HORIZONS:
            edge = result.get(f"{regime}_{h}d_edge")
            n = result.get(f"{regime}_{h}d_n")
            if edge is not None and not (isinstance(edge, float) and np.isnan(edge)):
                parts.append(f"{h}d:{edge*100:+.2f}%p(n={n})")
        print(f"  {regime}: {'  '.join(parts) if parts else '표본없음'}")


if __name__ == "__main__":
    baseline_result = run_experiment()
    print_result("기본 가중치 (현재 운영값)", baseline_result)

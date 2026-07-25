"""매수신호 스코어링 (PROJECT_PLAN.md 섹션 3-3)."""

import numpy as np
import pandas as pd

from signal_bot import indicators as ind
from signal_bot import signals as sig

WEIGHTS = {
    "weekly_trend": 25,
    "percent_b": 20,
    "rsi_divergence": 20,
    "mfi_lead": 15,
    "squeeze_expansion": 10,
    "volume_exhaustion": 10,
}

STRONG_BUY_THRESHOLD = 70
WATCHLIST_THRESHOLD = 50


def _score_weekly_trend(close: pd.Series, ma20w: pd.Series, ma20w_slope: pd.Series) -> pd.Series:
    score = pd.Series(0.0, index=close.index)
    score = score.where(~((close > ma20w) & (ma20w_slope > 0)), 1.0)
    cond_above = (close > ma20w) & ~((close > ma20w) & (ma20w_slope > 0))
    score = score.where(~cond_above, 0.6)
    cond_near = (close <= ma20w) & (close >= ma20w * 0.97)
    score = score.where(~cond_near, 0.3)
    return score.where(ma20w.notna(), 0.0)


def _score_percent_b(percent_b: pd.Series) -> pd.Series:
    score = pd.Series(0.0, index=percent_b.index)
    near = (percent_b > 0.05) & (percent_b <= 0.2)
    score = score.where(~near, (0.2 - percent_b) / 0.15)
    score = score.where(~(percent_b <= 0.05), 1.0)
    return score.clip(lower=0.0, upper=1.0)


def _score_rsi_divergence(detected: pd.Series, strength: pd.Series) -> pd.Series:
    return (detected.astype(float) * (0.7 + strength * 0.3))


def _score_volume_exhaustion(ratio: pd.Series) -> pd.Series:
    score = pd.Series(0.0, index=ratio.index)
    score = score.where(~(ratio < 1.0), 0.5)
    score = score.where(~(ratio < 0.8), 1.0)
    return score


def compute_scores(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """daily/weekly: date 오름차순 정렬된 OHLCV DataFrame (kis_client.fetch_ohlcv 형식).
    Returns: daily에 지표/신호/점수 컬럼이 추가된 DataFrame."""
    df = daily.copy().reset_index(drop=True)

    df["rsi"] = ind.rsi(df["close"])
    df["mfi"] = ind.mfi(df["high"], df["low"], df["close"], df["volume"])
    df = pd.concat([df, ind.bollinger(df["close"])], axis=1)
    df = pd.concat([df, ind.adx(df["high"], df["low"], df["close"])], axis=1)

    weekly_ind = pd.concat([weekly[["date", "close"]], ind.weekly_ma(weekly["close"])], axis=1)
    weekly_ind = weekly_ind.rename(columns={"close": "weekly_close"})
    df = pd.merge_asof(
        df.sort_values("date"), weekly_ind.sort_values("date"),
        on="date", direction="backward",
    )

    div_rsi = sig.bullish_divergence(df["close"], df["rsi"])
    div_mfi = sig.bullish_divergence(df["close"], df["mfi"])
    df["rsi_div_detected"] = div_rsi["detected"] | div_mfi["detected"]
    df["rsi_div_strength"] = pd.concat([div_rsi["strength"], div_mfi["strength"]], axis=1).max(axis=1)

    df["squeeze_exp_detected"] = sig.bollinger_squeeze_expansion(df["bandwidth"])
    df["mfi_lead_detected"] = sig.mfi_leads_rsi_rebound(df["rsi"], df["mfi"])
    df["vol_ratio"] = sig.volume_exhaustion_ratio(df["volume"])

    df["s_weekly_trend"] = _score_weekly_trend(df["close"], df["ma20w"], df["ma20w_slope"])
    df["s_percent_b"] = _score_percent_b(df["percent_b"])
    df["s_rsi_divergence"] = _score_rsi_divergence(df["rsi_div_detected"], df["rsi_div_strength"])
    df["s_mfi_lead"] = df["mfi_lead_detected"].astype(float)
    df["s_squeeze_expansion"] = df["squeeze_exp_detected"].astype(float)
    df["s_volume_exhaustion"] = _score_volume_exhaustion(df["vol_ratio"])

    df["raw_score"] = (
        df["s_weekly_trend"] * WEIGHTS["weekly_trend"]
        + df["s_percent_b"] * WEIGHTS["percent_b"]
        + df["s_rsi_divergence"] * WEIGHTS["rsi_divergence"]
        + df["s_mfi_lead"] * WEIGHTS["mfi_lead"]
        + df["s_squeeze_expansion"] * WEIGHTS["squeeze_expansion"]
        + df["s_volume_exhaustion"] * WEIGHTS["volume_exhaustion"]
    )

    downtrend_regime = (df["adx"] >= 25) & (df["minus_di"] > df["plus_di"])
    df["regime_penalty_applied"] = downtrend_regime
    df["score"] = df["raw_score"].where(~downtrend_regime, df["raw_score"] * 0.3)
    df["score"] = df["score"].clip(lower=0, upper=100)

    df["verdict"] = np.select(
        [df["score"] >= STRONG_BUY_THRESHOLD, df["score"] >= WATCHLIST_THRESHOLD],
        ["강한매수후보", "관찰대상"],
        default="무시",
    )

    return df

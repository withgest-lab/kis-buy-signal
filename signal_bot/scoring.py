"""매수신호 스코어링 (PROJECT_PLAN.md 섹션 3-3)."""

import numpy as np
import pandas as pd

from signal_bot import indicators as ind
from signal_bot import signals as sig

# STEP 10 백테스트(13년치, 인샘플/아웃오브샘플 교차검증 + Bollinger/Cardwell/
# Faber·Siegel 등 문헌 대조)로 재조정한 가중치. 추세/밴드위치(구조적 상태
# 신호)보다 다이버전스/MFI선행/스퀴즈확장(확인성 신호) 비중을 높였다 —
# ablation 결과 이 조합이 아웃오브샘플에서 일관되게 더 나았음(2026-07-26).
WEIGHTS = {
    "weekly_trend": 15,
    "percent_b": 15,
    "rsi_divergence": 25,
    "mfi_lead": 20,
    "squeeze_expansion": 15,
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


def compute_components(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """지표/파생신호/항목별 0~1 점수까지 계산 (가중치를 곱하기 전 단계).

    가중치·하락추세 페널티는 combine_score()에서 적용한다 — 백테스트에서
    같은 지표 계산을 반복하지 않고 가중치 조합만 바꿔가며 빠르게 실험하기
    위해 분리했다 (PROJECT_PLAN.md 섹션 3-4 백테스트/기여도 검증)."""
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

    return df


def combine_score(df: pd.DataFrame, weights: dict = None,
                   apply_regime_penalty: bool = True,
                   regime_penalty_factor: float = 0.3) -> pd.DataFrame:
    """compute_components() 결과에 가중치를 곱해 최종 score/verdict를 만든다."""
    w = weights or WEIGHTS
    df = df.copy()

    df["raw_score"] = (
        df["s_weekly_trend"] * w["weekly_trend"]
        + df["s_percent_b"] * w["percent_b"]
        + df["s_rsi_divergence"] * w["rsi_divergence"]
        + df["s_mfi_lead"] * w["mfi_lead"]
        + df["s_squeeze_expansion"] * w["squeeze_expansion"]
        + df["s_volume_exhaustion"] * w["volume_exhaustion"]
    )

    downtrend_regime = (df["adx"] >= 25) & (df["minus_di"] > df["plus_di"])
    df["regime_penalty_applied"] = downtrend_regime
    if apply_regime_penalty:
        df["score"] = df["raw_score"].where(~downtrend_regime, df["raw_score"] * regime_penalty_factor)
    else:
        df["score"] = df["raw_score"]
    df["score"] = df["score"].clip(lower=0, upper=100)

    df["verdict"] = np.select(
        [df["score"] >= STRONG_BUY_THRESHOLD, df["score"] >= WATCHLIST_THRESHOLD],
        ["강한매수후보", "관찰대상"],
        default="무시",
    )
    return df


def compute_scores(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """daily/weekly: date 오름차순 정렬된 OHLCV DataFrame (kis_client.fetch_ohlcv 형식).
    Returns: daily에 지표/신호/점수 컬럼이 추가된 DataFrame. (운영 파이프라인은 이 함수만 씀)"""
    return combine_score(compute_components(daily, weekly))


# 시장(SPY) 전체가 하락 국면일 때 신규 진입 자체를 막는 필터. 개별종목 ADX
# 페널티(위)는 "그 종목 자체"만 보지만, 이건 시장 전체를 본다 — 백테스트에서
# 개별종목 지표(특히 %B·다이버전스)가 하락장에서 기준 대비 1.6~2.2배 과다
# 출현하는 걸 확인했고, Bollinger 본인("밴드 터치는 확인이 필요")과
# Faber(2007)/Siegel(1886~2006)의 200일선 시장타이밍 연구가 이 필터를
# 뒷받침한다 (PROJECT_PLAN.md 섹션 13, 2026-07-26).
MARKET_REGIME_BAND = 0.03


def market_regime(spy_close: pd.Series) -> str:
    """SPY 종가 시계열(오름차순)의 마지막 값 기준 오늘의 시장 국면 판정."""
    sma200 = spy_close.rolling(200).mean()
    if pd.isna(sma200.iloc[-1]):
        return "판정불가"
    ratio = spy_close.iloc[-1] / sma200.iloc[-1]
    if ratio >= 1 + MARKET_REGIME_BAND:
        return "상승장"
    if ratio <= 1 - MARKET_REGIME_BAND:
        return "하락장"
    return "횡보장"


def apply_market_filter(df: pd.DataFrame, regime: str) -> pd.DataFrame:
    """시장 전체가 하락장이면 이 종목의 오늘 점수를 0으로 눌러 신규 진입을 막는다."""
    if regime != "하락장":
        return df
    df = df.copy()
    df.loc[df.index[-1], "score"] = 0.0
    df.loc[df.index[-1], "verdict"] = "무시"
    return df

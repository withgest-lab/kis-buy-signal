"""일/주/월 시간대별 RSI/MFI/다이버전스 계산.

주봉/월봉은 별도 API 호출 없이, 일봉 데이터를 pandas로 리샘플링해서 만든다.
월봉 RSI(14)는 워밍업에 최소 14개월+가 필요해서 운영용 250일(약 1년) 일봉만으론
부족하므로, MDD 계산용으로 이미 받아둔 20년치 baseline 일봉을 합쳐서(중복일
제거, 운영용이 있으면 그쪽을 우선) 리샘플링한다 - 추가 API 호출 없음.

`compute_timeframe_frames()`는 전체 시계열(대시보드 차트용)을, 그 위의
`compute_multi_timeframe_signals()`는 오늘자 스냅샷 값만(운영 파이프라인/알림용)
반환한다 - 지표 계산 로직은 한 곳(`_indicator_frame`)에서만 수행.
"""

from typing import Optional

import pandas as pd

from signal_bot import indicators as ind
from signal_bot import signals as sig
from signal_bot.config import RSI_OVERSOLD, MFI_OVERSOLD

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def _resample(daily: pd.DataFrame, rule: str) -> pd.DataFrame:
    df = daily.set_index("date").resample(rule).agg(_AGG).dropna(subset=["close"])
    return df.reset_index()


def combined_daily(baseline_daily: Optional[pd.DataFrame], recent_daily: pd.DataFrame) -> pd.DataFrame:
    """baseline(20년, 월1회 갱신) + 운영용(최근 250일, 매일 갱신)을 날짜기준
    합쳐서(운영용 우선) 주/월봉 리샘플링용 워밍업 데이터를 만든다."""
    recent = recent_daily.sort_values("date").reset_index(drop=True)
    if baseline_daily is None or baseline_daily.empty:
        return recent
    cutoff = recent["date"].min()
    older = baseline_daily[baseline_daily["date"] < cutoff]
    combined = pd.concat([older, recent], ignore_index=True)
    return combined.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)


def _indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    """date/close에 rsi/mfi/divergence(그 바에서 감지됐는지) 컬럼을 추가."""
    out = df.copy()
    out["rsi"] = ind.rsi(out["close"])
    out["mfi"] = ind.mfi(out["high"], out["low"], out["close"], out["volume"])
    div_rsi = sig.bullish_divergence(out["close"], out["rsi"])
    div_mfi = sig.bullish_divergence(out["close"], out["mfi"])
    out["divergence"] = (div_rsi["detected"] | div_mfi["detected"]).values
    return out


def _timeframe_snapshot(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"rsi": None, "mfi": None, "divergence": False,
                "rsi_oversold": False, "mfi_oversold": False}

    last = frame.iloc[-1]
    rsi_val, mfi_val = last["rsi"], last["mfi"]
    return {
        "rsi": None if pd.isna(rsi_val) else round(float(rsi_val), 1),
        "mfi": None if pd.isna(mfi_val) else round(float(mfi_val), 1),
        "divergence": bool(last["divergence"]),
        "rsi_oversold": bool(pd.notna(rsi_val) and rsi_val <= RSI_OVERSOLD),
        "mfi_oversold": bool(pd.notna(mfi_val) and mfi_val <= MFI_OVERSOLD),
    }


def compute_timeframe_frames(recent_daily: pd.DataFrame,
                              baseline_daily: Optional[pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """대시보드 차트용 - 시간대별 전체 시계열(date/close/rsi/mfi/divergence).

    "daily"도 운영용 250일치만이 아니라 baseline과 합친 전체 기간으로 계산한다 -
    대시보드 기간 선택(1Y~ALL)에서 일봉 그래프를 여러 해 단위로 확대해서 볼 수
    있으려면 일봉 시계열 자체가 그만큼 길어야 하기 때문(주/월봉과 동일한 이유)."""
    combined = combined_daily(baseline_daily, recent_daily)
    weekly = _resample(combined, "W")
    monthly = _resample(combined, "ME")
    return {
        "daily": _indicator_frame(combined),
        "weekly": _indicator_frame(weekly),
        "monthly": _indicator_frame(monthly),
    }


def compute_multi_timeframe_signals(recent_daily: pd.DataFrame,
                                     baseline_daily: Optional[pd.DataFrame]) -> dict:
    """운영 파이프라인/알림용 - 오늘자 스냅샷만.
    Returns: {"daily": {...}, "weekly": {...}, "monthly": {...}} (각 항목은
    rsi/mfi/divergence/rsi_oversold/mfi_oversold)."""
    frames = compute_timeframe_frames(recent_daily, baseline_daily)
    return {tf: _timeframe_snapshot(frame) for tf, frame in frames.items()}

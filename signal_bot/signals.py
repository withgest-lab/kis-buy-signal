"""파생 신호 계산 함수 (PROJECT_PLAN.md 섹션 3-2)."""

import pandas as pd


def bullish_divergence(close: pd.Series, indicator: pd.Series,
                        lookback: int = 30, min_gap: int = 5) -> pd.DataFrame:
    """RSI/MFI 강세 다이버전스.

    오늘이 최근 `lookback`일 내 가격 최저점이면서(신저점), 그 이전 저점(A) 대비
    indicator 값이 더 높으면 감지. 신호는 신저점이 찍힌 당일에 발생한다.

    Returns: DataFrame(detected: bool, strength: 0~1)
    """
    n = len(close)
    detected = pd.Series(False, index=close.index)
    strength = pd.Series(0.0, index=close.index)

    for t in range(lookback, n):
        window_start = t - lookback
        window = close.iloc[window_start:t + 1]
        pos_b = close.index.get_loc(window.idxmin())
        if pos_b != t:
            continue  # 오늘이 구간 내 최저점이 아니면 다이버전스 대상 아님

        early_end = pos_b - min_gap
        if early_end <= window_start:
            continue
        window_a = close.iloc[window_start:early_end + 1]
        pos_a = close.index.get_loc(window_a.idxmin())

        price_a, price_b = close.iloc[pos_a], close.iloc[pos_b]
        ind_a, ind_b = indicator.iloc[pos_a], indicator.iloc[pos_b]
        if pd.isna(ind_a) or pd.isna(ind_b):
            continue

        if price_b < price_a and ind_b > ind_a:
            detected.iloc[t] = True
            strength.iloc[t] = min(1.0, max(0.0, (ind_b - ind_a) / 20.0))

    return pd.DataFrame({"detected": detected, "strength": strength})


def bollinger_squeeze_expansion(bandwidth: pd.Series, lookback: int = 120,
                                 percentile: float = 0.2) -> pd.Series:
    """볼린저 스퀴즈->확장. 전날이 최근 120일 하위 20% 구간(스퀴즈)이었다가
    오늘 bandwidth가 전날보다 커지면(확장 전환) 감지."""
    pct_rank = bandwidth.rolling(lookback).apply(
        lambda x: (x <= x[-1]).mean(), raw=True
    )
    in_squeeze = pct_rank <= percentile
    was_squeeze_yesterday = in_squeeze.shift(1, fill_value=False)
    expanding_today = bandwidth.diff() > 0
    return was_squeeze_yesterday & expanding_today


def _last_turn_offset(series: pd.Series, t: int, window: int):
    """t 시점 기준 최근 `window`일 내에서 하락->상승으로 꺾인 가장 최근 저점의
    오프셋(t로부터 며칠 전인지)을 반환. 없으면 None."""
    for i in range(t, max(t - window, 2) - 1, -1):
        if series.iloc[i] > series.iloc[i - 1] and series.iloc[i - 1] <= series.iloc[i - 2]:
            return t - (i - 1)
    return None


def mfi_leads_rsi_rebound(rsi: pd.Series, mfi: pd.Series, window: int = 5) -> pd.Series:
    """MFI 선행반등. 최근 `window`일 내 MFI가 RSI보다 먼저(더 과거 시점에) 저점을
    찍고 반등 전환했으면 감지. RSI가 아직 저점을 못 찍었다면, 그 구간 동안 RSI가
    순수 하락/횡보 중이었을 때만(이미 상승 추세인데 우연히 트리거되는 것 방지) 인정."""
    detected = pd.Series(False, index=rsi.index)
    for t in range(window + 2, len(rsi)):
        mfi_offset = _last_turn_offset(mfi, t, window)
        if mfi_offset is None:
            continue
        rsi_offset = _last_turn_offset(rsi, t, window)
        if rsi_offset is not None:
            if mfi_offset > rsi_offset:  # offset이 클수록 더 과거 저점
                detected.iloc[t] = True
        elif rsi.iloc[t] <= rsi.iloc[t - window]:
            detected.iloc[t] = True
    return detected


def volume_exhaustion_ratio(volume: pd.Series, short: int = 5, long: int = 20) -> pd.Series:
    """최근 5일 평균 거래량 / 최근 20일 평균 거래량. 1보다 작을수록 거래량 감소(소진)."""
    vol_short = volume.rolling(short).mean()
    vol_long = volume.rolling(long).mean()
    return vol_short / vol_long

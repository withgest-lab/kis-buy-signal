"""파생 신호 계산 함수 (RSI/MFI 강세 다이버전스)."""

import pandas as pd


def bullish_divergence(close: pd.Series, indicator: pd.Series,
                        lookback: int = 30, min_gap: int = 5) -> pd.DataFrame:
    """RSI/MFI 강세 다이버전스.

    오늘이 최근 `lookback`바(bar) 내 가격 최저점이면서(신저점), 그 이전 저점(A) 대비
    indicator 값이 더 높으면 감지. 신호는 신저점이 찍힌 당일에 발생한다.
    일봉/주봉/월봉 어디에 써도 동일하게 동작(lookback 단위가 그 시간대의 바 개수).

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

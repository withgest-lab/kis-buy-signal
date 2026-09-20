"""기본 지표 계산 함수 (RSI/MFI).

입력은 date 오름차순으로 정렬된 DataFrame/Series여야 하며, close/high/low/volume
컬럼을 사용한다 (signal_bot.kis_client.fetch_ohlcv 결과 형식과 동일).
"""

import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI. Wilder's smoothing (ewm alpha=1/period, adjust=False)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
        period: int = 14) -> pd.Series:
    """MFI. Typical Price(고저종평균) x 거래량 기반 자금흐름비율."""
    typical_price = (high + low + close) / 3
    money_flow = typical_price * volume
    tp_diff = typical_price.diff()

    positive_flow = money_flow.where(tp_diff > 0, 0.0)
    negative_flow = money_flow.where(tp_diff < 0, 0.0)

    positive_sum = positive_flow.rolling(period).sum()
    negative_sum = negative_flow.rolling(period).sum()

    money_ratio = positive_sum / negative_sum
    return 100 - (100 / (1 + money_ratio))

"""기본 지표 계산 함수 (PROJECT_PLAN.md 섹션 3-1).

입력은 date 오름차순으로 정렬된 DataFrame이어야 하며, close/high/low/volume
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


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """볼린저밴드. mid/upper/lower + %B + Bandwidth."""
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)

    upper = mid + num_std * std
    lower = mid - num_std * std

    percent_b = (close - lower) / (upper - lower)
    bandwidth = (upper - lower) / mid

    return pd.DataFrame({
        "bb_mid": mid,
        "bb_upper": upper,
        "bb_lower": lower,
        "percent_b": percent_b,
        "bandwidth": bandwidth,
    })


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    """ADX + DI. 표준 Wilder's smoothing 공식."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_dm = plus_dm.clip(lower=0)
    minus_dm = minus_dm.clip(lower=0)

    prev_close = close.shift()
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()

    return pd.DataFrame({
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx_val,
    })


def weekly_ma(weekly_close: pd.Series, period: int = 20) -> pd.DataFrame:
    """주봉 이동평균 + 기울기(전주 대비 증감)."""
    ma = weekly_close.rolling(period).mean()
    slope = ma.diff()
    return pd.DataFrame({
        "ma20w": ma,
        "ma20w_slope": slope,
    })

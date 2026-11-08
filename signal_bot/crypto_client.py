"""비트코인 현물 일봉 - 코인베이스 공개 시세 API(키 불필요).

KIS Open API에는 코인 시세가 없어서 BTC만 여기서 받는다(IBIT 같은 미국 상장 비트코인 ETF는 kis_client 그대로).
출력 열은 kis_client.fetch_ohlcv와 같다(date + close/open/high/low/volume) — 이후 계산(MDD·RSI/MFI·매도)은 그대로 쓴다.

- 일봉 경계는 UTC 자정. 실행 시점에 아직 끝나지 않은 UTC 당일 봉은 버린다(종가가 아니라서).
- 이 시스템은 연 252봉(52주=250봉, 12개월=252봉, 화면 기간 환산 ÷252·÷21)을 가정하므로, 코인의 주말 봉은
  다음 월요일 봉에 합친다(시가=토요일 시가, 고가·저가=사흘 최고·최저, 종가=월요일 종가, 거래량=합). 주말 동안의
  가격 변화는 월요일 종가에 그대로 반영된다. 월요일 봉이 아직 끝나지 않았으면 남은 주말 봉은 다음 실행 때 합친다.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

API = "https://api.exchange.coinbase.com/products/{product}/candles"
PAGE_DAYS = 300                    # 요청당 최대 봉 수
HISTORY_START = datetime(2015, 7, 20, tzinfo=timezone.utc)   # 코인베이스 BTC-USD 첫 거래일
TIMEOUT = 20
HEADERS = {"User-Agent": "kis-buy-signal/1.0"}


def _fetch_page(product: str, start: datetime, end: datetime) -> list[list]:
    res = requests.get(API.format(product=product), headers=HEADERS, timeout=TIMEOUT, params={
        "granularity": 86400, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    res.raise_for_status()
    rows = res.json()
    if not isinstance(rows, list):
        raise RuntimeError(f"코인베이스 응답 형식 오류: {str(rows)[:200]}")
    return rows


def fold_weekends(raw: pd.DataFrame) -> pd.DataFrame:
    """UTC 일봉(7일) → 평일 봉. 토·일 봉은 다음 월요일 봉에 합치고, 월요일 봉이 없는(아직 안 끝난) 주말은 버린다."""
    df = raw.sort_values("date").reset_index(drop=True)
    wd = df["date"].dt.weekday
    df["bar"] = df["date"] + pd.to_timedelta((7 - wd).where(wd >= 5, 0), unit="D")
    present = set(df.loc[wd < 5, "date"])
    df = df[df["bar"].isin(present)]
    out = df.groupby("bar", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum"),
    ).reset_index().rename(columns={"bar": "date"})
    return out[["date", "close", "open", "high", "low", "volume"]]


def fetch_ohlcv_crypto(product: str, min_rows: int, now: datetime | None = None) -> pd.DataFrame:
    """최근부터 과거로 300일씩 받아 평일 봉이 min_rows 이상 모이거나 상장일에 닿으면 멈춘다."""
    now = now or datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)   # 이 시각 이후 봉은 진행 중
    rows: list[list] = []
    end = today
    while end > HISTORY_START:
        start = max(end - timedelta(days=PAGE_DAYS), HISTORY_START)
        page = _fetch_page(product, start, end)
        rows.extend(page)
        # 평일 봉 수(주말 제외 ≈ 5/7) 기준으로 충분하면 멈춘다
        if len(rows) * 5 / 7 >= min_rows + 10:
            break
        end = start
    if not rows:
        raise RuntimeError(f"{product} 일봉 없음")
    raw = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    raw["date"] = pd.to_datetime(raw["time"], unit="s", utc=True).dt.tz_localize(None).dt.normalize()
    raw = raw[raw["date"] < pd.Timestamp(today.replace(tzinfo=None))]
    raw = raw.drop_duplicates(subset="date")
    for c in ("low", "high", "open", "close", "volume"):
        raw[c] = raw[c].astype(float)
    return fold_weekends(raw[["date", "open", "high", "low", "close", "volume"]])

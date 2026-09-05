"""MDD(최대낙폭) 백분위 기반 매수신호 계산.

낙폭 국면(peak-to-trough episode)을 추출해서, 완결된(신고가로 복귀 완료한)
국면들의 depth 분포에서 비파라메트릭 백분위(P50/P25/P10)를 산출하고, 오늘의
진행중 낙폭을 그 분포와 비교해 3단계로 판정한다. 평균/표준편차 대신 경험적
백분위를 쓰는 이유는 낙폭 분포가 두꺼운 꼬리(소수의 극단치)를 가져서다.
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

DATA_DIR = Path("signal_bot/data")
BASELINE_DIR = DATA_DIR / "baseline"
BASELINE_PATH = DATA_DIR / "mdd_baseline.json"

MIN_EPISODE_DEPTH = -0.05       # -5% 이내 낙폭은 노이즈로 국면 불인정
MIN_EPISODES_REQUIRED = 5       # 완결국면이 이보다 적으면 베이스라인 데이터 부족

MARKET_REGIME_BAND = 0.03


def compute_drawdown(close: pd.Series) -> pd.DataFrame:
    """종가 시계열(오름차순)에서 롤링 신고가와 drawdown(<=0)을 계산."""
    rolling_max = close.cummax()
    drawdown = close / rolling_max - 1.0
    return pd.DataFrame({"rolling_max": rolling_max, "drawdown": drawdown})


def extract_episodes(dates: pd.Series, drawdown: pd.Series,
                      min_depth: float = MIN_EPISODE_DEPTH) -> list[dict]:
    """낙폭 국면 추출. 신고가 갱신 시점마다 국면이 끝나고(완결), 그 다음
    신고가 이탈 시점부터 새 국면이 시작된다. 마지막까지 신고가로 복귀하지
    못했으면 진행중(is_complete=False) 국면 하나가 남는다."""
    dates = list(dates)
    dd = list(drawdown)
    episodes: list[dict] = []

    in_episode = False
    start_idx = trough_idx = None
    trough_depth = 0.0

    for i, d in enumerate(dd):
        at_high = d >= -1e-9
        if at_high:
            if in_episode:
                if trough_depth <= min_depth:
                    episodes.append({
                        "start_date": str(dates[start_idx].date()),
                        "trough_date": str(dates[trough_idx].date()),
                        "recovery_date": str(dates[i].date()),
                        "depth": round(trough_depth, 4),
                        "recovery_days": i - start_idx,
                        "is_complete": True,
                    })
                in_episode = False
        else:
            if not in_episode:
                in_episode = True
                start_idx = i
                trough_idx = i
                trough_depth = d
            elif d < trough_depth:
                trough_depth = d
                trough_idx = i

    if in_episode and trough_depth <= min_depth:
        episodes.append({
            "start_date": str(dates[start_idx].date()),
            "trough_date": str(dates[trough_idx].date()),
            "recovery_date": None,
            "depth": round(trough_depth, 4),
            "recovery_days": None,
            "is_complete": False,
        })

    return episodes


def percentile_stats(episodes: list[dict]) -> Optional[dict]:
    """완결국면 depth 분포의 P50/P25/P10(비파라메트릭) + 회복기간(거래일) 통계.
    완결국면이 MIN_EPISODES_REQUIRED보다 적으면 None(베이스라인 데이터 부족)."""
    completed = [e for e in episodes if e["is_complete"]]
    if len(completed) < MIN_EPISODES_REQUIRED:
        return None

    depths = np.array([e["depth"] for e in completed])
    recovery = np.array([e["recovery_days"] for e in completed])
    return {
        "count": len(completed),
        "p50": float(np.percentile(depths, 50)),
        "p25": float(np.percentile(depths, 25)),
        "p10": float(np.percentile(depths, 10)),
        "recovery_days_min": int(recovery.min()),
        "recovery_days_median": int(np.median(recovery)),
        "recovery_days_max": int(recovery.max()),
    }


def classify_stage(depth: float, percentiles: Optional[dict]) -> int:
    """0=신호없음, 1=관찰(P50 수준), 2=깊은낙폭(P25 수준), 3=극단(P10 수준).
    percentiles의 p10<=p25<=p50<=0 순서를 이용 — 더 깊을수록(더 음수) 더 높은 단계."""
    if percentiles is None:
        return 0
    if depth <= percentiles["p10"]:
        return 3
    if depth <= percentiles["p25"]:
        return 2
    if depth <= percentiles["p50"]:
        return 1
    return 0


def is_record_drawdown(depth: float, episodes: list[dict]) -> bool:
    """오늘 depth가 과거 모든 완결국면보다 깊으면(사상 최대 낙폭) True."""
    completed = [e for e in episodes if e["is_complete"]]
    if not completed:
        return False
    deepest = min(e["depth"] for e in completed)
    return depth < deepest


def build_baseline_for_symbol(symb: str) -> dict:
    """signal_bot/data/baseline/{symb}_daily.csv 전체로 무거운 전체 재계산
    (월 1회 빈도로 호출됨)."""
    path = BASELINE_DIR / f"{symb}_daily.csv"
    if not path.exists():
        return {"insufficient_data": True, "error": "baseline csv 없음"}

    df = pd.read_csv(path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    if len(df) < 30:
        return {"insufficient_data": True, "error": "데이터 부족"}

    dd = compute_drawdown(df["close"])
    episodes = extract_episodes(df["date"], dd["drawdown"])
    stats = percentile_stats(episodes)

    return {
        "as_of_date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "rolling_high": float(dd["rolling_max"].iloc[-1]),
        "episodes": episodes,
        "percentiles": stats,
        "insufficient_data": stats is None,
    }


def build_all_baselines(tickers: list[tuple[str, str]]) -> dict:
    """tickers: [(category, symb), ...]. mdd_baseline.json에 저장 후 반환."""
    baseline: dict = {}
    for _category, symb in tickers:
        try:
            baseline[symb] = build_baseline_for_symbol(symb)
        except Exception as e:
            baseline[symb] = {"insufficient_data": True, "error": str(e)}

    DATA_DIR.mkdir(exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    return baseline


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    with open(BASELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def update_today_state(baseline_entry: dict, recent_daily: pd.DataFrame) -> dict:
    """매일 가벼운 증분 갱신. recent_daily: 운영용 daily CSV(date 오름차순).
    baseline 기준일 이후~오늘까지의 종가로 캐시된 rolling_high를 갱신
    (추가 API 호출 없이 이미 받아둔 운영용 데이터만 사용)."""
    rolling_high = float(baseline_entry["rolling_high"])
    as_of = pd.Timestamp(baseline_entry["as_of_date"])

    since = recent_daily[recent_daily["date"] > as_of]
    if not since.empty:
        rolling_high = max(rolling_high, float(since["close"].max()))

    today_close = float(recent_daily["close"].iloc[-1])
    rolling_high = max(rolling_high, today_close)
    depth = today_close / rolling_high - 1.0
    return {"rolling_high": rolling_high, "depth": depth, "close": today_close}


def market_regime(index_close: pd.Series) -> str:
    """지수(SPY/KOSPI200 등) 종가 시계열(오름차순)의 200일선 대비 오늘의 국면.
    참고정보 전용 — 신호를 차단하지 않는다(대시보드에서만 선택적으로 사용)."""
    sma200 = index_close.rolling(200).mean()
    if pd.isna(sma200.iloc[-1]):
        return "판정불가"
    ratio = index_close.iloc[-1] / sma200.iloc[-1]
    if ratio >= 1 + MARKET_REGIME_BAND:
        return "상승장"
    if ratio <= 1 - MARKET_REGIME_BAND:
        return "하락장"
    return "횡보장"

"""STEP 11: 대시보드용 scores.json 생성 (PROJECT_PLAN.md 섹션 10).

history.json(전체 이력)에는 계좌/키 정보가 없지만, 혹시 모를 확장에 대비해
scores.json에는 섹션 10 스펙대로 종목코드/점수/세부신호/현재가/타임스탬프만 담는다.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from signal_bot import alerts
from signal_bot import indicators as ind
from signal_bot.config import TICKERS
from signal_bot.pipeline import DATA_DIR, load_history
from signal_bot.scoring import compute_components, compute_scores

OUTPUT_PATH = Path("docs/scores.json")
DETAIL_DIR = Path("docs/detail")
SPARKLINE_DAYS = 30
DETAIL_CHART_DAYS = 150
WEEKLY_CHART_WEEKS = 156  # 약 3년치 - 3~6개월 이상 보유 관점에서 큰 흐름을 보기 위함
RECENT_SIGNAL_DAYS = 3  # "최근 감지 이력" 배지용 - 점수 자체엔 영향 없음(정보 표시 전용)
KST = timezone(timedelta(hours=9))


def _recent_signal_flags(symb: str) -> dict | None:
    """오늘은 꺼졌지만 최근 며칠 내 감지된 적 있는 신호를 정보용으로 표시하기
    위한 값. 백테스트 결과 점수 계산 자체에 지속성을 넣으면 오히려 우위가
    희석돼서(2026-07-26 검증), 점수/알림 로직은 그대로 두고 화면에만 참고
    표시를 추가한다."""
    daily_path = DATA_DIR / f"{symb}_daily.csv"
    weekly_path = DATA_DIR / f"{symb}_weekly.csv"
    if not daily_path.exists() or not weekly_path.exists():
        return None
    daily = pd.read_csv(daily_path, parse_dates=["date"])
    weekly = pd.read_csv(weekly_path, parse_dates=["date"])
    df = compute_components(daily, weekly, signal_persistence_days=1).tail(RECENT_SIGNAL_DAYS)
    return {
        "divergence": bool(df["rsi_div_detected"].any()),
        "squeeze": bool(df["squeeze_exp_detected"].any()),
        "mfi_lead": bool(df["mfi_lead_detected"].any()),
    }


def _compute_volatility(symb: str) -> float | None:
    """연율화 일간수익률 변동성(표준편차x sqrt(252)). 낮을수록 '우량주다움'에
    가깝다는 프록시로 대시보드 "우량주 우선" 정렬 2차 기준에 쓴다
    (STEP 10 백테스트의 변동성 3등분 로직과 같은 방식, PROJECT_PLAN.md 섹션 14)."""
    daily_path = DATA_DIR / f"{symb}_daily.csv"
    if not daily_path.exists():
        return None
    daily = pd.read_csv(daily_path)
    rets = daily["close"].pct_change().dropna()
    if len(rets) < 20:
        return None
    return round(float(rets.std() * (252 ** 0.5)), 4)


def _build_sparkline(history: dict, symb: str, dates: list[str]) -> list[dict]:
    points = []
    for d in dates:
        rec = history.get(d, {}).get(symb)
        if rec:
            points.append({"date": d, "score": rec["score"]})
    return points


def _series_records(df: pd.DataFrame) -> list[dict]:
    records = []
    for _, r in df.iterrows():
        records.append({
            "date": r["date"].strftime("%Y-%m-%d"),
            "close": round(float(r["close"]), 2),
            "bb_upper": None if pd.isna(r["bb_upper"]) else round(float(r["bb_upper"]), 2),
            "bb_mid": None if pd.isna(r["bb_mid"]) else round(float(r["bb_mid"]), 2),
            "bb_lower": None if pd.isna(r["bb_lower"]) else round(float(r["bb_lower"]), 2),
            "rsi": None if pd.isna(r["rsi"]) else round(float(r["rsi"]), 1),
            "mfi": None if pd.isna(r["mfi"]) else round(float(r["mfi"]), 1),
        })
    return records


def _build_detail(symb: str) -> dict | None:
    """카드 상세뷰용 가격+볼린저밴드+RSI+MFI 시계열(일봉+주봉). 필요할 때만 프론트에서 lazy fetch."""
    daily_path = DATA_DIR / f"{symb}_daily.csv"
    weekly_path = DATA_DIR / f"{symb}_weekly.csv"
    if not daily_path.exists() or not weekly_path.exists():
        return None

    daily = pd.read_csv(daily_path, parse_dates=["date"])
    weekly = pd.read_csv(weekly_path, parse_dates=["date"])

    daily_df = compute_scores(daily, weekly).tail(DETAIL_CHART_DAYS)

    weekly_df = weekly.copy()
    weekly_df["rsi"] = ind.rsi(weekly_df["close"])
    weekly_df["mfi"] = ind.mfi(weekly_df["high"], weekly_df["low"], weekly_df["close"], weekly_df["volume"])
    weekly_df = pd.concat([weekly_df, ind.bollinger(weekly_df["close"])], axis=1)
    weekly_df = weekly_df.tail(WEEKLY_CHART_WEEKS)

    return {"daily": _series_records(daily_df), "weekly": _series_records(weekly_df)}


def export_details() -> int:
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for _category, symb in TICKERS:
        detail = _build_detail(symb)
        if detail is None:
            continue
        with open(DETAIL_DIR / f"{symb}.json", "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False)
        count += 1
    return count


def main():
    history = load_history()
    if not history:
        raise RuntimeError("history.json이 비어있습니다. main.py를 먼저 실행해서 이력을 만들어주세요.")

    dates = sorted(history.keys())
    today = dates[-1]
    sparkline_dates = dates[-SPARKLINE_DAYS:]

    new_signals = alerts.find_new_strong_signals(history, today)
    new_symbs = {r["symb"] for r in new_signals}

    tickers = []
    for symb, rec in history[today].items():
        entry = dict(rec)
        entry["is_new"] = symb in new_symbs
        entry["sparkline"] = _build_sparkline(history, symb, sparkline_dates)
        entry["volatility"] = _compute_volatility(symb)
        entry["recent_detected"] = _recent_signal_flags(symb)
        tickers.append(entry)

    tickers.sort(key=lambda r: r["score"], reverse=True)

    payload = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "as_of_date": today,
        "market_regime": tickers[0].get("market_regime", "판정불가") if tickers else "판정불가",
        "tickers": tickers,
    }

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"대시보드 데이터 저장 완료: {OUTPUT_PATH} ({len(tickers)}종목, 신규 신호 {len(new_symbs)}개)")

    detail_count = export_details()
    print(f"상세 차트 데이터 저장 완료: {DETAIL_DIR}/ ({detail_count}개 종목)")


if __name__ == "__main__":
    main()

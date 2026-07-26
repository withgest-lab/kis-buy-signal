"""STEP 7: 32개 종목 전체 파이프라인 - 점수/판정/세부신호 표 출력 + JSON 이력 저장.

실행 전 signal_bot/fetch_universe.py로 최신 시세를 먼저 받아둬야 한다.
"""

import json
from pathlib import Path

import pandas as pd

from signal_bot import alerts
from signal_bot import indicators as ind
from signal_bot.config import HISTORY_MAX_DAYS, TICKER_NAMES, TICKERS
from signal_bot.notifier import send_telegram_message
from signal_bot.scoring import apply_market_filter, compute_scores, market_regime

DATA_DIR = Path("signal_bot/data")
HISTORY_PATH = DATA_DIR / "history.json"

# "일봉+주봉 둘 다 볼린저 하단터치 + RSI/MFI 과매도" 필터 기준 (사용자 요청,
# 2026-07-26). %B<=0.1은 기존 오버솔드 백테스트(PROJECT_PLAN.md 섹션 14)와
# 동일 기준, RSI/MFI<=35도 마찬가지.
PULLBACK_PERCENT_B_MAX = 0.1
PULLBACK_RSI_MFI_MAX = 35


def _is_oversold(percent_b: float, rsi: float, mfi: float) -> bool:
    return percent_b <= PULLBACK_PERCENT_B_MAX and (rsi <= PULLBACK_RSI_MFI_MAX or mfi <= PULLBACK_RSI_MFI_MAX)


def _weekly_indicators(weekly: pd.DataFrame) -> pd.Series:
    """주봉 자체의 RSI/MFI/%B (compute_scores는 주봉추세 필터용 20주선만 쓰고
    주봉 자체 RSI/MFI/볼린저는 계산 안 해서 별도 계산)."""
    w = weekly.copy()
    w["rsi"] = ind.rsi(w["close"])
    w["mfi"] = ind.mfi(w["high"], w["low"], w["close"], w["volume"])
    w = pd.concat([w, ind.bollinger(w["close"])], axis=1)
    return w.iloc[-1]


def load_history() -> dict:
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history: dict) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def trim_history(history: dict, max_days: int = HISTORY_MAX_DAYS) -> dict:
    """최근 max_days 거래일만 남기고 그 이전 날짜는 버린다 (저장소 용량 무한증가 방지)."""
    dates = sorted(history.keys())
    if len(dates) <= max_days:
        return history
    keep = set(dates[-max_days:])
    return {d: rec for d, rec in history.items() if d in keep}


def _signal_summary(row: pd.Series) -> str:
    tags = []
    if row["rsi_div_detected"]:
        tags.append("다이버전스")
    if row["squeeze_exp_detected"]:
        tags.append("스퀴즈확장")
    if row["mfi_lead_detected"]:
        tags.append("MFI선행")
    if row["s_volume_exhaustion"] > 0:
        tags.append("거래량소진")
    return ",".join(tags) if tags else "-"


def _today_market_regime() -> str:
    spy_path = DATA_DIR / "SPY_daily.csv"
    if not spy_path.exists():
        return "판정불가"
    spy = pd.read_csv(spy_path, parse_dates=["date"])
    return market_regime(spy["close"])


def run() -> list[dict]:
    regime = _today_market_regime()
    results = []
    errors = []
    for category, symb in TICKERS:
        daily_path = DATA_DIR / f"{symb}_daily.csv"
        weekly_path = DATA_DIR / f"{symb}_weekly.csv"
        if not daily_path.exists() or not weekly_path.exists():
            errors.append((symb, "데이터 없음 (fetch_universe.py 먼저 실행 필요)"))
            continue
        try:
            daily = pd.read_csv(daily_path, parse_dates=["date"])
            weekly = pd.read_csv(weekly_path, parse_dates=["date"])
            df = compute_scores(daily, weekly)
            df = apply_market_filter(df, regime)
        except Exception as e:
            errors.append((symb, str(e)))
            continue

        last = df.iloc[-1]
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
        pct_chg = (float(last["close"]) - prev_close) / prev_close * 100 if prev_close else 0.0

        last_w = _weekly_indicators(weekly)
        daily_oversold = _is_oversold(last["percent_b"], last["rsi"], last["mfi"])
        weekly_oversold = (
            pd.notna(last_w["percent_b"]) and pd.notna(last_w["rsi"]) and pd.notna(last_w["mfi"])
            and _is_oversold(last_w["percent_b"], last_w["rsi"], last_w["mfi"])
        )

        results.append({
            "category": category,
            "symb": symb,
            "name": TICKER_NAMES.get(symb, symb),
            "date": last["date"].strftime("%Y-%m-%d"),
            "close": round(float(last["close"]), 2),
            "pct_chg": round(pct_chg, 2),
            "score": round(float(last["score"]), 1),
            "verdict": str(last["verdict"]),
            "signals": _signal_summary(last),
            "detected": {
                "divergence": bool(last["rsi_div_detected"]),
                "squeeze": bool(last["squeeze_exp_detected"]),
                "mfi_lead": bool(last["mfi_lead_detected"]),
                "vol_exhaustion": bool(last["s_volume_exhaustion"] > 0),
            },
            "breakdown": {
                "weekly_trend": round(float(last["s_weekly_trend"]), 2),
                "percent_b": round(float(last["s_percent_b"]), 2),
                "rsi_divergence": round(float(last["s_rsi_divergence"]), 2),
                "mfi_lead": round(float(last["s_mfi_lead"]), 2),
                "squeeze_expansion": round(float(last["s_squeeze_expansion"]), 2),
                "volume_exhaustion": round(float(last["s_volume_exhaustion"]), 2),
            },
            "adx": round(float(last["adx"]), 1),
            "regime_penalty": bool(last["regime_penalty_applied"]),
            "market_regime": regime,
            "pullback_raw": {
                "daily_percent_b": None if pd.isna(last["percent_b"]) else round(float(last["percent_b"]), 3),
                "daily_rsi": None if pd.isna(last["rsi"]) else round(float(last["rsi"]), 1),
                "daily_mfi": None if pd.isna(last["mfi"]) else round(float(last["mfi"]), 1),
                "weekly_percent_b": None if pd.isna(last_w["percent_b"]) else round(float(last_w["percent_b"]), 3),
                "weekly_rsi": None if pd.isna(last_w["rsi"]) else round(float(last_w["rsi"]), 1),
                "weekly_mfi": None if pd.isna(last_w["mfi"]) else round(float(last_w["mfi"]), 1),
            },
            "pullback_candidate": bool(daily_oversold and weekly_oversold),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results, errors


def print_report(results: list[dict], errors: list[tuple]) -> None:
    if results:
        print(f"오늘의 시장(SPY) 국면: {results[0]['market_regime']}"
              + (" - 신규 강한매수후보 진입 차단 중" if results[0]["market_regime"] == "하락장" else ""))
        print()
    print(f"{'종목':6s} {'분류':8s} {'점수':>6s} {'판정':10s} {'현재가':>10s}  세부신호")
    print("-" * 72)
    for r in results:
        print(f"{r['symb']:6s} {r['category']:8s} {r['score']:6.1f} {r['verdict']:10s} {r['close']:10.2f}  {r['signals']}")

    if errors:
        print("\n실패:")
        for symb, msg in errors:
            print(f"  {symb}: {msg}")

    strong = [r for r in results if r["verdict"] == "강한매수후보"]
    watch = [r for r in results if r["verdict"] == "관찰대상"]
    pullback = [r for r in results if r["pullback_candidate"]]
    print(f"\n{len(results)}/{len(TICKERS)} 종목 점수 산출 완료 "
          f"(강한매수후보 {len(strong)}개, 관찰대상 {len(watch)}개, "
          f"일봉+주봉 과매도 후보 {len(pullback)}개)")


def main():
    results, errors = run()
    print_report(results, errors)

    if not results:
        return

    today = results[0]["date"]
    history = load_history()
    history[today] = {r["symb"]: r for r in results}
    history = trim_history(history)
    save_history(history)
    print(f"\nJSON 이력 저장 완료: {HISTORY_PATH} (기준일 {today}, 최근 {HISTORY_MAX_DAYS}거래일 유지)")

    new_signals = alerts.find_new_strong_signals(history, today)
    notified = alerts.load_notified()
    to_send = alerts.filter_unnotified(new_signals, today, notified)

    if not to_send:
        print("신규 65점 진입 종목 없음 (알림 발송 안 함)")
        return

    message = alerts.format_alert_message(to_send, today)
    send_telegram_message(message)
    alerts.mark_notified(notified, today, [r["symb"] for r in to_send])
    alerts.save_notified(notified)
    print(f"\n텔레그램 알림 발송 완료: {[r['symb'] for r in to_send]}")


if __name__ == "__main__":
    main()

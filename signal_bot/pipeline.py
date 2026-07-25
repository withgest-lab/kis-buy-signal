"""STEP 7: 32개 종목 전체 파이프라인 - 점수/판정/세부신호 표 출력 + JSON 이력 저장.

실행 전 signal_bot/fetch_universe.py로 최신 시세를 먼저 받아둬야 한다.
"""

import json
from pathlib import Path

import pandas as pd

from signal_bot import alerts
from signal_bot.config import HISTORY_MAX_DAYS, TICKER_NAMES, TICKERS
from signal_bot.notifier import send_telegram_message
from signal_bot.scoring import compute_scores

DATA_DIR = Path("signal_bot/data")
HISTORY_PATH = DATA_DIR / "history.json"


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


def run() -> list[dict]:
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
        except Exception as e:
            errors.append((symb, str(e)))
            continue

        last = df.iloc[-1]
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
        pct_chg = (float(last["close"]) - prev_close) / prev_close * 100 if prev_close else 0.0

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
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results, errors


def print_report(results: list[dict], errors: list[tuple]) -> None:
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
    print(f"\n{len(results)}/{len(TICKERS)} 종목 점수 산출 완료 "
          f"(강한매수후보 {len(strong)}개, 관찰대상 {len(watch)}개)")


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
        print("신규 70점 진입 종목 없음 (알림 발송 안 함)")
        return

    message = alerts.format_alert_message(to_send, today)
    send_telegram_message(message)
    alerts.mark_notified(notified, today, [r["symb"] for r in to_send])
    alerts.save_notified(notified)
    print(f"\n텔레그램 알림 발송 완료: {[r['symb'] for r in to_send]}")


if __name__ == "__main__":
    main()

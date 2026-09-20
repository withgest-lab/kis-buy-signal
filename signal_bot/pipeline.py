"""MDD 단계 + 일/주/월 RSI/MFI/다이버전스 계산 → 이력 저장 → 텔레그램 알림.

실행 전 signal_bot/fetch_universe.py(운영용 일봉)와 signal_bot/baseline_fetch.py
(20년치 베이스라인, 월 1회 정도만 실제 수집)를 먼저 실행해둬야 한다.
"""

import json
from pathlib import Path

import pandas as pd

from signal_bot import alerts
from signal_bot import company_info
from signal_bot import mdd
from signal_bot import timeframe_signals as tf
from signal_bot.config import HISTORY_MAX_DAYS, TICKER_NAMES, TICKERS, is_kr

DATA_DIR = Path("signal_bot/data")
BASELINE_DIR = DATA_DIR / "baseline"
HISTORY_PATH = DATA_DIR / "history.json"

# 시장국면 참고정보용 지수 - 미국은 SPY, 한국은 KOSPI200. 신호를 차단하지
# 않고 알림/대시보드에 참고정보로만 쓴다.
US_REGIME_TICKER = "SPY"
KR_REGIME_TICKER = "KOSPI200"


def load_history() -> dict:
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history: dict) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def trim_history(history: dict, max_days: int = HISTORY_MAX_DAYS) -> dict:
    """최근 max_days 거래일만 남기고 그 이전 날짜는 버린다(저장소 용량 무한증가 방지)."""
    dates = sorted(history.keys())
    if len(dates) <= max_days:
        return history
    keep = set(dates[-max_days:])
    return {d: rec for d, rec in history.items() if d in keep}


def _read_daily(symb: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{symb}_daily.csv", parse_dates=["date"])


def _read_baseline_daily(symb: str) -> pd.DataFrame | None:
    path = BASELINE_DIR / f"{symb}_daily.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"])


def _regime_for(category: str, regime_cache: dict) -> str:
    ticker = KR_REGIME_TICKER if is_kr(category) else US_REGIME_TICKER
    if ticker in regime_cache:
        return regime_cache[ticker]
    try:
        close = _read_daily(ticker)["close"]
        regime_cache[ticker] = mdd.market_regime(close)
    except Exception:
        regime_cache[ticker] = "판정불가"
    return regime_cache[ticker]


def run() -> tuple[list[dict], list[tuple]]:
    baseline = mdd.load_baseline()
    regime_cache: dict = {}
    results, errors = [], []

    for category, symb in TICKERS:
        daily_path = DATA_DIR / f"{symb}_daily.csv"
        if not daily_path.exists():
            errors.append((symb, "데이터 없음 (fetch_universe.py 먼저 실행 필요)"))
            continue

        try:
            daily = _read_daily(symb)
            baseline_daily = _read_baseline_daily(symb)
            baseline_entry = baseline.get(symb)

            last = daily.iloc[-1]
            prev_close = float(daily.iloc[-2]["close"]) if len(daily) >= 2 else float(last["close"])
            pct_chg = (float(last["close"]) - prev_close) / prev_close * 100 if prev_close else 0.0

            record = {
                "category": category,
                "symb": symb,
                "name": TICKER_NAMES.get(symb, symb),
                "currency": "KRW" if is_kr(category) else "USD",
                "date": last["date"].strftime("%Y-%m-%d"),
                "close": round(float(last["close"]), 2),
                "pct_chg": round(pct_chg, 2),
                "market_regime": _regime_for(category, regime_cache),
            }

            if baseline_entry is None or baseline_entry.get("insufficient_data"):
                record.update({"depth": 0.0, "rolling_high": float(last["close"]),
                               "stage": 0, "percentiles": None, "episode_count": 0,
                               "is_record_drawdown": False})
            else:
                state = mdd.update_today_state(baseline_entry, daily)
                percentiles = baseline_entry.get("percentiles")
                episodes = baseline_entry.get("episodes", [])
                record.update({
                    "depth": round(state["depth"], 4),
                    "rolling_high": round(state["rolling_high"], 2),
                    "stage": mdd.classify_stage(state["depth"], percentiles),
                    "percentiles": percentiles,
                    "episode_count": len(episodes),
                    "is_record_drawdown": mdd.is_record_drawdown(state["depth"], episodes),
                })

            record["timeframes"] = tf.compute_multi_timeframe_signals(daily, baseline_daily)

            results.append(record)
        except Exception as e:
            errors.append((symb, str(e)))

    results.sort(key=lambda r: r["stage"], reverse=True)
    return results, errors


def print_report(results: list[dict], errors: list[tuple]) -> None:
    print(f"{'종목':8s} {'분류':14s} {'통화':>4s} {'현재가':>12s}  {'단계':>4s}  {'낙폭':>7s}  일RSI  주RSI  월RSI")
    print("-" * 90)
    for r in results:
        d = r["timeframes"]["daily"]
        w = r["timeframes"]["weekly"]
        m = r["timeframes"]["monthly"]
        cur = r["currency"]  # Windows 콘솔(cp949)이 ₩/$ 같은 기호를 못 찍는 경우가 있어 코드로 표시
        print(
            f"{r['symb']:8s} {r['category']:14s} {cur:>4s} {r['close']:12,.2f}  "
            f"{r['stage']:>4d}  {r['depth'] * 100:6.1f}%  "
            f"{d['rsi'] if d['rsi'] is not None else float('nan'):5.1f}  "
            f"{w['rsi'] if w['rsi'] is not None else float('nan'):5.1f}  "
            f"{m['rsi'] if m['rsi'] is not None else float('nan'):5.1f}"
        )

    if errors:
        print("\n실패:")
        for symb, msg in errors:
            print(f"  {symb}: {msg}")

    insufficient = sum(1 for r in results if r.get("percentiles") is None)
    by_stage = {s: sum(1 for r in results if r["stage"] == s) for s in (1, 2, 3)}
    print(
        f"\n{len(results)}/{len(TICKERS)} 종목 처리 완료 "
        f"(MDD 1단계 {by_stage[1]}개, 2단계 {by_stage[2]}개, 3단계 {by_stage[3]}개, "
        f"베이스라인 데이터 부족 {insufficient}개)"
    )


def main():
    from signal_bot.notifier import send_telegram_message

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

    # 지수성 ETF(SPY/QQQ/DIA/SOXX) 절대 낙폭 구간 경보 - 기존 MDD단계/RSI·MFI
    # 알림과는 완전히 별개 트리거라 독립적으로 판정하고 별도 메시지로 발송한다
    # (아래 candidates가 없어도 이건 그대로 확인해야 하므로 먼저 처리).
    baseline = mdd.load_baseline()
    mdd_alert_state = alerts.load_mdd_alert_state()
    mdd_level_events = alerts.find_mdd_level_events(results, baseline, mdd_alert_state)
    if mdd_level_events:
        level_message = alerts.format_mdd_level_message(mdd_level_events, today)
        try:
            send_telegram_message(level_message)
            alerts.save_mdd_alert_state(mdd_alert_state)
            print(f"\n지수 낙폭 경보 발송 완료: {[e['symb'] for e in mdd_level_events]}")
        except Exception as e:
            print(f"\n지수 낙폭 경보 발송 실패 - 상태 저장 안 함(다음 실행에서 재시도): {e}")
    else:
        alerts.save_mdd_alert_state(mdd_alert_state)

    mdd_state = alerts.load_mdd_state()
    indicator_state = alerts.load_indicator_state()
    # find_alert_candidates가 mdd_state/indicator_state를 in-place로 갱신하지만,
    # 발송이 실패하면 다음 실행에서 같은 이벤트를 재시도할 수 있도록 실제
    # 발송(텔레그램 API 호출)이 성공한 뒤에만 디스크에 저장한다(아래).
    candidates = alerts.find_alert_candidates(results, mdd_state, indicator_state)

    notified = alerts.load_notified()
    to_send = alerts.filter_unnotified(candidates, today, notified)

    if not to_send:
        alerts.save_mdd_state(mdd_state)
        alerts.save_indicator_state(indicator_state)
        print("신규 알림 대상 없음 (발송 안 함)")
        return

    for r in to_send:
        r["business_summary"] = company_info.get_business_summary(r["symb"], r["name"])

    messages = alerts.format_alert_messages(to_send, today)
    try:
        for msg in messages:
            send_telegram_message(msg)
    except Exception as e:
        print(f"\n텔레그램 발송 실패 - 상태 저장 안 함(다음 실행에서 재시도): {e}")
        return

    alerts.save_mdd_state(mdd_state)
    alerts.save_indicator_state(indicator_state)
    alerts.mark_notified(notified, today, [r["symb"] for r in to_send])
    alerts.save_notified(notified)
    print(f"\n텔레그램 알림 발송 완료({len(messages)}건): {[r['symb'] for r in to_send]}")


if __name__ == "__main__":
    main()

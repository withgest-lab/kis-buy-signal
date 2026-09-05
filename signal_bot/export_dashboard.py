"""대시보드용 scores.json + detail/*.json 생성 (MDD + RSI/MFI/다이버전스).

history.json/mdd_baseline.json에는 계좌/키 정보가 없지만, scores.json에는
화면 표시에 필요한 필드만(종목코드/MDD상태/RSI·MFI·다이버전스/현재가/
타임스탬프) 담는다. API 키/계좌정보는 절대 포함하지 않는다.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from signal_bot import alerts
from signal_bot import company_info
from signal_bot import mdd
from signal_bot import timeframe_signals as tf
from signal_bot.config import TICKERS, is_kr
from signal_bot.pipeline import BASELINE_DIR, DATA_DIR, load_history

OUTPUT_PATH = Path("docs/scores.json")
DETAIL_DIR = Path("docs/detail")
SPARK_DAYS = 250          # 카드 미니 underwater 스파크라인 (약 1년)
DETAIL_DAYS = 500         # 상세뷰 underwater/가격차트 (약 2년)
KST = timezone(timedelta(hours=9))


def _read_daily(symb: str) -> pd.DataFrame | None:
    path = DATA_DIR / f"{symb}_daily.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"])


def _read_baseline_daily(symb: str) -> pd.DataFrame | None:
    path = BASELINE_DIR / f"{symb}_daily.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"])


def _underwater_series(baseline_daily: pd.DataFrame | None, recent_daily: pd.DataFrame) -> pd.DataFrame:
    """depth%(t) 전체 시계열 - baseline+recent를 합쳐 롤링신고가를 정확히
    계산한 뒤(중간에 baseline이 없어도 recent만으로 동작), 호출부에서 tail로 자른다."""
    combined = tf.combined_daily(baseline_daily, recent_daily)
    dd = mdd.compute_drawdown(combined["close"])
    return pd.DataFrame({
        "date": combined["date"], "close": combined["close"],
        "rolling_high": dd["rolling_max"], "depth": dd["drawdown"],
    })


def _series_records(df: pd.DataFrame, cols: list[str]) -> list[dict]:
    records = []
    for _, r in df.iterrows():
        rec: dict = {"date": r["date"].strftime("%Y-%m-%d")}
        for c in cols:
            v = r.get(c)
            if c == "divergence":
                rec[c] = bool(v)
            elif v is None or (isinstance(v, float) and pd.isna(v)):
                rec[c] = None
            else:
                rec[c] = round(float(v), 4)
        records.append(rec)
    return records


def _build_detail(symb: str, baseline_entry: dict | None) -> dict | None:
    daily = _read_daily(symb)
    if daily is None:
        return None
    baseline_daily = _read_baseline_daily(symb)

    underwater = _underwater_series(baseline_daily, daily).tail(DETAIL_DAYS)
    frames = tf.compute_timeframe_frames(daily, baseline_daily)

    return {
        "underwater": _series_records(underwater, ["close", "rolling_high", "depth"]),
        "daily": _series_records(frames["daily"].tail(DETAIL_DAYS), ["close", "rsi", "mfi", "divergence"]),
        "weekly": _series_records(frames["weekly"].tail(260), ["close", "rsi", "mfi", "divergence"]),
        "monthly": _series_records(frames["monthly"].tail(180), ["close", "rsi", "mfi", "divergence"]),
        "episodes": (baseline_entry or {}).get("episodes", []),
        "percentiles": (baseline_entry or {}).get("percentiles"),
    }


def export_details(baseline: dict) -> int:
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for _category, symb in TICKERS:
        detail = _build_detail(symb, baseline.get(symb))
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

    baseline = mdd.load_baseline()
    # 오늘 신규 알림이 나갔는지는 notified.json으로 판단한다(pipeline.main()이
    # 알림 발송 시 이미 기록해둠) - find_stage_upgrades/find_indicator_events는
    # 상태를 변경(mutate)하는 함수라 여기서 다시 호출하면 실제 알림 상태가
    # 오염되므로 호출하지 않는다.
    notified = alerts.load_notified()
    new_symbs = set(notified.get(today, []))

    tickers = []
    for symb, rec in history[today].items():
        entry = dict(rec)
        entry["is_new"] = symb in new_symbs
        underwater = _underwater_series(_read_baseline_daily(symb), _read_daily(symb)).tail(SPARK_DAYS)
        entry["underwater_spark"] = _series_records(underwater, ["depth"])
        if entry["is_new"]:
            entry["business_summary"] = company_info.get_business_summary(symb, entry["name"])
        tickers.append(entry)

    # stage 내림차순, 같은 stage면 depth가 더 깊은(음수가 더 큰) 종목 우선.
    tickers.sort(key=lambda r: (-r["stage"], r["depth"]))

    us_regime = next((t["market_regime"] for t in tickers if not is_kr(t["category"])), "판정불가")
    kr_regime = next((t["market_regime"] for t in tickers if is_kr(t["category"])), "판정불가")

    payload = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "as_of_date": today,
        "market_regime": {"us": us_regime, "kr": kr_regime},
        "tickers": tickers,
    }

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"대시보드 데이터 저장 완료: {OUTPUT_PATH} ({len(tickers)}종목, 신규 알림 {len(new_symbs)}개)")

    detail_count = export_details(baseline)
    print(f"상세 차트 데이터 저장 완료: {DETAIL_DIR}/ ({detail_count}개 종목)")


if __name__ == "__main__":
    main()

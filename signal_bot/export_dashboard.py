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
from signal_bot import buy_view
from signal_bot import company_info
from signal_bot import mdd
from signal_bot import sell as sellmod
from signal_bot import timeframe_signals as tf
from signal_bot import proxies
from signal_bot.config import (JP_BENCH_TICKER, KR_BENCH_TICKER, MDD_ALERT_LEVELS, MDD_ALERT_TICKERS, TICKERS,
                               is_crypto, is_jp, is_kr)
from signal_bot.pipeline import BASELINE_DIR, DATA_DIR, load_history

OUTPUT_PATH = Path("docs/scores.json")
DETAIL_DIR = Path("docs/detail")
SPARK_DAYS = 250            # 카드 미니 underwater 스파크라인 (약 1년, 가벼운 미리보기용)

# 개별 종목의 -25% 이상 낙폭 국면 중 기존 거시이벤트(MACRO_EVENTS)로 설명되지 않는
# 것들을 실제로 조사해(WebSearch) 채워둔 원인 메모 - 프론트에서 거시이벤트와 같은
# 방식(점선+라벨)으로 병합 표시한다. 1회성으로 수동 조사한 결과이며, 못 찾은 건은
# "특정 단일 원인 확인 안 됨"으로 정직하게 표기해뒀다(지어내지 않음).
EPISODE_NOTES_PATH = Path(__file__).parent / "data" / "episode_notes.json"


def _load_episode_notes() -> dict:
    if not EPISODE_NOTES_PATH.exists():
        return {}
    with open(EPISODE_NOTES_PATH, encoding="utf-8") as f:
        return json.load(f)

# 상세뷰(카드 펼침) 차트는 더 이상 여기서 기간을 잘라내지 않는다 - baseline 전체
# (가능한 만큼 최대) 기간을 그대로 detail json에 담아서, 프론트의 기간 선택 버튼
# (1Y~ALL)이 그 안에서 원하는 구간만 잘라 보여주도록 한다.
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
            if c in ("divergence", "divergence_bear"):
                rec[c] = bool(v)
            elif v is None or (isinstance(v, float) and pd.isna(v)):
                rec[c] = None
            else:
                rec[c] = round(float(v), 4)
        records.append(rec)
    return records


def _bench_daily(symb: str, category: str) -> pd.DataFrame | None:
    """상대강도 벤치마크: 미국 종목·비트코인=SPY, 한국 종목=KODEX 200(코스피200), 일본=EWJ(본인 제외)."""
    bench = KR_BENCH_TICKER if is_kr(category) else JP_BENCH_TICKER if is_jp(category) else "SPY"
    if bench == symb:
        return None
    recent = _read_daily(bench)
    if recent is None:
        return None
    return tf.combined_daily(_read_baseline_daily(bench), recent)


def _compute_sell(symb: str, category: str, regime: str, daily: pd.DataFrame,
                  baseline_daily: pd.DataFrame | None) -> dict | None:
    combined = tf.combined_daily(baseline_daily, daily)
    return sellmod.compute_sell(combined, category, symb, _bench_daily(symb, category), regime)


def _tf_summary(frames: dict) -> dict:
    """카드용 매도 관점 일/주/월 RSI·MFI·하락 다이버전스(마지막 봉 기준)."""
    out = {}
    for key in ("daily", "weekly", "monthly"):
        df = frames[key]
        if df.empty:
            out[key] = None
            continue
        last = df.iloc[-1]
        rsi = None if pd.isna(last["rsi"]) else round(float(last["rsi"]), 1)
        mfi = None if pd.isna(last["mfi"]) else round(float(last["mfi"]), 1)
        out[key] = {"rsi": rsi, "mfi": mfi, "div_bear": bool(last["divergence_bear"])}
    return out


def _build_detail(symb: str, baseline_entry: dict | None, episode_notes: dict,
                  sell: dict | None = None, frames: dict | None = None, buy_perf: dict | None = None) -> dict | None:
    daily = _read_daily(symb)
    if daily is None:
        return None
    baseline_daily = _read_baseline_daily(symb)

    underwater = _underwater_series(baseline_daily, daily)
    if frames is None:
        frames = tf.compute_timeframe_frames(daily, baseline_daily)

    return {
        "underwater": _series_records(underwater, ["close", "rolling_high", "depth"]),
        "daily": _series_records(frames["daily"], ["close", "rsi", "mfi", "divergence", "divergence_bear"]),
        "weekly": _series_records(frames["weekly"], ["close", "rsi", "mfi", "divergence", "divergence_bear"]),
        "monthly": _series_records(frames["monthly"], ["close", "rsi", "mfi", "divergence", "divergence_bear"]),
        "episodes": (baseline_entry or {}).get("episodes", []),
        "percentiles": (baseline_entry or {}).get("percentiles"),
        "episode_notes": episode_notes.get(symb, []),
        "sell": sell,
        "buy_perf": buy_perf,
    }


def export_details(baseline: dict, sells: dict | None = None, frames_by: dict | None = None,
                   buy_perfs: dict | None = None) -> int:
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    episode_notes = _load_episode_notes()
    sells = sells or {}
    count = 0
    for _category, symb in TICKERS:
        detail = _build_detail(symb, baseline.get(symb), episode_notes, sells.get(symb),
                               (frames_by or {}).get(symb), (buy_perfs or {}).get(symb))
        if detail is None:
            continue
        with open(DETAIL_DIR / f"{symb}.json", "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False)
        count += 1
    return count


def _date_strs(uw: pd.DataFrame) -> list[str]:
    return pd.to_datetime(uw["date"]).dt.strftime("%Y-%m-%d").tolist()


def _attach_buy(tickers: list[dict], series_by: dict, baseline: dict) -> dict:
    """종목마다 entry["buy"](판단·기간별 흐름·드문 깊이·과거 결과·3분할 의견)를 붙이고, detail용 buy_perf를 돌려준다.
    BASELINE_PROXY 종목(IBIT)은 드문 깊이·과거 결과를 원본 자산(BTC)의 긴 이력으로 계산하고 묶음 집계에서는 뺀다."""
    days: dict = {}
    for t in tickers:
        src = mdd.BASELINE_PROXY.get(t["symb"], t["symb"])
        uw = series_by.get(src)
        if uw is None or src in days:
            continue
        days[src] = buy_view.walk_days(uw["close"].to_numpy(), uw["depth"].to_numpy(), _date_strs(uw))
    walks = {s: buy_view.walk_forward(None, None, days=d) for s, d in days.items()}
    by_group: dict = {}
    days_by_group: dict = {}
    for t in tickers:
        if t["symb"] in mdd.BASELINE_PROXY or t["symb"] not in walks:
            continue
        g = buy_view.group_of(t["category"])
        by_group.setdefault(g, []).append(walks[t["symb"]])
        days_by_group.setdefault(g, []).append(days[t["symb"]])
    groups = {g: buy_view.pool(accs) for g, accs in by_group.items()}
    # 3분할 간격·백테스트·기다린 비용: 묶음별(1차 신호가 MIN_ANCHORS개 미만인 묶음은 전체 묶음 값)
    plans = {g: buy_view.plan_stats(ds) for g, ds in days_by_group.items()}
    plan_all = buy_view.plan_stats([d for ds in days_by_group.values() for d in ds])

    perfs: dict = {"_groups": groups, "_plans": {**plans, "all": plan_all}}
    for t in tickers:
        symb = t["symb"]
        uw = series_by.get(symb)
        if uw is None:
            continue
        src = mdd.BASELINE_PROXY.get(symb, symb)
        src_uw = series_by.get(src, uw)
        close = uw["close"].to_numpy()
        share, years = buy_view.days_deeper(uw["depth"].to_numpy())
        if src != symb:
            # 원본 자산의 과거 날짜 분포에서 '오늘 이 종목의 낙폭'이 어디쯤인지
            d_src = src_uw["depth"].to_numpy()
            start = buy_view.current_episode_start(d_src)
            past = d_src if start is None else d_src[:start]
            share = (round(float((past <= float(uw["depth"].iloc[-1])).mean()), 4)
                     if t["depth"] < 0 and len(past) >= buy_view.MIN_HIST_DAYS else None)
            years = round(len(past) / buy_view.BARS_1Y, 1)
        mv = buy_view.moves(close)
        net_1y = (mv.get("252") or {}).get("net")
        tier = buy_view.verdict(t["stage"], t.get("percentiles") is not None, t["is_record_drawdown"], share, net_1y)
        group = buy_view.group_of(t["category"])
        own = buy_view.summarize_all(walks[src]) if src in walks else {"tiers": {}, "base": None}
        grp = groups.get(group, {"tiers": {}, "base": None})
        stats = buy_view.pick_stats(tier, own, grp, group)
        gplan = plans.get(group)
        if not gplan or gplan["n"] < buy_view.MIN_ANCHORS:
            gplan = {**plan_all, "src": "all"} if plan_all else None
        own_dates = _date_strs(uw)
        anchor = buy_view.current_anchor(days.get(src), own_dates, uw["depth"].to_numpy(), tier)
        t["buy"] = {
            "tier": tier, "days_deeper": share, "years": years, "moves": mv,
            "retrace_1y": buy_view.retrace(close),
            "stats": stats,
            "plan": buy_view.plan(tier, close, own_dates, float(t["rolling_high"]), t.get("percentiles"), anchor,
                                  stats, gplan, grp, days.get(src), group),
        }
        if src != symb:
            t["buy"]["pct_from"] = src
        perfs[symb] = {"self": own, "group": {"name": group, **grp}, "src_symb": src if src != symb else None}
    return perfs


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

    # TICKERS는 이미 화면 분류 순서(미국지수 → 한국지수 → 미국ETF → 한국ETF → 미국주식(시가총액순) → 한국주식
    # → 일본주식 → 비트코인)로 큐레이션돼 있으므로, 이 순서를 그대로 대시보드의 "분류순" 정렬 기준으로 쓴다.
    universe_rank = {symb: i for i, (_category, symb) in enumerate(TICKERS)}

    tickers = []
    sells: dict = {}
    frames_by: dict = {}
    series_by: dict = {}     # 매수 판단용 전체 종가·낙폭(워크포워드 결과 묶음 집계)
    for symb, rec in history[today].items():
        entry = dict(rec)
        entry["is_new"] = symb in new_symbs
        entry["universe_rank"] = universe_rank.get(symb, len(TICKERS))
        full_uw = _underwater_series(_read_baseline_daily(symb), _read_daily(symb))
        underwater = full_uw.tail(SPARK_DAYS)
        entry["underwater_spark"] = _series_records(underwater, ["depth"])
        # 카드 낙폭도 상세 차트·매도 모드와 같은 시계열(매일 새로 받는 종가 기준)의 마지막 값으로 맞춘다.
        # history.json/mdd_baseline.json의 rolling_high는 월 1회 스냅샷이라, 배당락 등으로 과거 종가(수정주가)가
        # 조금 바뀐 ETF(예: SPY)는 같은 종가인데 카드와 상세의 낙폭이 0.2%p쯤 어긋났다.
        last_uw = full_uw.iloc[-1]
        entry["depth"] = round(float(last_uw["depth"]), 4)
        entry["rolling_high"] = round(float(last_uw["rolling_high"]), 4)
        entry["stage"] = mdd.classify_stage(entry["depth"], entry.get("percentiles"))
        b_entry = baseline.get(symb) or {}
        entry["is_record_drawdown"] = mdd.is_record_drawdown(entry["depth"], b_entry.get("episodes", []), b_entry.get("record_depth"))
        series_by[symb] = full_uw
        daily = _read_daily(symb)
        if daily is not None:
            sell = _compute_sell(symb, entry["category"], entry["market_regime"], daily,
                                 _read_baseline_daily(symb))
            if sell is not None:
                sells[symb] = sell
                frames = tf.compute_timeframe_frames(daily, _read_baseline_daily(symb))
                frames_by[symb] = frames
                entry["sell"] = sellmod.summary(sell)
                entry["sell"]["tf"] = _tf_summary(frames)
        if entry["is_new"]:
            entry["business_summary"] = company_info.get_business_summary(symb, entry["name"])
        if symb in MDD_ALERT_TICKERS:
            # 텔레그램 발송 이력(mdd_alert_state.json)과 무관하게, "지금 depth 기준
            # 현재 상태"를 대시보드에는 항상 정확하게 보여준다(알림은 이미 보낸
            # 구간이라도 화면에는 계속 표시돼야 하므로).
            depth = entry["depth"]
            level = next(((t, label) for t, label in MDD_ALERT_LEVELS if depth <= -t), None)
            entry["mdd_alert"] = (
                {"threshold": level[0], "label": level[1]} if level else None
            )
        tickers.append(entry)

    buy_perfs = _attach_buy(tickers, series_by, baseline)

    # stage 내림차순, 같은 stage면 depth가 더 깊은(음수가 더 큰) 종목 우선.
    tickers.sort(key=lambda r: (-r["stage"], r["depth"]))

    us_regime = next((t["market_regime"] for t in tickers if t["symb"] == "SPY"), "판정불가")
    kr_regime = next((t["market_regime"] for t in tickers if t["symb"] == KR_BENCH_TICKER), "판정불가")

    payload = {
        "generated_at": datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "as_of_date": today,
        "market_regime": {"us": us_regime, "kr": kr_regime},
        # 보유 종목 → 전략 종목 매칭 규칙: 포트폴리오 화면과 이 대시보드가 같은 목록을 읽는다(signal_bot/proxies.py)
        "proxies": {"prefix": proxies.ISSUER_PREFIX_RE, "rules": proxies.RULES},
        "buy_groups": buy_perfs.pop("_groups", {}),
        "buy_plans": buy_perfs.pop("_plans", {}),
        "tickers": tickers,
    }

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"대시보드 데이터 저장 완료: {OUTPUT_PATH} ({len(tickers)}종목, 신규 알림 {len(new_symbs)}개)")

    detail_count = export_details(baseline, sells, frames_by, buy_perfs)
    print(f"상세 차트 데이터 저장 완료: {DETAIL_DIR}/ ({detail_count}개 종목)")


if __name__ == "__main__":
    main()

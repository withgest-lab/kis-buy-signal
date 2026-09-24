"""매도 전략 모드 계산 - 신고가 돌파 → 천정 → 천정 대비 낙폭 3단계(주의/경고/매도검토).

이 시스템의 기본 철학은 우량 종목 장기보유이므로 신호는 "매도 지시"가 아니라
"경고/부분 축소 검토"용이다. 계산은 전부 여기서 하고 프론트는 그리기만 한다.

- 천정 = 종가 기준 러닝하이(직전 N봉 최고). 그 봉이 신고가 돌파였고, 이후 낙폭이
  '주의' 임계에 닿으면 확정(이벤트 1건). 천정을 다시 넘으면 이벤트는 회복 처리된다.
- 임계 = 종목별 완결 낙폭 에피소드 |depth| 분포의 P25/P50/P75(하한 -5%),
  에피소드가 부족하면 고정 폴백값. 모든 종목 동일한 방식(종목 성격은 문구에만 반영).
- 보강 신호 6종은 등급을 바꾸지 않고 패널/카운터로만 표시한다.
"""

from typing import Optional

import numpy as np
import pandas as pd

from signal_bot import mdd

LOOKBACKS = (60, 120, 250, 0)      # 0 = 사상최고(전체 기간)
DEFAULT_LOOKBACK = 250
MIN_ATTN = 0.05                    # '주의' 하한
FALLBACK_THRESHOLDS = (0.08, 0.15, 0.25)
MIN_STEP = 0.02                    # 단계 간 최소 간격(임계가 겹치지 않게)
MIN_PERF_EVENTS = 5                # 과거 신호 성과 표를 보여줄 최소 이벤트 수
FWD_6M, FWD_12M = 126, 252
SPARK_BARS = 250                   # 카드 미니 낙폭 스파크라인(약 1년)
MIN_REC_EVENTS = 3                 # 회복기간 통계를 보여줄 최소 회복 사례 수

CORE_TICKERS = {"SPY", "QQQ", "DIA", "IWM", "KOSPI200", "069500"}   # 계속 모아가는 주요 지수(069500=KODEX 200)
SIGNAL_KEYS = ("retrace", "wedge", "bigBear", "ma200", "rs", "regime")
SIGNAL_NAMES = {"retrace": "되돌림률", "wedge": "쐐기형", "bigBear": "장대음봉", "ma200": "200일선 이탈",
                "rs": "상대강도 약화", "regime": "하락장"}


def symbol_tag(symb: str, category: str) -> str:
    """core=주요 지수(참고용 문구), theme=섹터/테마 ETF(주 대상), stock=개별주."""
    if symb in CORE_TICKERS:
        return "core"
    if category in ("섹터ETF", "한국ETF"):
        return "theme"
    return "stock"


def compute_thresholds(close: pd.Series, dates: pd.Series) -> dict:
    """완결 낙폭 에피소드 |depth| 분포로 주의/경고/매도검토 임계(음수)를 계산.
    (mdd.percentile_stats의 p25/p50은 '깊이' 기준이라 순서가 반대라 직접 계산한다.)"""
    dd = mdd.compute_drawdown(close.reset_index(drop=True))
    episodes = mdd.extract_episodes(dates.reset_index(drop=True), dd["drawdown"])
    depths = np.array([abs(e["depth"]) for e in episodes if e["is_complete"]])
    if len(depths) < mdd.MIN_EPISODES_REQUIRED:
        a, w, s = FALLBACK_THRESHOLDS
        return {"levels": [-a, -w, -s], "fallback": True, "episodes": int(len(depths))}
    a = max(float(np.percentile(depths, 25)), MIN_ATTN)
    w = max(float(np.percentile(depths, 50)), a + MIN_STEP)
    s = max(float(np.percentile(depths, 75)), w + MIN_STEP)
    return {"levels": [round(-a, 4), round(-w, 4), round(-s, 4)],
            "fallback": False, "episodes": int(len(depths))}


def _rolling_high(c: np.ndarray, n: int) -> np.ndarray:
    """i번째 봉을 포함한 직전 n봉 최고 종가(n=0이면 전체 누적)."""
    s = pd.Series(c)
    return (s.cummax() if n == 0 else s.rolling(n, min_periods=1).max()).to_numpy()


def _new_high_flags(c: np.ndarray, n: int) -> np.ndarray:
    """i번째 종가가 직전 n봉(자기 제외) 최고 종가를 넘으면 True(신고가 돌파)."""
    s = pd.Series(c)
    prev = s.shift(1)
    prior = prev.cummax() if n == 0 else prev.rolling(n, min_periods=n).max()
    return (s > prior).to_numpy()


def _stage(depth: float, levels: list) -> int:
    return sum(1 for lv in levels if depth <= lv)


def _find_events(c: np.ndarray, n: int, levels: list) -> list[dict]:
    """신고가 봉(천정 후보)마다, 낙폭이 '주의' 임계에 닿으면 이벤트를 만들고
    회복(천정 재돌파)/윈도우 이탈/데이터 끝까지 저점과 단계 진입을 추적한다."""
    newhigh = _new_high_flags(c, n)
    hi_idx = np.zeros(len(c), dtype=int)     # 각 봉 시점의 러닝하이 위치
    best = 0
    for i in range(len(c)):
        if n == 0:
            if c[i] >= c[best]:
                best = i
            hi_idx[i] = best
        else:
            lo = max(0, i - n + 1)
            hi_idx[i] = lo + int(np.argmax(c[lo:i + 1]))
    attn = levels[0]
    events: list[dict] = []
    open_ev: Optional[dict] = None
    for i in range(len(c)):
        h = hi_idx[i]
        if open_ev is not None:
            if c[i] >= c[open_ev["peak_idx"]] and i > open_ev["confirm_idx"]:
                open_ev["recovered"], open_ev["end_idx"] = True, i
                events.append(open_ev)
                open_ev = None
            elif n and i - open_ev["peak_idx"] >= n:      # 천정이 윈도우 밖으로 밀려남
                open_ev["recovered"], open_ev["end_idx"] = False, i
                events.append(open_ev)
                open_ev = None
            else:
                d = c[i] / c[open_ev["peak_idx"]] - 1
                if d < open_ev["trough_depth"]:
                    open_ev["trough_depth"], open_ev["trough_idx"] = d, i
                for k in (2, 3):
                    if k not in open_ev["stages"] and d <= levels[k - 1]:
                        open_ev["stages"][k] = i
        if open_ev is None:
            d = c[i] / c[h] - 1
            # 동률 종가로 "회복"한 직후 같은 천정이 다시 사례로 잡히지 않게 직전 사례와 같은 천정은 건너뛴다.
            if d <= attn and newhigh[h] and not (events and events[-1]["peak_idx"] == h):
                open_ev = {"peak_idx": int(h), "confirm_idx": i, "trough_depth": d,
                           "trough_idx": i, "stages": {1: i}, "recovered": None, "end_idx": None}
                for k in (2, 3):
                    if d <= levels[k - 1]:
                        open_ev["stages"][k] = i
    if open_ev is not None:
        events.append(open_ev)      # 진행중(recovered=None)
    # 돌파 시점 = 천정에서 거슬러 올라가며 '주의' 낙폭 없이 이어진 신고가 봉 중 가장 이른 것.
    # 직전 사례의 종료 위치 이후로만 거슬러 올라가서, 사례들의 상승 구간이 서로 겹치지 않게 한다.
    nh = np.flatnonzero(newhigh)
    floor = 0
    for ev in events:
        ev["breakout_idx"] = _breakout_idx(c, nh, ev["peak_idx"], attn, floor)
        if ev["end_idx"] is not None:
            floor = ev["end_idx"]
    return events


def _breakout_idx(c: np.ndarray, nh: np.ndarray, j: int, attn: float, floor: int = 0) -> int:
    """j(천정 또는 현재 고점)에서 거슬러 올라가며, 사이에 '주의' 낙폭이 없이 이어진 신고가 봉 중
    가장 이른 것(= 이번 상승의 시작이 된 신고가 돌파일). floor 이전으로는 가지 않는다."""
    b = j
    for p in nh[(nh < j) & (nh >= floor)][::-1]:
        if c[p:b + 1].min() / c[p] - 1 > attn:
            b = int(p)
        else:
            break
    return b


def _perf(c: np.ndarray, events: list[dict]) -> dict:
    """같은 단계에 처음 진입했던 과거 사례들의 이후 6/12개월 수익률·추가 하락폭 중앙값."""
    out = {}
    for k in (1, 2, 3):
        idxs = [ev["stages"][k] for ev in events if k in ev["stages"]]
        if len(idxs) < MIN_PERF_EVENTS:
            out[str(k)] = {"n": len(idxs), "insufficient": True}
            continue
        r6 = [c[i + FWD_6M] / c[i] - 1 for i in idxs if i + FWD_6M < len(c)]
        r12 = [c[i + FWD_12M] / c[i] - 1 for i in idxs if i + FWD_12M < len(c)]
        dd = [c[i:i + FWD_12M + 1].min() / c[i] - 1 for i in idxs if i + FWD_6M < len(c)]
        med = lambda v: round(float(np.median(v)), 4) if v else None
        out[str(k)] = {"n": len(idxs), "n6": len(r6), "n12": len(r12),
                       "r6": med(r6), "r12": med(r12), "dd": med(dd), "insufficient": False}
    return out


def _retrace(c: np.ndarray, n: int) -> Optional[dict]:
    """(천정-현재)/(직전 상승파동 시작~천정 폭). 0.5 이상이면 해당."""
    i = len(c) - 1
    lo = max(0, i - n + 1) if n else 0
    h = lo + int(np.argmax(c[lo:i + 1]))
    w = n if n else 250
    start = c[max(0, h - w):h + 1].min() if h > 0 else c[h]
    rise = c[h] - start
    if rise <= 0:
        return None
    ratio = float((c[h] - c[i]) / rise)
    return {"ratio": round(ratio, 3), "hit": ratio >= 0.5}


def _swings(c: np.ndarray, k: int = 10) -> list[tuple[int, str]]:
    """종가 기준 스윙 고저점(좌우 k봉 최고/최저) - 고점/저점이 번갈아 나오게 정리."""
    pts = []
    for i in range(k, len(c) - k):
        w = c[i - k:i + k + 1]
        if c[i] == w.max():
            pts.append((i, "H"))
        elif c[i] == w.min():
            pts.append((i, "L"))
    clean: list[tuple[int, str]] = []
    for p in pts:
        if clean and clean[-1][1] == p[1]:
            prev = clean[-1][0]
            keep = (c[p[0]] > c[prev]) if p[1] == "H" else (c[p[0]] < c[prev])
            if keep:
                clean[-1] = p
        else:
            clean.append(p)
    return clean


def _wedge(c: np.ndarray) -> Optional[dict]:
    """최근 상승파동(저점→고점) 3개 크기가 연속 감소하는데 고점은 계속 갱신되면 해당(쐐기형)."""
    sw = _swings(c[-600:])
    waves = []
    for a, b in zip(sw, sw[1:]):
        if a[1] == "L" and b[1] == "H":
            base = c[-600:][a[0]]
            waves.append((float(c[-600:][b[0]] / base - 1), float(c[-600:][b[0]])))
    if len(waves) < 3:
        return None
    last = waves[-3:]
    sizes = [w[0] for w in last]
    highs = [w[1] for w in last]
    hit = sizes[0] > sizes[1] > sizes[2] and highs[0] < highs[1] < highs[2]
    return {"waves": [round(s, 4) for s in sizes], "hit": bool(hit)}


def _big_bear(df: pd.DataFrame) -> dict:
    """거래량 급증(20봉 평균 1.5배+) + 몸통 하락폭이 평균 일변동의 3배+인 음봉.
    종가/중심선(시가·종가 중간)을 저항선으로 보고, 최근 60봉 안에 있고 현재가가
    그 중심선 아래면 해당."""
    o, cl, v = df["open"].to_numpy(float), df["close"].to_numpy(float), df["volume"].to_numpy(float)
    body = (cl - o) / np.where(o == 0, np.nan, o)
    avg_move = pd.Series(np.abs(body)).rolling(20).mean().shift(1).to_numpy()
    avg_vol = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    cand = []
    for i in range(max(20, len(cl) - 120), len(cl)):
        if (body[i] < 0 and not np.isnan(avg_move[i]) and -body[i] >= 3 * avg_move[i]
                and avg_vol[i] > 0 and v[i] >= 1.5 * avg_vol[i]):
            cand.append({"date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                         "close": round(float(cl[i]), 4), "mid": round(float((o[i] + cl[i]) / 2), 4),
                         "drop": round(float(body[i]), 4), "_i": i})
    recent = [x for x in cand if x["_i"] >= len(cl) - 60]
    hit = any(cl[-1] < x["mid"] for x in recent)
    for x in cand:
        del x["_i"]
    return {"candles": cand[-3:], "hit": bool(hit)}


def _rel_strength(df: pd.DataFrame, bench: Optional[pd.DataFrame]) -> Optional[dict]:
    """벤치마크 대비 상대강도가 최근 60봉 하락하고 120봉 평균 아래면 해당."""
    if bench is None:
        return None
    m = df[["date", "close"]].merge(bench[["date", "close"]], on="date", suffixes=("", "_b"))
    if len(m) < 130:
        return None
    ratio = (m["close"] / m["close_b"]).to_numpy(float)
    chg = ratio[-1] / ratio[-61] - 1
    below = ratio[-1] < ratio[-120:].mean()
    return {"chg60": round(float(chg), 4), "hit": bool(chg < 0 and below)}


def compute_sell(df: pd.DataFrame, category: str, symb: str,
                 bench: Optional[pd.DataFrame], regime: str) -> Optional[dict]:
    """df: date/open/high/low/close/volume 오름차순(baseline+recent 합친 일봉)."""
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 260:
        return None
    c = df["close"].to_numpy(float)
    th = compute_thresholds(df["close"], df["date"])
    levels = th["levels"]
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()

    ma200 = None
    if len(c) >= 200:
        m = float(c[-200:].mean())
        ma200 = {"dist": round(float(c[-1] / m - 1), 4), "hit": bool(c[-1] < m)}
    common = {
        "wedge": _wedge(c),
        "bigBear": _big_bear(df),
        "ma200": ma200,
        "rs": _rel_strength(df, bench),
        "regime": {"label": regime, "hit": regime == "하락장"} if regime != "판정불가" else None,
    }

    by = {}
    for n in LOOKBACKS:
        events = _find_events(c, n, levels)
        hi = _rolling_high(c, n)
        depth = float(c[-1] / hi[-1] - 1)
        lo = max(0, len(c) - n) if n else 0
        h = lo + int(np.argmax(c[lo:]))
        retrace = _retrace(c, n)
        sigs = dict(common, retrace=retrace)
        avail = [k for k in SIGNAL_KEYS if sigs.get(k) is not None]
        rec_bars = [e["end_idx"] - e["peak_idx"] for e in events if e["recovered"] is True]
        # 확정된 진행 사례가 없을 때(미확정 후보)의 현재 고점 돌파일 - 상승 구간을 그리기 위함. 현재 고점이 돌파 봉이 아니면 None.
        cur_break = None
        if not any(e["recovered"] is None for e in events):
            newhigh = _new_high_flags(c, n)
            if newhigh[h]:
                floor = max((e["end_idx"] for e in events if e["end_idx"] is not None), default=0)
                cur_break = _breakout_idx(c, np.flatnonzero(newhigh), h, levels[0], floor)
        by[str(n)] = {
            "spark": [round(float(x), 3) for x in (c / hi - 1)[-SPARK_BARS:]],
            "rec": ({"n": len(rec_bars), "min": int(min(rec_bars)), "med": int(np.median(rec_bars)),
                     "max": int(max(rec_bars))} if len(rec_bars) >= MIN_REC_EVENTS else None),
            "current": {"depth": round(depth, 4), "stage": _stage(depth, levels),
                        "high_date": dates[h], "high_price": round(float(c[h]), 4),
                        "breakout": dates[cur_break] if cur_break is not None else None,
                        "breakout_price": round(float(c[cur_break]), 4) if cur_break is not None else None},
            "events": [{
                "breakout": dates[e["breakout_idx"]], "breakout_price": round(float(c[e["breakout_idx"]]), 4),
                "peak": dates[e["peak_idx"]],
                "peak_price": round(float(c[e["peak_idx"]]), 4), "confirm": dates[e["confirm_idx"]],
                "trough": dates[e["trough_idx"]], "trough_depth": round(float(e["trough_depth"]), 4),
                "recovered": e["recovered"],
                "end": dates[e["end_idx"]] if e["end_idx"] is not None else None,
                "stages": {str(k): dates[i] for k, i in e["stages"].items()},
            } for e in events],
            "perf": _perf(c, events),
            "retrace": retrace,
            "hits": sum(1 for k in avail if sigs[k]["hit"]),
            "hit_names": [SIGNAL_NAMES[k] for k in avail if sigs[k]["hit"]],
            "avail": len(avail),
        }
    return {"tag": symbol_tag(symb, category), "thresholds": th, "byLookback": by, **common}


def summary(sell: dict) -> dict:
    """scores.json 카드용 요약(상세 JSON을 열기 전에도 배지/정렬/카운터를 그릴 수 있게)."""
    return {
        "tag": sell["tag"], "levels": sell["thresholds"]["levels"],
        "fallback": sell["thresholds"]["fallback"],
        "by": {n: {"depth": v["current"]["depth"], "stage": v["current"]["stage"],
                   "hits": v["hits"], "avail": v["avail"], "names": v["hit_names"], "spark": v["spark"], "rec": v["rec"]}
               for n, v in sell["byLookback"].items()},
    }

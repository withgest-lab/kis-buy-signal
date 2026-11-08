"""매수 판단("지금 살 때인가")과 3분할 매수 의견 - 계산은 전부 여기서 하고 화면(signals/index.html)은 그리기만 한다.

낙폭 단계(mdd.classify_stage: 과거 조정 대비 깊이)에 두 가지를 더해 판단을 정한다.
- 시간상 드문 깊이: 지금 하락이 시작되기 전 모든 날 중 오늘보다 깊었던 날의 비율(days_deeper).
- 급등 뒤 하락: 1년 전 대비 수익률(net_1y)이 +30%를 넘으면 고점이 부풀려진 상태라 같은 낙폭이라도 위험이 크다.

판단(verdict) 순서: unknown(과거 국면 5개 미만) → record(사상 최대 낙폭) → hot(2단계+ · 1년 +30% 초과)
→ strong(2단계+ · 드문 깊이 ≤10%) → split(2단계+) → watch(1단계) → wait.

같은 판단이 과거에 어땠는지는 워크포워드로 센다 - 과거 매일에 대해 그날까지의 국면·날짜만으로 판단을 다시 내리고
(미래 정보 미사용), 그 뒤 1년 수익률·6개월 안 추가 하락을 모은다. 사례(하락 국면 수)는 1년 뒤 결과가 있는 하락만
센다 - 진행 중이거나 1년이 안 지난 하락까지 세면 사례가 부풀어 '사례 적으면 묶음' 규칙을 피해 간다(SOXX 2026-11).

3분할 매수 의견(plan): 이번 하락에서 매수 판단(BUY_TIERS)이 처음 나온 날이 1차(하락이 1년 넘게 이어지면 1년마다 새 1차),
2·3차는 과거 1차 신호 뒤 1년 안 최저점의 중앙값·하위 25% 지점(묶음별, 1년이 끝난 신호만 = 오늘 알 수 있는 것만).
매수 판단 전이면 '더 기다리기'와 1차가 되는 가격 조건을 준다. 검증 결과는 validate_buy_rules.py 참고.
"""

import bisect
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from signal_bot import mdd

BARS_1Y = 252
BARS_6M = 126
MOVE_WINDOWS = (63, 126, 252, 756)      # 3개월·6개월·1년·3년(거래일)
HOT_NET_1Y = 0.30                       # 1년 전 대비 이보다 높으면 '급등 뒤 하락'
RARE_DAYS = 0.10                        # 과거 날짜 중 이보다 적게 더 깊었으면 '드문 깊이'
MIN_HIST_DAYS = 3 * BARS_1Y             # 드문 깊이 판단에 필요한 과거 날짜(지금 하락 전) - 3년
DROP_FURTHER = -0.15                    # 6개월 안 이만큼 더 빠지면 '추가 하락'
MIN_SELF_EPISODES = 5                   # 종목 자체 사례(하락 국면)가 이보다 적으면 묶음 통계로 대신(3~4번은 들쭉날쭉)
TIERS = ("strong", "split", "hot", "watch", "wait", "record")

# 3분할 매수 의견
BUY_TIERS = ("strong", "split", "record")   # 1차 신호가 되는 판단: 2단계 이상이고 급등 뒤가 아님, 또는 사상 최대 낙폭
REBOUND = 0.03                  # 1차 신호 뒤 1차가보다 이만큼 넘게 반등했고 지금 판단이 매수가 아니면 다시 '더 기다리기'
MIN_ANCHORS = 10                # 2·3차 간격에 필요한 과거 1차 신호 수 - 묶음이 이보다 적으면 전체 묶음 값을 쓴다
EDGE_MED = 0.03                 # 근거 비교어: 1년 뒤 중앙값 차이가 이 안이면 '비슷'
EDGE_LOSS = 0.03                # 근거 비교어: 손해 확률 차이가 이 안이면 '비슷'
CONF_TOL = 0.02                 # 2·3차 가격이 단계 선(P25·P10 깊이)과 이 비율 안이면 '겹침'
HOT_SCAN_DAYS = 126             # 가격이 그대로일 때 급등 조건이 풀리는 날을 찾는 최대 거래일

GROUP_OF_CATEGORY = {
    "미국지수": "index", "한국지수": "index", "섹터ETF": "usETF", "한국ETF": "krETF",
    "개별종목": "usStock", "한국개별종목": "krStock", "일본개별종목": "jpStock", "비트코인": "crypto",
}


def group_of(category: str) -> str:
    return GROUP_OF_CATEGORY.get(category, "other")


def _r(v: Optional[float], nd: int = 4) -> Optional[float]:
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def moves(close: np.ndarray) -> dict:
    """기간별 흐름: 기간 시작가 → 기간 고점(up) → 지금(down), 결과(net). 데이터가 기간보다 짧으면 None."""
    c = np.asarray(close, dtype=float)
    out: dict = {}
    for w in MOVE_WINDOWS:
        if len(c) <= w:
            out[str(w)] = None
            continue
        p0, seg = c[-w - 1], c[-w - 1:]
        hi = float(seg.max())
        out[str(w)] = {"up": _r(hi / p0 - 1), "down": _r(c[-1] / hi - 1), "net": _r(c[-1] / p0 - 1)}
    return out


def retrace(close: np.ndarray, w: int = BARS_1Y) -> Optional[float]:
    """w봉 동안 오른 폭(시작가→고점) 중 지금까지 반납한 비율. 1 이상이면 상승분 전부(이상) 반납. 오른 적 없으면 None."""
    c = np.asarray(close, dtype=float)
    if len(c) <= w:
        return None
    p0, hi = c[-w - 1], float(c[-w - 1:].max())
    if hi <= p0:
        return None
    return _r((hi - c[-1]) / (hi - p0))


def current_episode_start(depth: np.ndarray) -> Optional[int]:
    """진행 중 하락 국면의 시작 인덱스(마지막 신고가 다음 날). 오늘이 신고가면 None."""
    d = np.asarray(depth, dtype=float)
    if d[-1] >= -1e-9:
        return None
    at_high = np.where(d >= -1e-9)[0]
    return int(at_high[-1]) + 1 if len(at_high) else 0


def days_deeper(depth: np.ndarray) -> tuple[Optional[float], float]:
    """(지금 하락이 시작되기 전 날들 중 낙폭이 오늘보다 깊거나 같았던 비율, 그 기간 년수). 신고가이거나 과거가 3년 미만이면 비율 None."""
    d = np.asarray(depth, dtype=float)
    start = current_episode_start(d)
    past = d if start is None else d[:start]
    years = len(past) / BARS_1Y
    if start is None or len(past) < MIN_HIST_DAYS:
        return None, round(years, 1)
    return _r(float(np.mean(past <= d[-1]))), round(years, 1)


def verdict(stage: int, has_percentiles: bool, is_record: bool,
            deeper_share: Optional[float], net_1y: Optional[float]) -> str:
    if not has_percentiles:
        return "unknown"
    if is_record:
        return "record"
    if stage >= 2 and net_1y is not None and net_1y > HOT_NET_1Y:
        return "hot"
    if stage >= 2 and deeper_share is not None and deeper_share <= RARE_DAYS:
        return "strong"
    if stage >= 2:
        return "split"
    if stage == 1:
        return "watch"
    return "wait"


def fwd_min(close: np.ndarray, w: int) -> np.ndarray:
    """i일 종가 대비 i..i+w일 최저 종가의 변화율(0 이하) - 미래가 w일보다 모자란 날은 NaN."""
    c = np.asarray(close, dtype=float)
    m = pd.Series(c[::-1]).rolling(w + 1, min_periods=w + 1).min().to_numpy()[::-1]
    return m / c - 1


def forward_arrays(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(1년 뒤 수익률, 6개월 안 최저가 기준 추가 하락률) - 미래가 모자란 날은 NaN."""
    c = np.asarray(close, dtype=float)
    n = len(c)
    f12 = np.full(n, np.nan)
    if n > BARS_1Y:
        f12[:n - BARS_1Y] = c[BARS_1Y:] / c[:n - BARS_1Y] - 1
    return f12, fwd_min(c, BARS_6M)


def daily_tiers(close: np.ndarray, depth: np.ndarray) -> tuple[list[Optional[str]], list[int]]:
    """과거 매일의 판단 - i일의 판단은 0..i일 데이터(그때까지 끝난 국면·그 국면 전 날들)만으로 정한다(미래 미사용).
    판단 대상이 아닌 날(신고가, 첫 1년, 끝난 국면 5개 미만)은 None. 반환: (판단, 하락 국면 번호)."""
    c = np.asarray(close, dtype=float)
    d = np.asarray(depth, dtype=float)
    tiers: list[Optional[str]] = [None] * len(c)
    eps = [0] * len(c)
    comp: list[float] = []
    pct = None
    in_ep, trough, ep_id = False, 0.0, 0
    past_sorted = np.array([])
    for i in range(len(c)):
        x = d[i]
        if x >= -1e-9:
            if in_ep and trough <= mdd.MIN_EPISODE_DEPTH:
                comp.append(trough)
                if len(comp) >= mdd.MIN_EPISODES_REQUIRED:
                    p50, p25, p10 = np.percentile(comp, [50, 25, 10])
                    pct = {"p50": p50, "p25": p25, "p10": p10, "count": len(comp)}
            in_ep, trough = False, 0.0
            continue
        if not in_ep:
            in_ep, trough, ep_id = True, x, ep_id + 1
            past_sorted = np.sort(d[:i])
        trough = min(trough, x)
        eps[i] = ep_id
        if i < BARS_1Y or pct is None:
            continue
        stage = mdd.classify_stage(x, pct)
        share = (np.searchsorted(past_sorted, x, side="right") / len(past_sorted)
                 if len(past_sorted) >= MIN_HIST_DAYS else None)
        tiers[i] = verdict(stage, True, x < min(comp), share, c[i] / c[i - BARS_1Y] - 1)
    return tiers, eps


def walk_days(close: np.ndarray, depth: np.ndarray, dates: Optional[list] = None) -> dict:
    """과거 매일의 판단(워크포워드)과 그 뒤 결과 배열 - walk_forward(판단별 결과)와 plan_stats(3분할)가 함께 쓴다.
    dates는 'YYYY-MM-DD' 문자열 목록(묶음 백테스트에서 신호 순서를 날짜로 맞출 때 필요)."""
    c = np.asarray(close, dtype=float)
    tiers, eps = daily_tiers(c, depth)
    f12, fdd = forward_arrays(c)
    return {"close": c, "dates": list(dates) if dates is not None else None, "tiers": tiers,
            "eps": np.asarray(eps, dtype=int), "f12": f12, "fdd": fdd, "m12": fwd_min(c, BARS_1Y)}


def walk_forward(close: Optional[np.ndarray], depth: Optional[np.ndarray], days: Optional[dict] = None) -> dict:
    """과거 매일의 판단(daily_tiers)과 그 뒤 결과. 반환: {tier|"base": {"f12": [...], "drop": [...], "eps": set}}.
    사례(eps)는 1년 뒤 결과가 있는 날의 하락 국면만 담는다(진행 중·1년 안 된 하락은 결과가 없으니 사례가 아니다)."""
    w = days if days is not None else walk_days(close, depth)
    f12, fdd, eps = w["f12"], w["fdd"], w["eps"]
    acc = {k: {"f12": [], "drop": [], "eps": set()} for k in TIERS + ("base",)}
    for i, tier in enumerate(w["tiers"]):
        keys = (["base"] if i >= BARS_1Y else []) + ([tier] if tier else [])
        for k in keys:
            a = acc[k]
            if not np.isnan(f12[i]):
                a["f12"].append(f12[i])
                if k != "base":
                    a["eps"].add(int(eps[i]))
            if not np.isnan(fdd[i]):
                a["drop"].append(fdd[i] < DROP_FURTHER)
    return acc


def summarize(a: dict, n_tickers: Optional[int] = None) -> Optional[dict]:
    """f12·drop 모음 → 표시용 요약. 1년 뒤 결과가 있는 날이 없으면 None."""
    f = np.asarray(a["f12"], dtype=float)
    if len(f) == 0:
        return None
    dr = np.asarray(a["drop"], dtype=float)
    out = {"days": int(len(f)), "med12": _r(np.median(f)), "loss": _r(np.mean(f < 0)),
           "drop15": _r(np.mean(dr)) if len(dr) else None}
    if "eps" in a:
        out["n_ep"] = len(a["eps"]) if isinstance(a["eps"], set) else int(a["eps"])
    if n_tickers is not None:
        out["tickers"] = n_tickers
    return out


def summarize_all(acc: dict) -> dict:
    return {"tiers": {k: summarize(acc[k]) for k in TIERS}, "base": summarize(acc["base"])}


def pool(accs: list[dict]) -> dict:
    """여러 종목의 walk_forward 결과를 합친 묶음 요약(국면 수는 종목별 합)."""
    out = {"tiers": {}, "base": None}
    for k in TIERS + ("base",):
        f12 = [v for a in accs for v in a[k]["f12"]]
        drop = [v for a in accs for v in a[k]["drop"]]
        eps = sum(len(a[k]["eps"]) for a in accs)
        n_t = sum(1 for a in accs if a[k]["f12"])
        s = summarize({"f12": f12, "drop": drop, "eps": eps}, n_t)
        if k == "base":
            out["base"] = s
        else:
            out["tiers"][k] = s
    return out


def pick_stats(tier: str, own: dict, grp: dict, group: str) -> Optional[dict]:
    """카드 3줄용: 지금 판단의 과거 결과. 종목 자체 사례(하락 국면)가 MIN_SELF_EPISODES 이상이면 종목 값, 아니면 같은 묶음
    (2종목 이상) 값. 묶음도 없으면 적은 사례라도 종목 값을 few=True로 준다(화면에 '사례 적음' 표시)."""
    if tier == "unknown":
        return None
    t_own = (own.get("tiers") or {}).get(tier)
    if t_own and t_own.get("n_ep", 0) >= MIN_SELF_EPISODES and own.get("base"):
        return {"src": "self", "group": group, "tier": t_own, "base": own["base"]}
    t_grp = (grp.get("tiers") or {}).get(tier)
    if t_grp and grp.get("base") and t_grp.get("tickers", 0) >= 2:
        return {"src": "group", "group": group, "tier": t_grp, "base": grp["base"]}
    if t_own and own.get("base"):
        return {"src": "self", "group": group, "tier": t_own, "base": own["base"], "few": True}
    return None


# ---- 3분할 매수 의견 ----

def anchor_indices(tiers: list, eps) -> list[int]:
    """3분할 1차 신호: 하락 국면마다 매수 판단(BUY_TIERS)이 처음 나온 날. 같은 하락이 이어져도 3분할은 1년(BARS_1Y)으로
    끝나므로(백테스트·간격이 모두 1년 기준), 그 뒤 처음 나온 매수 판단 날이 새 3분할의 1차다 - 몇 년째 하락 중인 종목에
    2008년 1차 같은 의미 없는 기준이 남지 않게(034020·ADBE 등 2026-11 점검)."""
    out: list[int] = []
    last_ep, last_a = None, None
    for i, t in enumerate(tiers):
        if t not in BUY_TIERS or not eps[i]:
            continue
        if eps[i] != last_ep or i - last_a >= BARS_1Y:
            out.append(i)
            last_ep, last_a = eps[i], i
    return out


def first_buy_in_episode(tiers: list, eps, i: Optional[int] = None, extra: tuple = ()) -> Optional[int]:
    """i일(기본 마지막 날)의 1차 신호 = 그 하락 국면 안에서 anchor_indices와 같은 규칙으로 정한 가장 최근 1차.
    신고가(국면 밖)이거나 매수 판단이 아직 없거나, 마지막 1차에서 1년이 지나 그 3분할이 끝났으면 None.
    extra는 이 종목에서 매수 판단으로 함께 보는 판단(급등 뒤 하락 규칙이 이 종목 자료로 받쳐지지 않을 때 "hot")."""
    buy = BUY_TIERS + tuple(extra)
    i = len(tiers) - 1 if i is None else i
    e = eps[i]
    if not e:
        return None
    j = i
    while j > 0 and eps[j - 1] == e:
        j -= 1
    a = None
    for k in range(j, i + 1):
        if tiers[k] in buy and (a is None or k - a >= BARS_1Y):
            a = k
    if a is not None and i - a >= BARS_1Y:
        return None
    return a


def _next_buy(tiers: list, eps) -> np.ndarray:
    """i일부터(같은 하락 국면 안) 처음 매수 판단이 나오는 날. 없으면 -1."""
    n = len(tiers)
    nxt = np.full(n, -1, dtype=int)
    cur = -1
    for i in range(n - 1, -1, -1):
        if i + 1 < n and eps[i + 1] != eps[i]:
            cur = -1
        if tiers[i] in BUY_TIERS:
            cur = i
        nxt[i] = cur
    return nxt


def _ladder_backtest(rows: list) -> Optional[dict]:
    """1차 신호 날 한 번에 vs 3분할(1/3씩 1차가·2차가·3차가, 1년 안 못 채운 몫은 현금)의 1년 뒤 결과.
    간격은 그 신호 날까지 1년이 끝난 과거 1차 신호만으로 정한다(워크포워드) - 그런 신호가 MIN_ANCHORS개 미만이면 건너뜀."""
    rows = sorted(rows, key=lambda r: r[0])
    ends = sorted((r[1], r[2]) for r in rows)
    end_dates = [e[0] for e in ends]
    lump, lad, f2s, f3s = [], [], [], []
    for date_a, _end, _m, _f, c, a in rows:
        k = bisect.bisect_right(end_dates, date_a)
        if k < MIN_ANCHORS:
            continue
        prior = np.array([e[1] for e in ends[:k]])
        s2, s3 = float(np.median(prior)), float(np.percentile(prior, 25))
        p1, end = c[a], c[a + BARS_1Y]
        lo = float(np.min(c[a:a + BARS_1Y + 1]))
        p2, p3 = p1 * (1 + s2), p1 * (1 + s3)
        f2, f3 = lo <= p2, lo <= p3
        lump.append(end / p1 - 1)
        lad.append((end / p1 + (end / p2 if f2 else 1.0) + (end / p3 if f3 else 1.0)) / 3 - 1)
        f2s.append(f2)
        f3s.append(f3)
    if not lump:
        return None
    lu, la = np.array(lump), np.array(lad)
    return {"n": len(lu), "lump": _r(np.median(lu)), "lump_loss": _r(np.mean(lu < 0)), "lump_min": _r(lu.min()),
            "lad": _r(np.median(la)), "lad_loss": _r(np.mean(la < 0)), "lad_min": _r(la.min()),
            "f2": _r(np.mean(f2s)), "f3": _r(np.mean(f3s))}


def _hot_stats(walks: list[dict]) -> Optional[dict]:
    """급등 뒤 하락 날(1년 뒤가 있는 날): 1년 안 최저점 분포와 '기다린 비용' - 같은 하락 안에서 매수 판단으로 바뀐 비율·
    걸린 거래일·그날 가격 차이(중앙값), 바뀌기 전에 신고가로 회복해 놓친 비율, 그리고 바로 산 1년 뒤 vs 바뀐 날 산 1년 뒤.
    (2026-11 점검: 기다려도 1년 수익은 나아지지 않았다 - 미국ETF +7.4%→+5.6%, 한국주식 +1.3%→-1.3%. 기다리라는 근거는
    수익이 아니라 '산 뒤 6개월 안 15% 넘게 더 빠지는 일이 모든 묶음에서 아무 때나보다 잦았다'는 추가 하락 위험이다.)"""
    m, days, px, sw, tot, now12, wait12 = [], [], [], 0, 0, [], []
    for w in walks:
        c, tiers, f12 = w["close"], w["tiers"], w["f12"]
        nxt = _next_buy(tiers, w["eps"])
        for i, t in enumerate(tiers):
            if t != "hot" or np.isnan(w["m12"][i]):
                continue
            tot += 1
            m.append(w["m12"][i])
            now12.append(f12[i])
            j = int(nxt[i])
            if j >= 0:
                sw += 1
                days.append(j - i)
                px.append(c[j] / c[i] - 1)
                if not np.isnan(f12[j]):
                    wait12.append(f12[j])
    if tot == 0:
        return None
    ma, nw_, wt = np.array(m), np.array(now12), np.array(wait12)
    return {"days_n": tot, "m_med": _r(np.median(ma)), "m_p25": _r(np.percentile(ma, 25)), "m15": _r(np.mean(ma < -0.15)),
            "sw": _r(sw / tot), "sw_days": int(np.median(days)) if days else None,
            "sw_px": _r(np.median(px)) if px else None, "missed": _r(1 - sw / tot),
            "now12": _r(np.median(nw_)), "now_loss": _r(np.mean(nw_ < 0)),
            "wait12": _r(np.median(wt)) if len(wt) else None, "wait_loss": _r(np.mean(wt < 0)) if len(wt) else None}


def ann_vol(close: np.ndarray, i: Optional[int] = None) -> Optional[float]:
    """i일(기본 마지막 날)까지 1년 일간 로그수익률 표준편차(연율). 1년이 안 되면 None."""
    c = np.asarray(close, dtype=float)
    i = len(c) - 1 if i is None else i
    if i < BARS_1Y:
        return None
    return _r(float(np.std(np.diff(np.log(c[i - BARS_1Y:i + 1])), ddof=1) * np.sqrt(BARS_1Y)))


def plan_stats(walks: list[dict]) -> Optional[dict]:
    """묶음 3분할 통계(walk_days 목록, 날짜 필요). n=1년이 끝난 1차 신호 수, s2·s3=그 뒤 1년 안 최저점의 중앙값·하위 25%
    (= 오늘 쓰는 2·3차 간격), lump=1차 날 한 번에 산 1년 뒤 결과, ladder=한 번에 vs 3분할 워크포워드 백테스트,
    hot=급등 뒤 하락 날의 추가 하락·기다린 비용."""
    rows, vols = [], []
    for w in walks:
        c, dates = w["close"], w["dates"]
        for a in anchor_indices(w["tiers"], w["eps"]):
            if a + BARS_1Y < len(c):
                rows.append((dates[a], dates[a + BARS_1Y], float(w["m12"][a]), float(w["f12"][a]), c, a))
                v = ann_vol(c, a)
                if v:
                    vols.append(v)
    if not rows:
        return None
    m = np.array([r[2] for r in rows])
    f = np.array([r[3] for r in rows])
    return {"n": len(rows), "s2": _r(np.median(m)), "s3": _r(np.percentile(m, 25)),
            "vol_med": _r(np.median(vols)) if vols else None,
            "lump": {"med12": _r(np.median(f)), "loss": _r(np.mean(f < 0))},
            "ladder": _ladder_backtest(rows), "hot": _hot_stats(walks)}


def scale_for_vol(gplan: dict, vol: Optional[float], cap: float = 2.5) -> dict:
    """1차 신호가 적어 전체 묶음 간격(src=all)을 쓰는 종목은 간격을 변동성 비율만큼 넓힌다(1~cap배, 2차 -60%·3차 -80% 한도).
    비트코인(변동성 0.5~0.9 vs 1차 신호 날 중앙 0.28): 전체 간격 그대로면 자기 1차 신호 7번 중 2차 5번·3차 3번 체결로
    설계(약 50%·25%)보다 너무 촘촘했고, 변동성 맞춤이면 3번·1번(2026-11 점검). 묶음 간격이 있는 종목은 그대로 둔다 —
    묶음 안에서 변동성 맞춤은 체결률을 오히려 벌렸다(변동성 3분위별 2차 체결 묶음 간격 50/57/50% vs 맞춤 61/59/42%)."""
    if not vol or not gplan.get("vol_med"):
        return gplan
    k = min(max(vol / gplan["vol_med"], 1.0), cap)
    if k <= 1.0:
        return gplan
    return {**gplan, "s2": _r(max(gplan["s2"] * k, -0.6)), "s3": _r(max(gplan["s3"] * k, -0.8)), "scaled": _r(k, 2)}


def hot_release(close: np.ndarray, limit: float = HOT_NET_1Y) -> Optional[dict]:
    """급등 뒤 하락 조건(1년 전 대비 +limit 초과)이 풀리는 가격·지금 대비 변화율, 가격이 그대로일 때 풀리는 거래일 수
    (1년 전 기준가가 하루씩 뒤로 밀린다 - HOT_SCAN_DAYS 안에 없으면 None)."""
    c = np.asarray(close, dtype=float)
    if len(c) <= BARS_1Y:
        return None
    price = c[-BARS_1Y - 1] * (1 + limit)
    days = next((k for k in range(1, HOT_SCAN_DAYS + 1) if c[-1] / c[-BARS_1Y - 1 + k] - 1 <= limit), None)
    return {"price": _r(price), "gap": _r(price / c[-1] - 1), "days": days}


def compare(ev: dict, base: dict) -> dict:
    """근거 비교어 - 1년 뒤 중앙값: better/same/worse, 손해 확률: lower/same/higher, 6개월 안 15% 넘게 더 빠진 비율:
    more/same/less(차이가 EDGE 안이면 same)."""
    dm = round((ev.get("med12") or 0) - (base.get("med12") or 0), 4)
    dl = round((ev.get("loss") or 0) - (base.get("loss") or 0), 4)
    out = {"med": "better" if dm >= EDGE_MED else "worse" if dm <= -EDGE_MED else "same",
           "loss": "lower" if dl <= -EDGE_LOSS else "higher" if dl >= EDGE_LOSS else "same"}
    if ev.get("drop15") is not None and base.get("drop15") is not None:
        dd = round(ev["drop15"] - base["drop15"], 4)
        out["drop"] = "more" if dd >= EDGE_LOSS else "less" if dd <= -EDGE_LOSS else "same"
    return out


def weak_edge(cmp: dict) -> bool:
    """근거가 아무 때나보다 나빴다: 1년 뒤 중앙값이 EDGE 넘게 낮거나, 비슷한데 손해 확률이 EDGE 넘게 높음.
    워크포워드 검증(validate_buy_rules ②, 1차 신호 1073번, 그날까지 1년이 끝난 묶음 자료로 분류): 이런 신호는 1년 뒤
    +10.1%·손해 35%, 근거가 비슷·나았던 신호는 +16.0%·23%, +16.3%·27% — 그래서 이런 날은 1차 대신 '추가 매수 보류'."""
    return cmp.get("med") == "worse" or (cmp.get("med") == "same" and cmp.get("loss") == "higher")


def hot_supported(stats: Optional[dict]) -> bool:
    """급등 뒤 하락에서 1차를 미루는 규칙이 이 종목·묶음 자료로도 받쳐지는가: 산 뒤 6개월 안 추가 하락이 아무 때나보다
    잦았거나(모든 큰 묶음이 그랬다) 1년 뒤가 나빴다. 둘 다 아니면 이 종목엔 급등 규칙을 적용하지 않는다(깊이 판단으로)."""
    if not stats or not stats.get("tier") or not stats.get("base"):
        return True
    c = compare(stats["tier"], stats["base"])
    return c.get("drop") == "more" or weak_edge(c)


def tier_profile(walk: dict, tier: str) -> Optional[dict]:
    """이 종목의 tier 날(1년 결과 있는 날)을 하락 국면별로 묶음: 국면 수, 1년 뒤 중앙값, 일수가 가장 많은 두 국면의 비중·연도."""
    idx = [i for i, t in enumerate(walk["tiers"]) if t == tier and not np.isnan(walk["f12"][i])]
    if not idx:
        return None
    by: dict = {}
    for i in idx:
        by.setdefault(int(walk["eps"][i]), []).append(i)
    top = sorted(by.values(), key=len, reverse=True)[:2]
    years = sorted({str(walk["dates"][v[0]])[:4] for v in top}) if walk.get("dates") else []
    return {"n_ep": len(by), "days": len(idx), "med12": _r(np.median(walk["f12"][idx])),
            "top2": _r(sum(len(v) for v in top) / len(idx)), "years": years}


def no_edge(gpool: Optional[dict]) -> bool:
    """묶음에서 매수 판단(적극·분할) 날의 1년 뒤 중앙값이 아무 날보다 EDGE_MED 넘게 낫지 않았으면 True."""
    if not gpool or not gpool.get("base"):
        return False
    b = gpool["base"]["med12"]
    vals = [s["med12"] for k in ("strong", "split") if (s := (gpool.get("tiers") or {}).get(k))]
    return bool(vals) and all(v - b < EDGE_MED for v in vals)


def current_anchor(walk: Optional[dict], dates: list, depth: np.ndarray, tier: str,
                   extra: tuple = ()) -> tuple[Optional[int], Optional[str]]:
    """이번 하락(이 종목 낙폭 기준)의 1차 신호 날 인덱스(이 종목 시계열)와 그날 판단. walk가 원본 자산(BASELINE_PROXY)이면
    날짜로 옮긴다. 일별 판단엔 아직 없는데 오늘 판단이 매수면(백분위 갱신 시점 차이) 오늘을 1차로 본다.
    extra = 이 종목에서 매수 판단으로 함께 보는 판단(first_buy_in_episode 참고)."""
    d = np.asarray(depth, dtype=float)
    start = current_episode_start(d)
    if start is None:
        return None, None
    if walk is not None:
        a = first_buy_in_episode(walk["tiers"], walk["eps"], extra=extra)
        if a is not None:
            tier_a = walk["tiers"][a]
            wd = walk.get("dates")
            if wd is not None and (len(wd) != len(d) or wd[-1] != dates[-1]):
                a = bisect.bisect_right(list(dates), wd[a]) - 1      # 원본 날짜 이하의 마지막 거래일
            if a >= start:
                return a, tier_a
    if tier in BUY_TIERS + tuple(extra):
        return len(d) - 1, tier
    return None, None


def plan(tier: str, close: np.ndarray, dates: list, high: float, pct: Optional[dict],
         anchor: tuple[Optional[int], Optional[str]], stats: Optional[dict], gplan: Optional[dict],
         gpool: Optional[dict], walk: Optional[dict], group: str,
         hot_ok: bool = False, alt: Optional[dict] = None) -> dict:
    """3분할 매수 의견(카드 회색 박스). tier=오늘 판단, close·dates=이 종목, high=오늘 신고가, pct=단계 기준 백분위,
    anchor=current_anchor 결과, stats=pick_stats(오늘 판단의 과거 결과), gplan=plan_stats(묶음, 적으면 전체 + scale_for_vol),
    gpool=pool(묶음 판단별 결과), walk=판단 일별 배열(사례 쏠림 확인용), hot_ok=급등 뒤 하락 규칙이 이 종목 자료로
    받쳐지지 않음(hot_supported False → 급등 뒤도 매수 판단), alt=보류일 때 근거가 생기는 다음 깊이(드문 깊이 선 {price, gap}).
    state: wait(더 기다리기) / t1(1차 매수 시작) / t2 / t3 / hold(추가 매수 보류 — 매수 판단이지만 근거가 아무 때나보다
    나빴음, weak_edge) / unknown(판단 보류). 칩이 3줄 근거와 반대로 말하지 않게 하는 것이 hold다(2026-11 점검: 23개 카드)."""
    if tier == "unknown" or pct is None or not gplan:
        return {"state": "unknown"}
    buy = BUY_TIERS + (("hot",) if hot_ok else ())
    c = np.asarray(close, dtype=float)
    px = float(c[-1])
    lv: dict = {"s2": gplan["s2"], "s3": gplan["s3"], "n": gplan["n"], "src": gplan.get("src", "group")}
    if gplan.get("scaled"):
        lv["scaled"] = gplan["scaled"]
    out: dict = {"lv": lv, "t1": None, "cond": None}
    a, tier_a = anchor
    if a is not None:
        p1 = float(c[a])
        p2, p3 = p1 * (1 + gplan["s2"]), p1 * (1 + gplan["s3"])
        lv.update({"t2": _r(p2), "t3": _r(p3)})
        d1 = str(dates[a])[:10]
        # 3분할은 1년 단위(백테스트·간격 모두 1년) — 2·3차 가격이 그때까지 안 오면 남은 몫은 사지 않는다(현금)
        out["t1"] = {"date": d1, "price": _r(p1), "until": (date.fromisoformat(d1) + timedelta(days=365)).isoformat()}
        if px <= p3:
            state = "t3"
        elif px <= p2:
            state = "t2"
        elif tier not in buy and px > p1 * (1 + REBOUND):
            state = "wait"
        else:
            state = "t1"
        why = tier if tier in buy else (tier_a or tier)
        if state == "wait":
            why = "rebound"
            out["cond"] = {"kind": "rebound", "price": _r(p1), "gap": _r(p1 / px - 1)}
    else:
        state, why = "wait", tier
        if tier == "hot":
            hr = hot_release(c)
            out["cond"] = {"kind": "hot", **hr} if hr else None
        else:
            line = high * (1 + pct["p25"])
            out["cond"] = {"kind": "stage2", "price": _r(line), "gap": _r(line / px - 1), "level": _r(pct["p25"])}
    buying = state in ("t1", "t2", "t3")

    # 근거: 지금 판단의 과거 결과(같은 판단 날 샀다면) - 1차 신호 뒤인데 지금 판단이 매수가 아니면 묶음의 1차 신호 결과
    ev = None
    if buying and tier not in buy and gpool and gpool.get("base"):
        ev = {"src": "anchor", "group": group, "n": gplan["n"], "med12": gplan["lump"]["med12"],
              "loss": gplan["lump"]["loss"], "drop15": None, "base": gpool["base"]}
    elif stats and stats.get("tier") and stats.get("base"):
        s, b = stats["tier"], stats["base"]
        ev = {"src": stats["src"], "group": stats.get("group", group), "n": s.get("n_ep"), "tickers": s.get("tickers"),
              "med12": s["med12"], "loss": s["loss"], "drop15": s.get("drop15"), "base": b, "few": bool(stats.get("few"))}
    if ev:
        ev["base"] = {k: ev["base"].get(k) for k in ("med12", "loss", "drop15")}
        ev["cmp"] = compare(ev, ev["base"])
    out["ev"] = ev
    # 근거 확인: 매수 판단이어도 이 종목·묶음의 같은 판단 결과가 아무 때나보다 나빴으면 1차를 권하지 않는다(워크포워드 검증)
    if buying and ev and weak_edge(ev["cmp"]):
        state, why, buying = "hold", "noedge", False
        out["cond"] = {"kind": "rare", **alt} if alt else None
    out["aggr"] = bool(buying and tier == "strong" and ev and ev["cmp"]["med"] == "better" and ev["cmp"]["loss"] == "lower")

    # 알아두실 점(화면이 상태에 맞는 것만 골라 문장으로): 숫자는 모두 위 통계에서 나온 것
    notes: dict = {}
    if gplan.get("ladder"):
        notes["ladder"] = gplan["ladder"]
    if state == "wait" and why == "hot" and gplan.get("hot"):
        notes["hot"] = gplan["hot"]
    if state == "wait" and why in ("watch", "wait"):
        wt = ((gpool or {}).get("tiers") or {}).get("watch")
        b = (gpool or {}).get("base")
        if wt and b and wt["med12"] - b["med12"] <= -EDGE_MED:
            notes["watch"] = {"med12": wt["med12"], "base": b["med12"], "level": _r(pct["p50"]),
                              "price": _r(high * (1 + pct["p50"]))}
    if buying and state != "t3" and ev and ev.get("drop15") is not None:
        notes["drop15"] = ev["drop15"]
    if buying:
        lines = [("p25", pct["p25"])]
        if pct.get("count", 0) >= mdd.MIN_EPISODES_FOR_P10:
            lines.append(("p10", pct["p10"]))
        for key in ("t2", "t3"):
            hit = next(({"lv": key, "line": name, "price": _r(high * (1 + q))} for name, q in lines
                        if abs(lv[key] / (high * (1 + q)) - 1) <= CONF_TOL), None)
            if hit:
                notes["conf"] = hit
                break
    if walk is not None and ev and ev["src"] in ("self", "group"):
        prof = tier_profile(walk, tier)
        if prof and ev["src"] == "group":
            notes["self"] = prof                    # 이 종목만 보면(사례가 적어 묶음을 썼을 때 대비)
        elif prof and prof["n_ep"] >= 3 and prof["top2"] >= 0.8:
            notes["conc"] = prof                    # 이 종목 사례가 두 번의 하락에 몰림
    if no_edge(gpool):
        notes["no_edge"] = True
    if state == "hold":
        notes["hold"] = True
    if tier == "record":
        notes["record"] = True
    out.update({"state": state, "why": why, "notes": notes})
    return out

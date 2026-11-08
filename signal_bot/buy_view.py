"""매수 판단("지금 살 때인가") 지표 - 계산은 전부 여기서 하고 화면(signals/index.html)은 그리기만 한다.

낙폭 단계(mdd.classify_stage: 과거 조정 대비 깊이)에 두 가지를 더해 판단을 정한다.
- 시간상 드문 깊이: 지금 하락이 시작되기 전 모든 날 중 오늘보다 깊었던 날의 비율(days_deeper).
- 급등 뒤 하락: 1년 전 대비 수익률(net_1y)이 +30%를 넘으면 고점이 부풀려진 상태라 같은 낙폭이라도 위험이 크다.

판단(verdict) 순서: unknown(과거 국면 5개 미만) → record(사상 최대 낙폭) → hot(2단계+ · 1년 +30% 초과)
→ strong(2단계+ · 드문 깊이 ≤10%) → split(2단계+) → watch(1단계) → wait.

같은 판단이 과거에 어땠는지는 워크포워드로 센다 - 과거 매일에 대해 그날까지의 국면·날짜만으로 판단을 다시 내리고
(미래 정보 미사용), 그 뒤 1년 수익률·6개월 안 추가 하락을 모은다. 검증 결과는 validate_buy_rules.py 참고.
"""

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


def forward_arrays(close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(1년 뒤 수익률, 6개월 안 최저가 기준 추가 하락률) - 미래가 모자란 날은 NaN."""
    c = np.asarray(close, dtype=float)
    n = len(c)
    f12 = np.full(n, np.nan)
    if n > BARS_1Y:
        f12[:n - BARS_1Y] = c[BARS_1Y:] / c[:n - BARS_1Y] - 1
    fmin = pd.Series(c[::-1]).rolling(BARS_6M + 1, min_periods=BARS_6M + 1).min().to_numpy()[::-1]
    return f12, fmin / c - 1


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


def walk_forward(close: np.ndarray, depth: np.ndarray) -> dict:
    """과거 매일의 판단(daily_tiers)과 그 뒤 결과. 반환: {tier|"base": {"f12": [...], "drop": [...], "eps": set}}."""
    f12, fdd = forward_arrays(close)
    tiers, eps = daily_tiers(close, depth)
    acc = {k: {"f12": [], "drop": [], "eps": set()} for k in TIERS + ("base",)}
    for i, tier in enumerate(tiers):
        keys = (["base"] if i >= BARS_1Y else []) + ([tier] if tier else [])
        for k in keys:
            a = acc[k]
            if k != "base":
                a["eps"].add(eps[i])
            if not np.isnan(f12[i]):
                a["f12"].append(f12[i])
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

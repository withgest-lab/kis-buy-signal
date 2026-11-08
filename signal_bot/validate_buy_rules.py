"""매수 판단 규칙(buy_view.verdict) 검증 - 배포된(또는 로컬) detail/*.json 전체로 워크포워드 결과를 다시 센다.

    uv run python -m signal_bot.validate_buy_rules                # 배포된 데이터(공개 URL)
    uv run python -m signal_bot.validate_buy_rules docs           # 로컬 docs/ (export_dashboard 실행 후)

워크포워드: 과거 매일, 그날까지의 국면·날짜만으로 판단을 다시 내리고(미래 정보 미사용) 그 뒤 1년 수익률과
6개월 안 추가 하락(-15% 이상)을 모은다. 표의 '일수'는 1년 뒤 결과가 있는 날 수, '하락'은 그 판단이 나온 하락 국면 중
1년 뒤 결과가 있는 것의 수(진행 중 하락은 세지 않는다 - 2026-11-08 수정 전엔 세서 SOXX가 묶음 대신 자기 숫자를 썼다).

3분할(buy_view.plan_stats, 2026-11-08): 1차 = 하락마다 매수 판단 첫날(하락이 1년 넘게 이어지면 1년마다 새 1차),
2·3차 = 과거 1차 뒤 1년 안 최저점의 중앙값·하위 25%(그날까지 1년이 끝난 신호만). 간격: 지수 -7.7%·-13.6%,
미국ETF -11.9%·-23.3%, 미국주식 -8.1%·-19.5%, 한국주식 -17.2%·-29.6%, 일본주식 -12.6%·-23.2%.
한 번에 vs 3분할(못 채운 몫은 현금) 1년 뒤 중앙값/손해 확률, 워크포워드 1221번: +14.2%/29% vs +7.8%/21%
(2차 체결 50%, 3차 23%) - 수익보다 손해를 줄이는 방법. 한국 개별주만 둘 다 나았다(+0.2%/49% vs +2.7%/37%).
급등 뒤 하락 날 기다리면 76%가 중앙 18거래일 뒤 매수 판단으로 바뀌고(그날 가격 -3.0%) 24%는 그 전에 신고가로 놓쳤다
(미국ETF 90%/10%, 미국주식 57%/43%).

3분할 진행 로직 점검(plan_checks, 2026-11-08 오후 — 일본 보정 데이터):
 ① 남은 2/3를 언제 사나(1091번, 1년 뒤 중앙/손해/나쁜 10%/투입): 한 번에 +14.3%/29%/-20%/100%, 가격으로만(지금)
    +8.1%/21%/-7%/59%, 가격 또는 6·9개월 +10.1%/27%/-13%/100%, 0·3·6개월 시간 +9.8%/31%/-15%/100% — 시간 분할은
    한 번에 사는 것보다 나을 게 없고, 가격으로만이 손해·나쁜 경우를 가장 줄인다 → 가격으로만 + 기한 1년 유지.
 ② 근거 확인(1073번): 그날까지 근거가 나빴던(weak_edge) 1차 신호 381번 +10.1%/손해 35%, 비슷 284번 +16.0%/23%,
    나았음 408번 +16.3%/27% → 근거가 나쁘면 '추가 매수 보류'(buy_view.plan hold).
 ③ 급등 뒤 하락: 바로 vs 기다렸다 매수 판단 날 — 미국ETF +7.4%/39% vs +5.6%/43%(놓침 10%), 한국주식 +1.3% vs -1.3%,
    일본주식 -1.6% vs -11.3%, 미국주식 +34.4% vs +21.3%(놓침 43%). 기다려도 1년 수익은 안 나아짐 → 기다리는 근거는
    6개월 안 15% 넘게 더 빠지는 일이 모든 큰 묶음에서 잦았다는 추가 하락 위험(hot_supported)으로만 쓴다.
 변동성 맞춤 간격은 묶음 안에서 체결률을 벌려(변동성 3분위별 2차 체결 묶음 간격 50/57/50% vs 맞춤 61/59/42%) 쓰지 않고,
 1차 신호가 적어 전체 간격을 쓰는 묶음(비트코인)만 scale_for_vol로 넓힌다.

2026-11-08 결과(148종목, 약 20년, 상장 3년 이상, 전체 날짜) — 1년 뒤 중앙값 / 손실 확률 / 6개월 안 -15%↓.
분할 보정 베이스라인 + 일본 2014-04 이전 제거 + ISRG 2017 수정주가 보정(baseline_fetch.fix_history) 기준:
  평소(모든 날)    +13.5% / 29% / 29%
  적극 매수 검토   +15.9% / 27% / 32%   (지수만 +17.9% / 6% / 9%, 일본 개별주 +23% / 17%, 한국 개별주는 평소와 비슷)
  분할 매수 검토   +12.9% / 32% / 33%
  신중·급등 뒤     +12.3% / 39% / 43%   (지수만 -11.1% / 66%, 일본 개별주 -1.6% / 52%)
  관찰(1단계)      +11.4% / 34% / 31%
  주의·사상최대    +18.1% / 30% / 36%   (망한 종목이 빠져 특히 낙관적)
일본 2014-03 이전 가짜 구간이 있을 때는 일본 개별주 '평소'가 +21%로 부풀려졌었다(정상 +14.5%).
일봉 다이버전스·과매도는 2단계 이상에서 결과를 바꾸지 못해(약 +14% · 손실 32%로 같음) 판단에서 뺐다.
주의: 지금 남아 있는 대형주만 대상(생존 편향) - 특히 미국 개별주 결과가 좋게 나온다. 한국 개별주는 평소에도 손실 확률이 높다(42%).
"""

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from signal_bot import buy_view

DEFAULT_BASE = "https://withgest-lab.github.io/portfolio-retirement-dashboard/signals/"
NAMES = {"strong": "적극 매수 검토", "split": "분할 매수 검토", "hot": "신중·급등 뒤", "watch": "관찰(1단계)",
         "wait": "대기", "record": "주의·사상최대", "base": "평소(모든 날)"}


def _loader(src: str):
    if src.startswith("http"):
        return lambda p: json.loads(urllib.request.urlopen(src + p, timeout=90).read())
    root = Path(src)
    return lambda p: json.loads((root / p).read_text(encoding="utf-8"))


H = buy_view.BARS_1Y
VARIANTS = (("lump", "1차 날 한 번에"), ("ladder", "가격으로만(지금)"), ("pt126_189", "가격 또는 6·9개월"), ("dca", "0·3·6개월 시간으로"))


def _simulate(r: dict, sp: tuple, variant: str) -> tuple[float, float]:
    """1차 신호 날부터 1년 뒤 총자금 수익률과 투입 비율. 못 채운 몫은 현금(0%)."""
    c, a = r["c"], r["a"]
    path = c[a:a + H + 1]
    p1, end = c[a], c[a + H]
    if variant == "lump":
        return end / p1 - 1, 1.0
    p2, p3 = p1 * (1 + sp[0]), p1 * (1 + sp[1])
    hit = lambda m: (int(np.flatnonzero(m)[0]) if m.any() else None)
    h2, h3 = hit(path <= p2), hit(path <= p3)
    buys = [p1]
    if variant == "ladder":
        buys += [p for h, p in ((h2, p2), (h3, p3)) if h is not None]
    elif variant == "pt126_189":
        buys += [p2 if h2 is not None and h2 <= 126 else path[126], p3 if h3 is not None and h3 <= 189 else path[189]]
    elif variant == "dca":
        buys += [path[63], path[126]]
    return sum(end / p for p in buys) / 3 + (3 - len(buys)) / 3 - 1, len(buys) / 3


def plan_checks(group_days: dict) -> None:
    """3분할 진행 로직 점검 표 3개(2026-11-08): ① 남은 2/3를 언제 사나 ② 근거 확인(보류 규칙) ③ 급등 뒤 바로 vs 기다림."""
    rows = []
    for g, ds in group_days.items():
        for w in ds:
            for a in buy_view.anchor_indices(w["tiers"], w["eps"]):
                if a + H < len(w["close"]):
                    rows.append({"g": g, "da": w["dates"][a], "de": w["dates"][a + H], "tier": w["tiers"][a],
                                 "m12": w["m12"][a], "f12": w["f12"][a], "c": w["close"], "a": a})
    rows.sort(key=lambda r: r["da"])
    by_g: dict = {}
    for r in rows:
        by_g.setdefault(r["g"], []).append(r)

    # ① 간격은 그 신호 날까지 1년이 끝난 같은 묶음 신호로(워크포워드)
    res = {v: [] for v, _ in VARIANTS}
    dep = {v: [] for v, _ in VARIANTS}
    for r in rows:
        prior = np.array([x["m12"] for x in by_g[r["g"]] if x["de"] <= r["da"]])
        if len(prior) < buy_view.MIN_ANCHORS:
            continue
        sp = (float(np.median(prior)), float(np.percentile(prior, 25)))
        for v, _ in VARIANTS:
            ret, d = _simulate(r, sp, v)
            res[v].append(ret)
            dep[v].append(d)
    print(f"\n[3분할 ① 남은 2/3를 언제 사나 — 1차 신호 {len(res['lump'])}번, 1년 뒤 중앙 / 손해 / 나쁜 10% / 투입]")
    for v, name in VARIANTS:
        a = np.array(res[v])
        print(f"   {name:16s} {np.median(a) * 100:+6.1f}% {np.mean(a < 0) * 100:4.0f}% {np.percentile(a, 10) * 100:+5.0f}% {np.mean(dep[v]) * 100:4.0f}%")

    # ② 그 신호 날까지 1년 결과가 끝난 묶음 자료로 같은 판단 vs 아무 때나를 분류 → 실제 1년 뒤
    pool: dict = {}
    for g, ds in group_days.items():
        for w in ds:
            n = len(w["close"])
            for i, t in enumerate(w["tiers"]):
                if i < H or i + H >= n:
                    continue
                pool.setdefault((g, "base"), []).append((w["dates"][i + H], w["f12"][i]))
                if t:
                    pool.setdefault((g, t), []).append((w["dates"][i + H], w["f12"][i]))
    idx = {k: (np.array([x[0] for x in sorted(v)]), np.array([x[1] for x in sorted(v)])) for k, v in pool.items()}

    def as_of(key, d):
        if key not in idx:
            return None
        de, f = idx[key]
        m = np.searchsorted(de, d, side="right")
        return (float(np.median(f[:m])), float(np.mean(f[:m] < 0))) if m >= 200 else None

    cls: dict = {}
    for r in rows:
        e, b = as_of((r["g"], r["tier"]), r["da"]), as_of((r["g"], "base"), r["da"])
        if not e or not b:
            continue
        cmp = buy_view.compare({"med12": e[0], "loss": e[1]}, {"med12": b[0], "loss": b[1]})
        k = "나빴음(보류)" if buy_view.weak_edge(cmp) else "나았음" if cmp["med"] == "better" and cmp["loss"] != "higher" else "비슷"
        cls.setdefault(k, []).append(r["f12"])
    print(f"\n[3분할 ② 근거 확인 — 그날까지의 근거로 분류한 1차 신호 {sum(len(v) for v in cls.values())}번의 실제 1년 뒤]")
    for k, v in sorted(cls.items()):
        v = np.array(v)
        print(f"   {k:10s} {len(v):5d}번 {np.median(v) * 100:+6.1f}% 손해 {np.mean(v < 0) * 100:3.0f}%")

    # ③ 급등 뒤 하락인 날: 바로 산 1년 뒤 vs 같은 하락에서 매수 판단으로 바뀐 날 산 1년 뒤
    print("\n[3분할 ③ 급등 뒤 하락 — 바로 사기 vs 기다렸다 매수 판단 날 사기(1년 뒤 중앙/손해), 놓침=판단 전 신고가]")
    for g, ds in sorted(group_days.items()):
        now, wait, missed, tot = [], [], 0, 0
        for w in ds:
            n = len(w["close"])
            nxt = buy_view._next_buy(w["tiers"], w["eps"])
            for i, t in enumerate(w["tiers"]):
                if t != "hot" or i + H >= n:
                    continue
                tot += 1
                now.append(w["f12"][i])
                j = int(nxt[i])
                if j < 0:
                    missed += 1
                elif j + H < n:
                    wait.append(w["f12"][j])
        if tot < 100:
            continue
        nw_, wt = np.array(now), np.array(wait)
        print(f"   {g:8s} {tot:5d}일 바로 {np.median(nw_) * 100:+6.1f}%/{np.mean(nw_ < 0) * 100:3.0f}%  기다림 "
              f"{np.median(wt) * 100:+6.1f}%/{np.mean(wt < 0) * 100:3.0f}%  놓침 {missed / tot * 100:3.0f}%")


def main(src: str = DEFAULT_BASE) -> None:
    get = _loader(src)
    scores = get("scores.json")
    cats = {t["symb"]: t["category"] for t in scores["tickers"]}

    def walk(symb):
        try:
            uw = get(f"detail/{symb}.json")["underwater"]
        except Exception:
            return symb, None
        if len(uw) < 3 * buy_view.BARS_1Y:
            return symb, None
        c = np.array([r["close"] for r in uw], dtype=float)
        d = np.array([r["depth"] for r in uw], dtype=float)
        return symb, buy_view.walk_days(c, d, [r["date"] for r in uw])

    with ThreadPoolExecutor(12) as pool:
        days = {s: a for s, a in pool.map(walk, cats) if a is not None}
    walks = {s: buy_view.walk_forward(None, None, days=w) for s, w in days.items()}
    print(f"종목 {len(walks)}개 (상장 3년 이상)")

    def table(title, accs):
        pooled = buy_view.pool(accs)
        print(f"\n[{title}]  {'판단':14s} {'일수':>7s} {'하락':>5s} {'1년뒤 중앙값':>11s} {'손실':>6s} {'6개월내 -15%↓':>12s}")
        for k in ("base", "strong", "split", "hot", "watch", "wait", "record"):
            s = pooled["base"] if k == "base" else pooled["tiers"].get(k)
            if not s:
                continue
            print(f"   {NAMES[k]:14s} {s['days']:7d} {s.get('n_ep', 0) if k != 'base' else '':>5} "
                  f"{s['med12'] * 100:+10.1f}% {s['loss'] * 100:5.0f}% {(s['drop15'] or 0) * 100:11.0f}%")

    def plan_table(title, ds):
        p = buy_view.plan_stats(ds)
        if not p:
            return
        lad, hot = p.get("ladder"), p.get("hot")
        pc = lambda v: f"{v * 100:+.1f}%"
        print(f"\n[3분할 · {title}] 1차 신호 {p['n']}번 → 2차 {pc(p['s2'])} · 3차 {pc(p['s3'])} | "
              f"1차 날 한 번에 1년 뒤 {pc(p['lump']['med12'])} 손해 {p['lump']['loss'] * 100:.0f}%")
        if lad:
            print(f"   워크포워드 {lad['n']}번: 한 번에 {pc(lad['lump'])} / 손해 {lad['lump_loss'] * 100:.0f}% / 최악 {pc(lad['lump_min'])}"
                  f"  vs  3분할 {pc(lad['lad'])} / {lad['lad_loss'] * 100:.0f}% / {pc(lad['lad_min'])}"
                  f"  (2차 체결 {lad['f2'] * 100:.0f}%, 3차 {lad['f3'] * 100:.0f}%)")
        if hot:
            print(f"   급등 뒤 하락 {hot['days_n']}일: 1년 안 최저점 중앙 {pc(hot['m_med'])} 하위25% {pc(hot['m_p25'])}"
                  f" (15% 넘게 더 {hot['m15'] * 100:.0f}%) | 기다리면 매수 판단으로 바뀜 {hot['sw'] * 100:.0f}%"
                  f" (중앙 {hot['sw_days']}거래일, 가격 {pc(hot['sw_px'] or 0)}) · 신고가로 놓침 {hot['missed'] * 100:.0f}%")

    table("전체", list(walks.values()))
    groups: dict = {}
    group_days: dict = {}
    for s, a in walks.items():
        if s in ("IBIT",):
            continue
        groups.setdefault(buy_view.group_of(cats[s]), []).append(a)
        group_days.setdefault(buy_view.group_of(cats[s]), []).append(days[s])
    for g, accs in groups.items():
        table(f"{g} {len(accs)}종목", accs)
    plan_table("전체", [d for ds in group_days.values() for d in ds])
    for g, ds in group_days.items():
        plan_table(f"{g} {len(ds)}종목", ds)
    plan_checks(group_days)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

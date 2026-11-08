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


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

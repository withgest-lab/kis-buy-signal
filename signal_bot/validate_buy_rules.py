"""매수 판단 규칙(buy_view.verdict) 검증 - 배포된(또는 로컬) detail/*.json 전체로 워크포워드 결과를 다시 센다.

    uv run python -m signal_bot.validate_buy_rules                # 배포된 데이터(공개 URL)
    uv run python -m signal_bot.validate_buy_rules docs           # 로컬 docs/ (export_dashboard 실행 후)

워크포워드: 과거 매일, 그날까지의 국면·날짜만으로 판단을 다시 내리고(미래 정보 미사용) 그 뒤 1년 수익률과
6개월 안 추가 하락(-15% 이상)을 모은다. 표의 '일수'는 1년 뒤 결과가 있는 날 수, '하락'은 그 판단이 나온 하락 국면 수.

2026-11-08 결과(148종목, 약 20년, 상장 3년 이상, 전체 날짜, 분할 보정된 베이스라인) — 1년 뒤 중앙값 / 손실 확률 / 6개월 안 -15%↓:
  평소(모든 날)    +14.1% / 29% / 28%
  적극 매수 검토   +16.1% / 27% / 33%   (지수만 +17.9% / 6% / 9%, 한국 개별주는 평소와 비슷)
  분할 매수 검토   +12.9% / 33% / 33%
  신중·급등 뒤     +11.6% / 39% / 42%   (지수만 -11.1% / 66%)
  관찰(1단계)      +11.2% / 34% / 31%
  주의·사상최대    +18.6% / 28% / 34%   (하락 국면 159번뿐 · 망한 종목이 빠져 특히 낙관적)
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
        return symb, buy_view.walk_forward(c, d)

    with ThreadPoolExecutor(12) as pool:
        walks = {s: a for s, a in pool.map(walk, cats) if a is not None}
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

    table("전체", list(walks.values()))
    groups: dict = {}
    for s, a in walks.items():
        if s in ("IBIT",):
            continue
        groups.setdefault(buy_view.group_of(cats[s]), []).append(a)
    for g, accs in groups.items():
        table(f"{g} {len(accs)}종목", accs)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE)

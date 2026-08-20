"""상태 변화 감지(어제 미만 -> 오늘 이상) + 중복 알림 방지 (PROJECT_PLAN.md 섹션 4)."""

import json
from pathlib import Path

DATA_DIR = Path("signal_bot/data")
NOTIFIED_PATH = DATA_DIR / "notified.json"

# 2026-07-26 백테스트 검증: 65점은 70점과 거의 동일한 우위(OOS 126일 기준
# +2.36%p vs +2.45%p)를 유지하면서 신호 건수는 1.8배 더 잡음(조기 감지 목적에
# 부합). 60점은 우위가 절반 수준(+1.21%p)으로 희석돼서 기각.
STRONG_BUY_THRESHOLD = 65


def find_new_strong_signals(history: dict, today: str,
                             threshold: float = STRONG_BUY_THRESHOLD) -> list[dict]:
    """history: {date: {symb: {score, verdict, ...}}}. today가 첫 기록이면(전날 데이터 없음)
    비교 대상이 없으므로 빈 리스트를 반환한다 (오탐 방지)."""
    dates = sorted(history.keys())
    if today not in dates:
        return []
    idx = dates.index(today)
    if idx == 0:
        return []

    prev_date = dates[idx - 1]
    today_data = history[today]
    prev_data = history[prev_date]

    new_signals = []
    for symb, rec in today_data.items():
        prev_score = prev_data.get(symb, {}).get("score", 0)
        if prev_score < threshold and rec["score"] >= threshold:
            new_signals.append(rec)
    return new_signals


# 세부신호별 쉬운 설명 (detected 딕셔너리 키 -> (표시이름, 쉬운 설명))
_SIGNAL_EXPLAINS = {
    "divergence": ("다이버전스", "가격은 신저점을 찍었는데 RSI/MFI(매수·매도 힘을 나타내는 지표)는 "
                                  "오히려 덜 떨어졌습니다 → 하락시키는 힘이 약해지고 있다는 신호"),
    "squeeze": ("스퀴즈확장", "변동성이 한동안 좁게 움직이다가 다시 커지기 시작했습니다 → "
                              "조만간 큰 방향성 움직임이 나올 가능성"),
    "mfi_lead": ("MFI선행", "거래(돈)의 흐름을 보는 지표(MFI)가 가격보다 먼저 반등 조짐을 보였습니다 "
                            "→ 사람 심리보다 실제 돈의 움직임이 한발 먼저 방향을 튼 경우"),
    "vol_exhaustion": ("거래량소진", "최근 거래량이 눈에 띄게 줄었습니다 → 팔 사람은 이제 얼추 다 팔았다는 신호"),
}


def format_alert_message(new_signals: list[dict], today: str) -> str:
    regime = new_signals[0].get("market_regime", "판정불가") if new_signals else "판정불가"
    regime_note = {
        "상승장": "과거 검증상 이런 신호가 상대적으로 더 잘 맞았던 국면입니다.",
        "횡보장": "과거 검증상 눌림목 신호가 특히 잘 맞았던 국면입니다.",
        "하락장": "시장 전체가 하락 국면이라 신규 강한매수 신호는 자동으로 걸러집니다.",
        "판정불가": "시장 국면 판정에 필요한 데이터가 부족합니다.",
    }.get(regime, "")

    n = len(new_signals)
    lines = [
        f"📈 *KIS 매수신호 알림* ({today})",
        "",
        f"💡 *요약*: 오늘 {n}개 종목이 걸러졌습니다. 543종목을 사람이 매일 다 "
        "훑어보긴 불가능해서, 그중 \"한 번 볼 만한 후보\"만 골라드리는 겁니다. "
        "*3~6개월 이상 보유를 전제로 검증된 참고 지표*이며, 며칠~몇 주 내 "
        "단기 반등을 노리는 용도는 아닙니다.",
        "",
    ]

    for r in new_signals:
        pct_chg = r.get("pct_chg", 0.0)
        summary = r.get("business_summary", "").strip()
        lines.append(f"• *{r['symb']}* ({r['name']}) - {r['verdict']}, {pct_chg:+.2f}%")
        if summary:
            lines.append(f"  {summary}")
    lines.append("")

    # 이번 알림에 실제로 등장한 세부신호만 골라서 설명 (없는 건 생략해서 메시지 간결하게)
    present_keys = []
    for r in new_signals:
        for key in r.get("detected", {}):
            if r["detected"].get(key) and key not in present_keys:
                present_keys.append(key)

    lines.append("📋 *왜 이 종목들이 걸렸나* (판단 근거)")
    lines.append(f"오늘 시장 국면: {regime}. {regime_note}")
    for key in present_keys:
        name, explain = _SIGNAL_EXPLAINS.get(key, (key, ""))
        if explain:
            lines.append(f"· {name}: {explain}")

    return "\n".join(lines)


def load_notified() -> dict:
    if NOTIFIED_PATH.exists():
        with open(NOTIFIED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_notified(notified: dict) -> None:
    with open(NOTIFIED_PATH, "w", encoding="utf-8") as f:
        json.dump(notified, f, ensure_ascii=False, indent=2)


def filter_unnotified(new_signals: list[dict], today: str, notified: dict) -> list[dict]:
    already = set(notified.get(today, []))
    return [r for r in new_signals if r["symb"] not in already]


def mark_notified(notified: dict, today: str, symbs: list[str]) -> dict:
    notified.setdefault(today, [])
    for s in symbs:
        if s not in notified[today]:
            notified[today].append(s)
    return notified

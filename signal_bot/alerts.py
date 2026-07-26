"""상태 변화 감지(어제 미만 -> 오늘 이상) + 중복 알림 방지 (PROJECT_PLAN.md 섹션 4)."""

import json
from pathlib import Path

DATA_DIR = Path("signal_bot/data")
NOTIFIED_PATH = DATA_DIR / "notified.json"

STRONG_BUY_THRESHOLD = 70


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


def format_alert_message(new_signals: list[dict], today: str) -> str:
    regime = new_signals[0].get("market_regime", "판정불가") if new_signals else "판정불가"
    regime_note = {
        "상승장": "지금은 상승장 국면입니다. 과거 검증상 이런 신호가 상대적으로 더 잘 맞았던 편입니다.",
        "횡보장": "지금은 횡보장 국면입니다. 과거 검증상 눌림목 신호가 특히 잘 맞았던 국면입니다.",
        "하락장": "지금은 시장 전체 하락 국면입니다. 신규 진입은 신중하게 판단하세요.",
        "판정불가": "시장 국면 판정에 필요한 데이터가 부족합니다.",
    }.get(regime, "")

    lines = [f"📈 *KIS 매수신호 알림* ({today})", ""]
    for r in new_signals:
        lines.append(f"• *{r['symb']}* ({r['category']}) - {r['score']}점")
        lines.append(f"  현재가 ${r['close']}  |  {r['signals']}")
    lines += [
        "",
        f"🌡️ 오늘 시장 국면: {regime}. {regime_note}",
        "",
        "⚠️ 참고: 이 점수는 \"사면 오른다\"는 보장이 아닙니다. 자체 검증 결과 "
        "5~20일 단기 반등 기준으로는 뚜렷한 우위를 찾지 못했고, 대신 "
        "3~6개월 이상 보유했을 때 거래비용을 반영하고도 통계적으로 유의미한 "
        "우위가 확인됐습니다(과거 12년 중 11년 플러스). 최악의 하락장 타이밍은 "
        "피하게 도와주는 참고 지표로 활용하시고, 최종 매수 판단과 보유기간은 "
        "직접 결정하세요.",
    ]
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

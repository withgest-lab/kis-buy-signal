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
    lines = [f"*KIS 매수신호 알림* ({today})", ""]
    for r in new_signals:
        lines.append(f"• *{r['symb']}* ({r['category']}) - {r['score']}점")
        lines.append(f"  현재가 ${r['close']}  |  {r['signals']}")
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

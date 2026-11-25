"""신규 신호 감지(상태변화) — 화면(signals)의 NEW 표시용.

두 종류의 독립 트리거가 있고, 하나라도 발생하면 그날의 신규 신호 종목이 된다:
  1. MDD 국면 단계 상승(1->2->3단계, 국면별 1회) - mdd_state.json
  2. RSI/MFI 과매도 신규진입 또는 다이버전스 감지(일/주/월 중 하나라도) - indicator_state.json
그날 신규로 잡힌 종목 목록은 notified.json(날짜별)에 남고, export_dashboard가 is_new로 쓴다
(같은 날 다시 실행해도 목록이 유지된다). 텔레그램 알림은 2026-11-25 삭제.
"""

import json
from pathlib import Path

DATA_DIR = Path("signal_bot/data")
NOTIFIED_PATH = DATA_DIR / "notified.json"
MDD_STATE_PATH = DATA_DIR / "mdd_state.json"
INDICATOR_STATE_PATH = DATA_DIR / "indicator_state.json"

_TIMEFRAMES = ["daily", "weekly", "monthly"]
_TIMEFRAME_LABELS = {"daily": "일봉", "weekly": "주봉", "monthly": "월봉"}
_METRICS = ["rsi_oversold", "mfi_oversold", "divergence"]

# 국면 종료(신고가 복귀) 판정 여유값 - depth가 이보다 0에 가까우면 신고가로
# 본다(부동소수 오차 방지).
EPISODE_CLOSE_BAND = -0.005


# ---------------------------------------------------------------------------
# 상태 파일 로드/저장
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_mdd_state() -> dict:
    return _load_json(MDD_STATE_PATH)


def save_mdd_state(state: dict) -> None:
    _save_json(MDD_STATE_PATH, state)


def load_indicator_state() -> dict:
    return _load_json(INDICATOR_STATE_PATH)


def save_indicator_state(state: dict) -> None:
    _save_json(INDICATOR_STATE_PATH, state)


def load_notified() -> dict:
    return _load_json(NOTIFIED_PATH)


def save_notified(notified: dict) -> None:
    _save_json(NOTIFIED_PATH, notified)



# ---------------------------------------------------------------------------
# 트리거 1: MDD 국면 단계 상승
# ---------------------------------------------------------------------------

def find_stage_upgrades(results: list[dict], mdd_state: dict) -> list[dict]:
    """국면 내 단계가 오늘 새로 올라갔으면 이벤트로 반환하고 mdd_state를 갱신.
    신고가 복귀(depth≈0)로 국면이 끝나면 상태를 리셋해 다음 국면에서 재알림 가능."""
    events = []
    for r in results:
        symb = r["symb"]
        depth = r["depth"]
        stage = r["stage"]  # percentiles가 없으면 classify_stage()가 항상 0을 반환
        state = mdd_state.setdefault(symb, {"episode_start_date": None, "last_stage_notified": 0})

        if depth >= EPISODE_CLOSE_BAND:
            if state["episode_start_date"] is not None:
                state["episode_start_date"] = None
                state["last_stage_notified"] = 0
            continue

        if state["episode_start_date"] is None:
            state["episode_start_date"] = r["date"]
            state["last_stage_notified"] = 0

        if stage > state["last_stage_notified"]:
            state["last_stage_notified"] = stage
            events.append({**r, "trigger_reasons": [f"mdd_stage_{stage}"]})

    return events


# ---------------------------------------------------------------------------
# 트리거 2: RSI/MFI 과매도 신규진입 또는 다이버전스 감지 (일/주/월)
# ---------------------------------------------------------------------------

def _empty_indicator_state() -> dict:
    return {tf: {m: False for m in _METRICS} for tf in _TIMEFRAMES}


def find_indicator_events(results: list[dict], indicator_state: dict) -> list[dict]:
    """일/주/월 각 시간대에서 RSI/MFI 과매도가 새로 켜졌거나 다이버전스가
    감지되면(어제는 아니었는데 오늘 그런 상태) 이벤트로 반환, indicator_state 갱신."""
    events = []
    for r in results:
        if "timeframes" not in r:
            continue
        symb = r["symb"]
        prev = indicator_state.setdefault(symb, _empty_indicator_state())
        reasons = []

        for tf in _TIMEFRAMES:
            cur_tf = r["timeframes"].get(tf, {})
            prev_tf = prev.setdefault(tf, {m: False for m in _METRICS})
            for m in _METRICS:
                cur_val = bool(cur_tf.get(m))
                if cur_val and not prev_tf.get(m):
                    reasons.append(f"{_TIMEFRAME_LABELS[tf]}_{m}")
                prev_tf[m] = cur_val

        if reasons:
            events.append({**r, "trigger_reasons": reasons})

    return events


def seed_new_symbols(results: list[dict], mdd_state: dict, indicator_state: dict) -> list[str]:
    """처음 보는 종목(유니버스 확대 직후 등)은 이미 낙폭 국면이거나 과매도 상태여도 "신규 알림"으로
    쏟아지지 않게, 알림 판정 전에 현재 값으로 상태를 조용히 채워 둔다. mdd_state에도 indicator_state에도
    없는 종목만 대상이라 기존 종목의 동작은 그대로다. 반환: 시드한 종목 목록."""
    seeded: list[str] = []
    for r in results:
        symb = r["symb"]
        if symb in mdd_state or symb in indicator_state:
            continue
        in_episode = r["depth"] < EPISODE_CLOSE_BAND
        mdd_state[symb] = {
            "episode_start_date": r["date"] if in_episode else None,
            "last_stage_notified": r["stage"] if in_episode else 0,
        }
        cur = _empty_indicator_state()
        for tf in _TIMEFRAMES:
            now = (r.get("timeframes") or {}).get(tf, {})
            for m in _METRICS:
                cur[tf][m] = bool(now.get(m))
        indicator_state[symb] = cur
        seeded.append(symb)
    return seeded


def find_alert_candidates(results: list[dict], mdd_state: dict, indicator_state: dict) -> list[dict]:
    """두 트리거(MDD 단계상승, RSI/MFI/다이버전스 이벤트)를 합쳐서 종목당 1건으로
    합침(같은 종목이 둘 다 발생하면 trigger_reasons를 합침)."""
    mdd_events = find_stage_upgrades(results, mdd_state)
    ind_events = find_indicator_events(results, indicator_state)

    merged: dict[str, dict] = {}
    for r in mdd_events + ind_events:
        symb = r["symb"]
        if symb in merged:
            merged[symb]["trigger_reasons"] = merged[symb]["trigger_reasons"] + r["trigger_reasons"]
        else:
            merged[symb] = dict(r)
    return list(merged.values())


def filter_unnotified(candidates: list[dict], today: str, notified: dict) -> list[dict]:
    already = set(notified.get(today, []))
    return [r for r in candidates if r["symb"] not in already]


def mark_notified(notified: dict, today: str, symbs: list[str]) -> dict:
    notified.setdefault(today, [])
    for s in symbs:
        if s not in notified[today]:
            notified[today].append(s)
    return notified

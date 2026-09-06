"""알림 트리거 감지(상태변화) + 메시지 포맷 + 발송 중복방지.

두 종류의 독립 트리거가 있고, 하나라도 발생하면 알림 대상이 된다:
  1. MDD 국면 단계 상승(1->2->3단계, 국면별 1회) - mdd_state.json
  2. RSI/MFI 과매도 신규진입 또는 다이버전스 감지(일/주/월 중 하나라도) - indicator_state.json
발송 자체의 당일 중복방지는 notified.json(기존 패턴 그대로)이 담당한다.
"""

import json
from pathlib import Path

from signal_bot.config import MDD_ALERT_LEVELS, MDD_ALERT_TICKERS

DATA_DIR = Path("signal_bot/data")
NOTIFIED_PATH = DATA_DIR / "notified.json"
MDD_STATE_PATH = DATA_DIR / "mdd_state.json"
INDICATOR_STATE_PATH = DATA_DIR / "indicator_state.json"
MDD_ALERT_STATE_PATH = DATA_DIR / "mdd_alert_state.json"

_TIMEFRAMES = ["daily", "weekly", "monthly"]
_TIMEFRAME_LABELS = {"daily": "일봉", "weekly": "주봉", "monthly": "월봉"}
_METRICS = ["rsi_oversold", "mfi_oversold", "divergence"]

_STAGE_LABELS = {1: "1단계(관찰)", 2: "2단계(깊은낙폭)", 3: "3단계(극단)"}

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


def load_mdd_alert_state() -> dict:
    return _load_json(MDD_ALERT_STATE_PATH)


def save_mdd_alert_state(state: dict) -> None:
    _save_json(MDD_ALERT_STATE_PATH, state)


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


# ---------------------------------------------------------------------------
# 트리거 3: 지수성 ETF(MDD_ALERT_TICKERS) 절대 낙폭 구간 경보 - 장기 매수 참고용
#
# 기존 MDD 0~3단계(트리거 1)는 종목별 과거 국면 대비 상대 백분위라서, 시장
# 전체가 "지금 조정인지 약세장인지 폭락 수준인지"를 절대 % 기준으로 바로
# 알기 어렵다. 이 시스템은 원래 "MDD 매수신호"(낙폭이 깊을수록 우량 지수 ETF를
# 장기 보유 목적으로 사는 전략)이므로, SPY/QQQ/DIA/SOXX 같은 지수성 ETF가 정해진
# 낙폭 구간(config.MDD_ALERT_LEVELS)에 새로 도달할 때마다 별도로, 더 눈에 띄게
# 알린다 - 매도 신호가 아니라 매수 참고 경보.
# ---------------------------------------------------------------------------

def _current_episode_start(episodes: list[dict]) -> str | None:
    """baseline의 국면(episode) 목록에서 아직 신고가로 복귀하지 못한(진행중) 국면의
    시작일. 신고가 상태(진행중 국면 없음)면 None."""
    for e in reversed(episodes or []):
        if not e.get("is_complete"):
            return e.get("start_date")
    return None


def find_mdd_level_events(results: list[dict], baseline: dict, mdd_alert_state: dict) -> list[dict]:
    """MDD_ALERT_TICKERS 한정으로 오늘 낙폭이 새 임계값을 넘었으면 이벤트로 반환하고
    mdd_alert_state를 갱신(in-place). 신고가 복귀로 국면이 끝나면 그 종목의 알림
    이력을 초기화해 다음 낙폭 국면에서 같은 구간을 다시 알릴 수 있게 한다."""
    events = []
    by_symb = {r["symb"]: r for r in results}

    for symb in MDD_ALERT_TICKERS:
        r = by_symb.get(symb)
        if r is None:
            continue

        depth = r["depth"]
        episodes = (baseline.get(symb) or {}).get("episodes", [])
        episode_start = _current_episode_start(episodes)
        state = mdd_alert_state.setdefault(symb, {"episode_start": None, "notified_levels": []})

        if episode_start != state["episode_start"]:
            state["episode_start"] = episode_start
            state["notified_levels"] = []

        if episode_start is None:
            continue  # 신고가 상태 - 알릴 낙폭 구간 없음

        # MDD_ALERT_LEVELS는 깊은 것부터 정렬돼 있어, newly_crossed도 깊은 순서 그대로.
        newly_crossed = [
            (threshold, label) for threshold, label in MDD_ALERT_LEVELS
            if depth <= -threshold and threshold not in state["notified_levels"]
        ]
        if newly_crossed:
            state["notified_levels"] = sorted(set(state["notified_levels"]) | {t for t, _ in newly_crossed})
            events.append({**r, "mdd_alert_levels": newly_crossed})

    return events


def format_mdd_level_message(events: list[dict], today: str) -> str:
    """트리거 3 전용 메시지 - 기존 MDD단계/RSI·MFI 알림과 섞지 않고 별도 발송해서
    "지금 시장이 어느 낙폭 구간인지"가 한눈에 눈에 띄게 한다."""
    if not events:
        return ""

    lines = [f"\U0001F6A8 *지수 낙폭 경보(장기 매수 참고)* ({today})", ""]
    for r in events:
        currency = "₩" if r.get("currency") == "KRW" else "$"
        _deepest_threshold, deepest_label = r["mdd_alert_levels"][0]
        lines.append(f"*{r['symb']}* ({r['name']}) - 낙폭 {r['depth'] * 100:.1f}% - {deepest_label}")
        if len(r["mdd_alert_levels"]) > 1:
            passed = ", ".join(f"-{int(t * 100)}%" for t, _ in r["mdd_alert_levels"])
            lines.append(f"  (오늘 새로 도달한 구간: {passed})")
        lines.append(f"  {currency}{r['close']:,.2f} ({r['pct_chg']:+.2f}%)")
        lines.append("")

    lines.append("_장기 매수 판단 참고용 경보입니다 - 실제 매매는 사용자가 직접 결정합니다._")
    return "\n".join(lines).rstrip()


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


# ---------------------------------------------------------------------------
# 메시지 포맷 - 종목명/비즈니스요약/MDD/RSI·MFI·다이버전스만 (그 외는 넣지 않음)
# ---------------------------------------------------------------------------

def _fmt_days(days) -> str:
    if days is None:
        return "-"
    years = days / 252
    if years >= 1:
        return f"약 {years:.1f}년"
    return f"약 {days / 21:.1f}개월"


def _format_mdd_block(r: dict) -> list[str]:
    if r.get("percentiles") is None:
        return ["\U0001F4C9 MDD - 베이스라인 데이터 부족(과거 국면 5개 미만)"]

    p = r["percentiles"]
    stage_label = _STAGE_LABELS.get(r["stage"], "신호없음")
    lines = [
        f"\U0001F4C9 MDD {stage_label} · 낙폭 {r['depth'] * 100:.1f}%",
        f"과거 국면 기준 중간값 {p['p50'] * 100:.1f}% / 극단 {p['p10'] * 100:.1f}%",
        f"회복기간 보통 {_fmt_days(p['recovery_days_median'])}, 길면 {_fmt_days(p['recovery_days_max'])}",
    ]
    if r.get("is_record_drawdown"):
        lines.append("⚠️ 사상 최대 낙폭 - 참고할 과거 데이터 없음")
    return lines


def _format_indicator_block(r: dict) -> list[str]:
    lines = ["\U0001F4C8 RSI·MFI (과매도 기준 30/20)"]
    for tf in _TIMEFRAMES:
        t = r.get("timeframes", {}).get(tf, {})
        rsi_v, mfi_v = t.get("rsi"), t.get("mfi")
        rsi_s = "-" if rsi_v is None else f"{rsi_v:.0f}" + ("(과매도)" if t.get("rsi_oversold") else "")
        mfi_s = "-" if mfi_v is None else f"{mfi_v:.0f}" + ("(과매도)" if t.get("mfi_oversold") else "")
        div_s = " · 다이버전스감지" if t.get("divergence") else ""
        lines.append(f"{_TIMEFRAME_LABELS[tf]} RSI {rsi_s} · MFI {mfi_s}{div_s}")
    return lines


def _format_ticker_block(r: dict) -> list[str]:
    currency = "₩" if r.get("currency") == "KRW" else "$"
    pct = r.get("pct_chg", 0.0)
    lines = [f"*{r['symb']}* ({r['name']}) - {currency}{r['close']:,.2f} ({pct:+.2f}%)"]

    summary = (r.get("business_summary") or "").strip()
    if summary:
        lines.append(summary)

    lines.append("")
    lines.extend(_format_mdd_block(r))
    lines.append("")
    lines.extend(_format_indicator_block(r))
    return lines


# 텔레그램 메시지 하나당 최대 4096자 제한 - 여유를 두고 이보다 낮게 잡아서
# 여러 종목이 한꺼번에 걸려도(예: 최초 실행일) 메시지가 잘려서 발송 자체가
# 실패(400 Bad Request)하지 않도록 종목 블록 단위로 여러 메시지로 쪼갠다.
TELEGRAM_MAX_LEN = 3500
_HEADER = "\U0001F4CA *MDD·RSI/MFI 매수참고 알림*"


def format_alert_messages(to_send: list[dict], today: str) -> list[str]:
    """to_send를 종목 블록 단위로 나눠 텔레그램 글자수 제한 안에 들어오는
    여러 메시지로 반환한다(발송은 호출부에서 순서대로 여러 번)."""
    if not to_send:
        return []

    header = f"{_HEADER} ({today})"
    divider = "─" * 16  # 종목 블록 사이 구분선(가독성용)
    messages: list[str] = []
    current: list[str] = [header, ""]

    for i, r in enumerate(to_send):
        block = _format_ticker_block(r)
        block_text = "\n".join(block)
        if len(current) > 2 and len("\n".join(current)) + len(block_text) + 1 > TELEGRAM_MAX_LEN:
            messages.append("\n".join(current).rstrip())
            current = [f"{header} (이어서)", ""]
        elif len(current) > 2:
            current.append(divider)
            current.append("")
        current.extend(block)
        current.append("")

    if len(current) > 2:
        messages.append("\n".join(current).rstrip())

    return messages


def format_alert_message(to_send: list[dict], today: str) -> str:
    """단일 문자열 버전(테스트/디버그용) - 실제 발송은 format_alert_messages()를
    써서 글자수 제한을 넘지 않게 여러 건으로 나눠 보낸다."""
    return "\n\n".join(format_alert_messages(to_send, today))

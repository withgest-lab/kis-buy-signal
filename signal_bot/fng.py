"""CNN 공포·탐욕 지수(Fear & Greed, 0~100) — 매매전략 RSI·MFI 칸에 함께 그리는 docs/fng.json.

    uv run python -m signal_bot.fng          # 공개 데이터셋에서 받아 이력·docs/fng.json 갱신

출처 = 공개 데이터셋 JakeLaoyu/fear-greed-index(MIT, 2011~, 평일 자동 갱신 — CNN 보관본 + CNN 공식 그래프 데이터).
CNN 사이트를 직접 긁지 않는다(브라우저 흉내 헤더가 필요한 비공식 주소라 막히기 쉬움).
이력 = signal_bot/data/fng_history.json(저장소 커밋): [날짜, 점수]. 받은 값으로 같은 날짜를 덮어쓰고 새 날짜를 붙인다 —
받기에 실패하면 저장 이력 그대로 발행(stale=true), 이력이 바뀌면 daily.yml 상태 커밋에 함께 올라간다.
화면 구분(CNN과 같은 경계): 0~25 극단적 공포 · 25~45 공포 · 45~55 중립 · 55~75 탐욕 · 75~100 극단적 탐욕.
"""

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/JakeLaoyu/fear-greed-index/main/data/fear-greed.json"
SOURCE_NAME = "CNN Fear & Greed Index — 이력: github.com/JakeLaoyu/fear-greed-index (MIT)"
OUTPUT_PATH = Path("docs/fng.json")
HISTORY_PATH = Path(__file__).parent / "data" / "fng_history.json"
UA = {"User-Agent": "kis-buy-signal (github actions)"}


def _get(url: str, timeout: int = 30) -> bytes:
    last = None
    for _ in range(2):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            last = e
    raise RuntimeError(last)


def parse_rows(payload: dict) -> list[list]:
    """공개 데이터셋 {"data": [[날짜, 점수, 등급번호], ...]} → 날짜순 [[날짜, 점수(소수 1자리)]]. 형식이 다르면 예외."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("공포·탐욕 데이터 형식이 다릅니다(data 배열 없음)")
    out = {}
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 2:
            continue
        d, v = str(r[0])[:10], r[1]
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if len(d) == 10 and d[4] == "-" and 0 <= v <= 100:
            out[d] = round(v, 1)
    if len(out) < 100:
        raise ValueError(f"공포·탐욕 데이터가 너무 적습니다({len(out)}줄)")
    return [[d, out[d]] for d in sorted(out)]


def merge(history: list[list], rows: list[list]) -> list[list]:
    """같은 날짜는 새 값으로, 새 날짜는 추가(이력에만 있던 옛 날짜는 그대로 둔다)."""
    m = {d: v for d, v in history}
    m.update({d: v for d, v in rows})
    return [[d, m[d]] for d in sorted(m)]


def _load_history() -> list[list]:
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))["data"]
    except Exception:
        return []


def _save_history(data: list[list]) -> None:
    HISTORY_PATH.write_text(json.dumps({"source": SOURCE_NAME, "data": data}, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")


def write(path: Path = OUTPUT_PATH, fetch=None) -> tuple[int, bool]:
    """docs/fng.json을 쓰고 (날짜 수, 새로 받지 못해 저장 이력만 썼는지)를 돌려준다."""
    history = _load_history()
    stale = False
    try:
        payload = fetch() if fetch else json.loads(_get(SOURCE_URL))
        data = merge(history, parse_rows(payload))
        if data != history:
            _save_history(data)
    except Exception as e:
        if not history:
            raise
        data, stale = history, True
        print(f"::warning::공포·탐욕 지수 받기 실패({e}) — 저장된 이력으로 발행(마지막 {history[-1][0]})")
    out = {"name": "CNN 공포·탐욕 지수", "source": SOURCE_NAME, "fetched": date.today().isoformat(),
           "stale": stale, "data": data}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(data), stale


if __name__ == "__main__":
    try:
        n, stale = write()
        print(f"{OUTPUT_PATH}: {n}일{' (저장 이력)' if stale else ''}")
    except Exception as e:   # 이력도 없고 받기도 실패 — 화면은 공포지수 없이 그린다(실행 전체를 멈추지 않음)
        print(f"::warning::공포·탐욕 지수 발행 실패({e}) — fng.json 없이 진행")
        sys.exit(0)

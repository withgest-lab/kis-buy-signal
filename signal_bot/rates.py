"""연준 기준금리(FOMC 목표 범위) — 매매전략 가격 그래프 아래 '금리 띠'용 docs/rates.json.

    uv run python -m signal_bot.rates            # FRED에서 받아 저장 이력·docs/rates.json 갱신(시험용)

FRED 공개 CSV(키 불필요)에서 받는다: 1982-09-27~2008-12-15는 단일 목표치(DFEDTAR), 2008-12-16부터는 목표 범위
상단(DFEDTARU)·하단(DFEDTARL). 실효금리(DFF)가 아니라 FOMC가 정한 값이라 0.25·0.5·0.75%p 계단이 그대로 보인다.
금리가 바뀐 날만 남겨([날짜, 상단, 하단|null]) 1982년부터 약 190줄. 화면이 날짜별 값·1년 변화를 계산해 그린다.

GitHub 서버에서는 FRED가 자주 시간 초과된다(2026-11-21 실제 발생). 금리는 FOMC 때만 바뀌므로 이력을
signal_bot/data/fed_steps.json(저장소에 커밋, daily.yml이 갱신분을 커밋)에 두고, FRED는 재시도해 받되 실패하면
저장 이력으로 발행한다(stale=true). 저장 이력도 없을 때만 예외 → 호출부는 경고만 남기고 띠 없이 발행.
"""

import csv
import io
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
OUTPUT_PATH = Path("docs/rates.json")
SEED_PATH = Path(__file__).parent / "data" / "fed_steps.json"
RANGE_START = "2008-12-16"      # 이날부터 목표 '범위'(상단·하단)
TRIES, TIMEOUT = 3, 30


def _series(sid: str) -> list[tuple[str, float]]:
    last = None
    for k in range(TRIES):
        try:
            req = urllib.request.Request(FRED_CSV.format(sid), headers={"User-Agent": "Mozilla/5.0 (kis-buy-signal)"})
            text = urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8")
            out = []
            for row in csv.DictReader(io.StringIO(text)):
                v = row.get(sid, "").strip()
                if v and v != ".":
                    out.append((row["observation_date"], round(float(v), 4)))
            if out:
                return out
            last = RuntimeError(f"FRED {sid}: 값이 없습니다")
        except Exception as e:     # 시간 초과·일시 오류는 잠깐 쉬고 다시
            last = e
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"FRED {sid}: {last}")


def fed_steps() -> list[list]:
    """금리가 바뀐 날만: [날짜, 상단, 하단(2008-12-16 전은 None)]."""
    old = [(d, v, None) for d, v in _series("DFEDTAR") if d < RANGE_START]
    lower = dict(_series("DFEDTARL"))
    new = [(d, v, lower.get(d)) for d, v in _series("DFEDTARU") if d >= RANGE_START]
    steps: list[list] = []
    for d, up, lo in old + new:
        if not steps or steps[-1][1] != up or steps[-1][2] != lo:
            steps.append([d, up, lo])
    return steps


def _load_seed() -> list[list] | None:
    try:
        steps = json.loads(SEED_PATH.read_text(encoding="utf-8"))["steps"]
        return steps if steps else None
    except Exception:
        return None


def write(path: Path = OUTPUT_PATH) -> tuple[int, bool]:
    """docs/rates.json을 쓰고 (바뀐 날 수, 저장 이력을 썼는지)를 돌려준다."""
    stale = False
    try:
        steps = fed_steps()
        if steps != _load_seed():
            SEED_PATH.write_text(json.dumps({"source": "FRED DFEDTAR·DFEDTARU·DFEDTARL", "steps": steps}, ensure_ascii=False),
                                 encoding="utf-8")
    except Exception as e:
        steps = _load_seed()
        if not steps:
            raise
        stale = True
        print(f"::warning::FRED 받기 실패({e}) — 저장된 금리 이력으로 발행(마지막 결정 {steps[-1][0]})")
    data = {"name": "미국 연준 기준금리(FOMC 목표 범위)", "source": "FRED DFEDTAR·DFEDTARU·DFEDTARL",
            "fetched": date.today().isoformat(), "stale": stale, "steps": steps}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return len(steps), stale


if __name__ == "__main__":
    n, stale = write()
    print(f"{OUTPUT_PATH}: 금리가 바뀐 날 {n}개{' (저장 이력)' if stale else ''}")

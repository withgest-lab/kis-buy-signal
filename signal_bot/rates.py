"""연준 기준금리(FOMC 목표 범위) — 매매전략 가격 그래프 아래 '금리 띠'용 docs/rates.json.

    uv run python -m signal_bot.rates            # docs/rates.json만 다시 쓰기(시험용)

FRED 공개 CSV(키 불필요)에서 받는다: 1982-09-27~2008-12-15는 단일 목표치(DFEDTAR), 2008-12-16부터는 목표 범위
상단(DFEDTARU)·하단(DFEDTARL). 실효금리(DFF)가 아니라 FOMC가 정한 값이라 0.25·0.5·0.75%p 계단이 그대로 보인다.
금리가 바뀐 날만 남겨([날짜, 상단, 하단|null]) 1982년부터 약 100줄. 화면이 날짜별 값·1년 변화를 계산해 그린다.
받기에 실패하면 예외를 올리고, 호출부(export_dashboard)는 경고만 남긴 채 나머지 데이터를 그대로 발행한다(띠만 빠짐).
"""

import csv
import io
import json
import urllib.request
from pathlib import Path

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
OUTPUT_PATH = Path("docs/rates.json")
RANGE_START = "2008-12-16"      # 이날부터 목표 '범위'(상단·하단)


def _series(sid: str) -> list[tuple[str, float]]:
    req = urllib.request.Request(FRED_CSV.format(sid), headers={"User-Agent": "kis-buy-signal/1.0"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        v = row.get(sid, "").strip()
        if v and v != ".":
            out.append((row["observation_date"], round(float(v), 4)))
    if not out:
        raise RuntimeError(f"FRED {sid}: 값이 없습니다")
    return out


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


def write(path: Path = OUTPUT_PATH, as_of: str | None = None) -> int:
    steps = fed_steps()
    data = {"name": "미국 연준 기준금리(FOMC 목표 범위)", "source": "FRED DFEDTAR·DFEDTARU·DFEDTARL",
            "as_of": as_of or steps[-1][0], "steps": steps}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return len(steps)


if __name__ == "__main__":
    n = write()
    print(f"{OUTPUT_PATH}: 금리가 바뀐 날 {n}개")

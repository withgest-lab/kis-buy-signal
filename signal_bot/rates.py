"""연준 기준금리(FOMC 목표 범위) — 매매전략 가격 그래프 아래 '금리 띠'용 docs/rates.json.

    uv run python -m signal_bot.rates            # 뉴욕 연은에서 새 결정만 받아 이력·docs/rates.json 갱신
    uv run python -m signal_bot.rates --fred     # FRED에서 1982년부터 이력 전체를 다시 만들기(로컬용)

이력 = signal_bot/data/fed_steps.json(저장소에 커밋): 금리가 바뀐 날만 [날짜, 상단, 하단|null], 1982년부터 약 190줄.
FOMC가 정한 목표 범위(실효금리 아님)라 0.25·0.5·0.75%p 계단이 그대로 보인다. 처음 이력은 FRED(1982-09-27~2008-12-15
단일 목표치 DFEDTAR, 2008-12-16부터 범위 DFEDTARU·DFEDTARL)로 만들었다.
매일 실행은 뉴욕 연은 공식 API(EFFR의 targetRateFrom/To, 요청 1번·1초 안)로 최근 120일을 받아 이력 뒤에 새 결정만 붙인다 —
GitHub 서버에서는 FRED가 계속 시간 초과돼(2026-11-21 두 번) 재시도만으로 실행이 몇 분 늦어졌다. 받기에 실패하면 저장 이력
그대로 발행(stale=true)하고, 이력이 바뀌면 daily.yml 상태 커밋에 함께 올라간다. 화면이 날짜별 값·1년 변화를 계산해 그린다.
"""

import csv
import io
import json
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
NYFED = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate={}&endDate={}"
OUTPUT_PATH = Path("docs/rates.json")
SEED_PATH = Path(__file__).parent / "data" / "fed_steps.json"
RANGE_START = "2008-12-16"      # 이날부터 목표 '범위'(상단·하단)
UA = {"User-Agent": "Mozilla/5.0 (kis-buy-signal)"}


def _get(url: str, timeout: int = 20) -> bytes:
    last = None
    for _ in range(2):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
        except Exception as e:
            last = e
    raise RuntimeError(last)


def _merge(steps: list[list], rows: list[tuple[str, float, float | None]]) -> list[list]:
    """날짜순 (날짜, 상단, 하단) 관측을 이력 뒤에 붙인다 — 이력 마지막 날 이후에 값이 바뀐 날만."""
    out = [list(s) for s in steps]
    for d, up, lo in sorted(rows):
        if out and d <= out[-1][0]:
            continue
        if not out or out[-1][1] != up or out[-1][2] != lo:
            out.append([d, up, lo])
    return out


def nyfed_rows(days: int = 120) -> list[tuple[str, float, float]]:
    end = date.today()
    data = json.loads(_get(NYFED.format((end - timedelta(days=days)).isoformat(), end.isoformat())))
    rows = [(r["effectiveDate"], round(float(r["targetRateTo"]), 4), round(float(r["targetRateFrom"]), 4))
            for r in data.get("refRates", []) if r.get("targetRateTo") is not None]
    if not rows:
        raise RuntimeError("뉴욕 연은 응답에 목표 범위가 없습니다")
    return rows


def fred_steps() -> list[list]:
    """FRED로 1982년부터 이력 전체(로컬에서 처음 만들거나 다시 맞출 때)."""
    def series(sid):
        text = _get(FRED_CSV.format(sid), timeout=60).decode("utf-8")
        return [(r["observation_date"], round(float(r[sid]), 4)) for r in csv.DictReader(io.StringIO(text))
                if r.get(sid, "").strip() not in ("", ".")]
    old = [(d, v, None) for d, v in series("DFEDTAR") if d < RANGE_START]
    lower = dict(series("DFEDTARL"))
    new = [(d, v, lower.get(d)) for d, v in series("DFEDTARU") if d >= RANGE_START]
    return _merge([], old + new)


def _load_seed() -> list[list]:
    try:
        return json.loads(SEED_PATH.read_text(encoding="utf-8"))["steps"]
    except Exception:
        return []


def _save_seed(steps: list[list]) -> None:
    SEED_PATH.write_text(json.dumps({"source": "FRED DFEDTAR·DFEDTARU·DFEDTARL + 뉴욕 연은 EFFR 목표 범위", "steps": steps},
                                    ensure_ascii=False), encoding="utf-8")


def write(path: Path = OUTPUT_PATH, full: bool = False) -> tuple[int, bool]:
    """docs/rates.json을 쓰고 (바뀐 날 수, 새로 받지 못해 저장 이력만 썼는지)를 돌려준다."""
    seed = _load_seed()
    stale = False
    try:
        steps = fred_steps() if full or not seed else _merge(seed, nyfed_rows())
        if steps != seed:
            _save_seed(steps)
    except Exception as e:
        if not seed:
            raise
        steps, stale = seed, True
        print(f"::warning::기준금리 받기 실패({e}) — 저장된 이력으로 발행(마지막 결정 {seed[-1][0]})")
    data = {"name": "미국 연준 기준금리(FOMC 목표 범위)", "source": "FRED·뉴욕 연은",
            "fetched": date.today().isoformat(), "stale": stale, "steps": steps}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return len(steps), stale


if __name__ == "__main__":
    n, stale = write(full="--fred" in sys.argv)
    print(f"{OUTPUT_PATH}: 금리가 바뀐 날 {n}개{' (저장 이력)' if stale else ''}")

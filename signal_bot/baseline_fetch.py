"""MDD 계산용 20년치 일봉 베이스라인 확보 (약 20년, 상장이 짧으면 있는 만큼).

운영용 일일 파이프라인이 쓰는 signal_bot/data/*.csv(250거래일치)와는 완전히
분리된 signal_bot/data/baseline/ 폴더에 저장한다. 대상은 전체 유니버스가
아니라 config.TICKERS(지수·ETF·시가총액 상위·한국·일본·비트코인)만.

staleness 체크(universe_source.py의 캐시 패턴과 동일) - 매일 워크플로우에서
호출되지만 30일 이내면 즉시 종료하고, 재수집이 필요할 때만 실제 API 호출.
재수집 완료 시 mdd.build_all_baselines()까지 이어서 호출해 mdd_baseline.json도
함께 갱신한다(이 20년치 데이터는 timeframe_signals.py의 주/월봉 워밍업에도
재사용됨 - 별도 수집 불필요).
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from signal_bot import crypto_client as cc
from signal_bot import kis_client as kc
from signal_bot import kis_client_kr as kc_kr
from signal_bot import mdd
from signal_bot.config import CRYPTO_SPOT, TICKERS, is_jp, is_kr, kr_kind

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

DATA_DIR = Path(__file__).parent / "data"
BASELINE_DIR = DATA_DIR / "baseline"
META_PATH = DATA_DIR / "baseline_meta.json"

DAILY_MIN_ROWS_LONG = 15000  # 넉넉한 상한(약 60년) - 실제로는 상장일 이전 데이터가
                              # 없으면 _fetch_pages가 먼저 멈추므로 사실상 "가능한 최대"
REFRESH_INTERVAL_DAYS = 30


def _load_meta() -> dict | None:
    if not META_PATH.exists():
        return None
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_meta(meta: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def needs_full_refresh(force: bool = False) -> bool:
    """모든 종목을 처음부터 다시 받아야 하는지 - force, 메타 없음, 베이스라인 CSV가 하나도 없음, 마지막 전체 갱신 후 30일 경과."""
    if force:
        return True
    meta = _load_meta()
    if meta is None:
        return True
    # signal_bot/data/baseline/은 .gitignore 대상이라 커밋되지 않는데, meta.json은
    # 커밋된다 - CI처럼 매번 새 파일시스템으로 시작하는 환경에서는 "meta상 날짜는
    # 최신"인데 실제 CSV 파일은 하나도 없는 상태가 될 수 있다. 이 경우 날짜만 보고
    # 재수집을 건너뛰면 이후 모든 계산이 베이스라인 없이(최근 데이터만으로) 진행되는
    # 조용한 데이터 손상으로 이어지므로, 파일이 실제로 있는지도 반드시 함께 확인한다.
    if not any(BASELINE_DIR.glob("*_daily.csv")):
        return True
    updated_at = datetime.strptime(meta["updated_at"], "%Y-%m-%d").date()
    return date.today() - updated_at > timedelta(days=REFRESH_INTERVAL_DAYS)


# 한국 개별종목·ETF 베이스라인 시작일. KIS 국내 일봉은 1990년대 종가가 자본 변동에 대해 수정주가로 일관되지 않는
# 종목이 있다(예: 기아 1990년 종가 347,656원 vs 2000년 4,000~8,000원) - 이 값이 "사상 최고가"가 되면 낙폭이 실제와
# 크게 다르게(-66%) 나오고 낙폭 국면 통계도 왜곡된다. 업종지수(kr_kind=index)는 실제 지수라 그대로 둔다.
KR_HISTORY_START = "2000-01-01"

# 일본(TSE) 종목 베이스라인 시작일. KIS 해외 일봉의 도쿄 종목은 2014-03 이전 값이 실제 가격이 아니다(2009년 0.1엔에서
# 매끄럽게 올라가는 값 - 야후 수정주가와 비교하면 2012년 비율 0.2~0.4, 2014-03-27부터 일정). 그대로 두면 가짜 상승 구간이
# 낙폭 국면·백분위와 과거 결과(1년 수익률)를 부풀린다(2026-11-08 야후 대조로 확인).
JP_HISTORY_START = "2014-04-01"

# KIS 과거 종가에 남은 수정주가 오류: (날짜, 배수) - 그날 이전 가격(시가·고가·저가·종가)에 배수를 곱해 이어 붙인다.
# ISRG: 2017-10-06 3:1 분할이 과거에 두 번 적용돼 그 전 값이 실제의 1/3(그날 +198%로 보임, 야후는 -0.5%).
# 이미 고쳐져 있으면(그날 하루 변화가 배수와 5% 넘게 다르면) 건드리지 않는다 - 매일 돌아도 한 번만 적용된다.
PRICE_BREAKS = {"ISRG": [("2017-10-06", 3.0)]}
SPLIT_FACTORS = (2, 3, 4, 5, 10, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10)


def _history_start(category: str, symb: str) -> str | None:
    if is_kr(category) and kr_kind(symb) == "item":
        return KR_HISTORY_START
    if is_jp(category):
        return JP_HISTORY_START
    return None


def trim_history() -> list[str]:
    """한국 개별종목·ETF는 KR_HISTORY_START, 일본 종목은 JP_HISTORY_START 이후로 베이스라인 CSV를 자른다
    (이미 잘려 있으면 건드리지 않음). 바뀐 종목 목록 반환."""
    changed = []
    for category, symb in TICKERS:
        start = _history_start(category, symb)
        path = BASELINE_DIR / f"{symb}_daily.csv"
        if start is None or not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        if df.empty or df["date"].min() >= pd.Timestamp(start):
            continue
        df[df["date"] >= pd.Timestamp(start)].to_csv(path, index=False)
        changed.append(symb)
    return changed


def repair_price_breaks() -> list[str]:
    """PRICE_BREAKS의 수정주가 오류를 베이스라인 CSV에서 고친다(아직 남아 있을 때만). 바뀐 종목 목록 반환."""
    changed = []
    for symb, fixes in PRICE_BREAKS.items():
        path = BASELINE_DIR / f"{symb}_daily.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        fixed = False
        for day, factor in fixes:
            before = df["date"] < pd.Timestamp(day)
            if not before.any() or before.all():
                continue
            jump = df.loc[~before, "close"].iloc[0] / df.loc[before, "close"].iloc[-1]
            if abs(jump / factor - 1) > 0.05:
                continue
            for col in ("open", "high", "low", "close"):
                if col in df:
                    df.loc[before, col] *= factor
            if "volume" in df:
                df.loc[before, "volume"] /= factor
            fixed = True
        if fixed:
            df.to_csv(path, index=False)
            changed.append(symb)
    return changed


def split_like_jumps() -> dict[str, list[tuple[str, float]]]:
    """베이스라인에 남은 '분할 배수와 거의 같은 하루 변화'(±2%) - 고치지 않고 로그로만 알린다(PRICE_BREAKS 후보).
    대형주가 하루에 정확히 2배·1/2이 되는 일은 드물어서, 여기 걸리면 대개 수정주가 오류다. 비트코인은 제외."""
    out: dict = {}
    for category, symb in TICKERS:
        path = BASELINE_DIR / f"{symb}_daily.csv"
        if symb in CRYPTO_SPOT or not path.exists():
            continue
        df = pd.read_csv(path, parse_dates=["date"], usecols=["date", "close"])
        r = (df["close"] / df["close"].shift(1)).to_numpy()
        hits = [(df["date"].iloc[i].strftime("%Y-%m-%d"), round(float(r[i]), 3)) for i in range(1, len(r))
                if any(abs(r[i] / f - 1) < 0.02 for f in SPLIT_FACTORS)]
        if hits:
            out[symb] = hits
    return out


def fix_history() -> list[str]:
    """시작일 자르기 + 수정주가 오류 고치기. 바뀐 종목이 있으면 호출부가 MDD 베이스라인을 다시 계산한다."""
    trimmed, repaired = trim_history(), repair_price_breaks()
    if trimmed:
        print(f"과거 시작일 보정(한국 {KR_HISTORY_START}·일본 {JP_HISTORY_START} 이후) {len(trimmed)}종목: {trimmed}")
    if repaired:
        print(f"수정주가 오류 보정 {len(repaired)}종목: {repaired}")
    jumps = split_like_jumps()
    if jumps:
        print(f"⚠ 분할 배수와 같은 하루 변화가 남은 종목(확인 필요, PRICE_BREAKS 후보): {jumps}")
    return sorted(set(trimmed + repaired))


def missing_symbols() -> list[tuple[str, str]]:
    """유니버스에는 있는데 베이스라인 CSV가 없는 종목(유니버스 확대로 새로 들어왔거나 지난번 수집에 실패한 종목).
    종목 구성이 바뀔 때 전체를 다시 받지 않고 이 종목들만 증분 수집한다(103종목 전체는 10분 이상 걸림)."""
    return [(c, s) for c, s in TICKERS if not (BASELINE_DIR / f"{s}_daily.csv").exists()]


# 주식 분할·병합이 있으면 KIS는 과거 종가를 수정주가로 바꿔 주는데, 30일마다 받는 베이스라인 CSV는 옛 값 그대로라
# 매일 받는 운영용 일봉과 이어 붙인 곳에서 가격이 몇 배로 튄다(2026-08 SOXX 3:1 분할 → 다음 전체 갱신까지 고점이 3배로 잡혀
# 낙폭 -50%·3단계로 잘못 표시). 겹치는 날의 종가 비율이 이만큼 넘게 어긋나면 그 종목 베이스라인만 다시 받는다.
# 배당 수정(ETF 0.2~1%)은 무시하고 분할·병합(2배, 3배, 1/10 …)만 잡는 폭.
SPLIT_MISMATCH_TOL = 0.05


def split_mismatch_symbols(tol: float = SPLIT_MISMATCH_TOL) -> list[tuple[str, str]]:
    """베이스라인 CSV와 운영용 일봉이 겹치는 날의 종가 비율(중앙값)이 1에서 tol 넘게 벗어난 종목 = 분할·병합 뒤 과거가 바뀐 종목."""
    out = []
    for category, symb in TICKERS:
        base_path, recent_path = BASELINE_DIR / f"{symb}_daily.csv", DATA_DIR / f"{symb}_daily.csv"
        if not base_path.exists() or not recent_path.exists():
            continue
        base = pd.read_csv(base_path, parse_dates=["date"], usecols=["date", "close"])
        recent = pd.read_csv(recent_path, parse_dates=["date"], usecols=["date", "close"])
        both = base.merge(recent, on="date", suffixes=("_base", "_recent"))
        both = both[both["close_base"] > 0]
        if both.empty:
            continue
        ratio = float((both["close_recent"] / both["close_base"]).median())
        if abs(ratio - 1) > tol:
            out.append((category, symb))
    return out


def is_stale(force: bool = False) -> bool:
    return needs_full_refresh(force) or bool(missing_symbols()) or bool(split_mismatch_symbols())


def _fetch_one(category: str, symb: str) -> dict:
    try:
        if symb in CRYPTO_SPOT:
            daily = cc.fetch_ohlcv_crypto(CRYPTO_SPOT[symb], min_rows=DAILY_MIN_ROWS_LONG)
        elif is_kr(category):
            daily = kc_kr.fetch_ohlcv_kr(symb, kind=kr_kind(symb), min_rows=DAILY_MIN_ROWS_LONG)
        else:
            daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS_LONG)
        daily.to_csv(BASELINE_DIR / f"{symb}_daily.csv", index=False)
        return {
            "category": category, "symb": symb, "ok": True,
            "daily_rows": len(daily), "earliest": daily["date"].min().strftime("%Y-%m-%d"),
            "error": None,
        }
    except Exception as e:
        return {
            "category": category, "symb": symb, "ok": False,
            "daily_rows": 0, "earliest": None, "error": str(e),
        }


def main(force: bool = False) -> None:
    full = needs_full_refresh(force)
    if full:
        targets = list(TICKERS)
    else:
        targets = missing_symbols()
        split = split_mismatch_symbols()
        if split:
            print(f"분할·병합으로 과거 종가가 바뀐 종목 {len(split)}개 베이스라인 다시 수집: {[s for _c, s in split]}")
        targets += [t for t in split if t not in targets]
    if not targets:
        if not fix_history():
            print(f"베이스라인이 최신(30일 이내)이라 재수집 생략 (마지막 갱신: {_load_meta()['updated_at']})")
            return
        print("\nMDD 베이스라인(낙폭국면/백분위) 다시 계산 중...")
        baseline = mdd.build_all_baselines(TICKERS)
        insufficient = [s for s, b in baseline.items() if b.get("insufficient_data")]
        print(f"완료: {len(baseline)}종목 (데이터 부족 {len(insufficient)}개: {insufficient})")
        return
    if not full:
        print(f"새로 들어왔거나 이전에 실패했거나 분할된 {len(targets)}종목만 증분 수집: {[s for _c, s in targets]}")

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    kc.ensure_auth()
    kc.MAX_PAGES = 200  # 15000행(약 60년) 확보용 상한

    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in targets}
        for future in as_completed(futures):
            results.append(future.result())
            done = len(results)
            if done % 20 == 0 or done == len(targets):
                print(f"진행: {done}/{len(targets)}", flush=True)

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    print(f"\n{len(ok)}/{len(results)} 성공")
    if ok:
        earliest_dates = sorted(r["earliest"] for r in ok)
        print(f"가장 긴 종목: {earliest_dates[0]}부터, 가장 짧은 종목: {earliest_dates[-1]}부터")
    if fail:
        print(f"실패 {len(fail)}종목: {[r['symb'] for r in fail]}")

    fix_history()

    # 증분 수집이면 마지막 "전체 갱신일"은 그대로 둔다(그래야 기존 종목의 30일 주기 갱신이 밀리지 않는다).
    prev_meta = _load_meta()
    _save_meta({
        "updated_at": date.today().strftime("%Y-%m-%d") if full or not prev_meta else prev_meta["updated_at"],
        "symbols": [symb for _c, symb in TICKERS],
    })

    print("\nMDD 베이스라인(낙폭국면/백분위) 계산 중...")
    baseline = mdd.build_all_baselines(TICKERS)
    insufficient = [s for s, b in baseline.items() if b.get("insufficient_data")]
    print(f"완료: {len(baseline)}종목 (데이터 부족 {len(insufficient)}개: {insufficient})")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)

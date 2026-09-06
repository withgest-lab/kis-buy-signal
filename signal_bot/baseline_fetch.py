"""MDD 계산용 20년치 일봉 베이스라인 확보 (약 20년, 상장이 짧으면 있는 만큼).

운영용 일일 파이프라인이 쓰는 signal_bot/data/*.csv(250거래일치)와는 완전히
분리된 signal_bot/data/baseline/ 폴더에 저장한다. 대상은 전체 유니버스가
아니라 CURATED_ETFS + 시가총액 상위 종목 + 한국 종목(약 75~78개)만.

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

from signal_bot import kis_client as kc
from signal_bot import kis_client_kr as kc_kr
from signal_bot import mdd
from signal_bot.config import TICKERS, is_kr, kr_kind

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


def is_stale(force: bool = False) -> bool:
    if force:
        return True
    meta = _load_meta()
    if meta is None:
        return True
    if sorted(meta.get("symbols", [])) != sorted(symb for _c, symb in TICKERS):
        return True  # 유니버스 구성이 바뀜(시총 랭킹 변동 등) -> 강제 재수집
    # signal_bot/data/baseline/은 .gitignore 대상이라 커밋되지 않는데, meta.json은
    # 커밋된다 - CI처럼 매번 새 파일시스템으로 시작하는 환경에서는 "meta상 날짜는
    # 최신"인데 실제 CSV 파일은 하나도 없는 상태가 될 수 있다. 이 경우 날짜만 보고
    # 재수집을 건너뛰면 이후 모든 계산이 베이스라인 없이(최근 데이터만으로) 진행되는
    # 조용한 데이터 손상으로 이어지므로, 파일이 실제로 있는지도 반드시 함께 확인한다.
    if not any(BASELINE_DIR.glob("*_daily.csv")):
        return True
    updated_at = datetime.strptime(meta["updated_at"], "%Y-%m-%d").date()
    return date.today() - updated_at > timedelta(days=REFRESH_INTERVAL_DAYS)


def _fetch_one(category: str, symb: str) -> dict:
    try:
        if is_kr(category):
            daily = kc_kr.fetch_ohlcv_kr(symb, kind=kr_kind(category), min_rows=DAILY_MIN_ROWS_LONG)
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
    if not is_stale(force=force):
        print(f"베이스라인이 최신(30일 이내)이라 재수집 생략 (마지막 갱신: {_load_meta()['updated_at']})")
        return

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    kc.ensure_auth()
    kc.MAX_PAGES = 200  # 15000행(약 60년) 확보용 상한

    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in TICKERS}
        for future in as_completed(futures):
            results.append(future.result())
            done = len(results)
            if done % 20 == 0 or done == len(TICKERS):
                print(f"진행: {done}/{len(TICKERS)}", flush=True)

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    print(f"\n{len(ok)}/{len(results)} 성공")
    if ok:
        earliest_dates = sorted(r["earliest"] for r in ok)
        print(f"가장 긴 종목: {earliest_dates[0]}부터, 가장 짧은 종목: {earliest_dates[-1]}부터")
    if fail:
        print(f"실패 {len(fail)}종목: {[r['symb'] for r in fail]}")

    _save_meta({
        "updated_at": date.today().strftime("%Y-%m-%d"),
        "symbols": [symb for _c, symb in TICKERS],
    })

    print("\nMDD 베이스라인(낙폭국면/백분위) 계산 중...")
    baseline = mdd.build_all_baselines(TICKERS)
    insufficient = [s for s, b in baseline.items() if b.get("insufficient_data")]
    print(f"완료: {len(baseline)}종목 (데이터 부족 {len(insufficient)}개: {insufficient})")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)

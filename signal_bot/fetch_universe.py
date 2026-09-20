"""타겟 종목 전체 일봉 데이터 조회 후 signal_bot/data/에 저장.

MDD는 일봉 종가만 필요하고 주/월봉 RSI/MFI/다이버전스는 일봉을 리샘플링해서
계산하므로(signal_bot/timeframe_signals.py), 주봉은 더 이상 별도로 받지 않는다.

종목별 조회를 스레드풀로 동시에 처리한다(kis_client의 레이트리미터가 전체
호출 속도를 안전선 아래로 유지해주므로, 동시 실행 개수를 늘려도 API
호출제한을 넘지 않는다). 미국 종목은 kis_client, 한국 종목(KR_TARGETS)은
kis_client_kr로 분기.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from signal_bot import kis_client as kc
from signal_bot import kis_client_kr as kc_kr
from signal_bot.config import TICKERS, DAILY_MIN_ROWS, is_kr, kr_kind
from signal_bot.notifier import send_telegram_message

logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")

DATA_DIR = Path(__file__).parent / "data"

# 종목 수가 늘수록 일시적 조회 실패 확률이 통계적으로 올라가므로, 1차 실패분만
# 모아 2차로 재시도한다. 그래도 전체 성공률이 이 아래로 떨어지면 "조용히 며칠
# 방치되는" 상황을 막기 위해 텔레그램으로 별도 경고를 보낸다 (섹션 13-4).
SUCCESS_RATE_WARNING_THRESHOLD = 0.9


def _fetch_one(category: str, symb: str) -> dict:
    try:
        if is_kr(category):
            daily = kc_kr.fetch_ohlcv_kr(symb, kind=kr_kind(category), min_rows=DAILY_MIN_ROWS)
            excd = "KRX"
        else:
            daily = kc.fetch_ohlcv(symb, gubn="0", min_rows=DAILY_MIN_ROWS)
            excd = kc.exchange_of(symb)
        daily.to_csv(DATA_DIR / f"{symb}_daily.csv", index=False)
        return {
            "category": category,
            "symb": symb,
            "ok": True,
            "excd": excd,
            "daily_rows": len(daily),
            "error": None,
        }
    except Exception as e:
        return {
            "category": category,
            "symb": symb,
            "ok": False,
            "excd": None,
            "daily_rows": 0,
            "error": str(e),
        }


def _fetch_all(tickers: list[tuple[str, str]]) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=kc.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_fetch_one, category, symb): symb for category, symb in tickers}
        for future in as_completed(futures):
            results.append(future.result())

    order = {symb: i for i, (_category, symb) in enumerate(tickers)}
    results.sort(key=lambda r: order[r["symb"]])
    return results


def _send_quality_warning(results: list[dict]) -> None:
    ok_count = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    success_rate = ok_count / len(results) if results else 1.0
    if success_rate >= SUCCESS_RATE_WARNING_THRESHOLD:
        return

    failed_list = ", ".join(r["symb"] for r in failed[:20])
    if len(failed) > 20:
        failed_list += f" 외 {len(failed) - 20}개"
    message = (
        f"⚠️ *KIS 데이터 품질 경고*\n"
        f"{ok_count}/{len(results)}개 종목만 조회 성공 ({success_rate * 100:.1f}%, "
        f"기준 {SUCCESS_RATE_WARNING_THRESHOLD * 100:.0f}% 미만)\n"
        f"실패 종목: {failed_list}"
    )
    try:
        send_telegram_message(message)
        print("\n데이터 품질 경고 텔레그램 발송 완료")
    except Exception as e:
        print(f"\n데이터 품질 경고 텔레그램 발송 실패: {e}")


def main():
    DATA_DIR.mkdir(exist_ok=True)
    kc.ensure_auth()

    results = _fetch_all(TICKERS)

    failed_tickers = [(r["category"], r["symb"]) for r in results if not r["ok"]]
    if failed_tickers:
        print(f"\n1차 조회 실패 {len(failed_tickers)}종목 재시도 중...")
        retry_results = {r["symb"]: r for r in _fetch_all(failed_tickers)}
        results = [retry_results[r["symb"]] if r["symb"] in retry_results else r for r in results]

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{ok_count}/{len(results)} 성공\n")

    for r in results:
        if r["ok"]:
            flag = "OK  "
            daily_flag = "" if r["daily_rows"] >= DAILY_MIN_ROWS else f" (요청 {DAILY_MIN_ROWS} 미달)"
            print(f"{flag}{r['category']:6s} {r['symb']:6s} ({r['excd']})  daily={r['daily_rows']}{daily_flag}")
        else:
            print(f"FAIL {r['category']:6s} {r['symb']:6s}  {r['error']}")

    _send_quality_warning(results)

    return results


if __name__ == "__main__":
    main()

"""미국 정규장 마감 직후 실행이면 종가가 들어올 때까지 기다린다(daily.yml 첫 수집 전 단계).

    uv run python -m signal_bot.wait_us_close

us-close-timer.yml이 16:02 ET(겨울 06:02 KST, 여름 05:02 KST)에 daily.yml을 실행한다. 준비 단계가 빨리 끝나 16:04 ET
전이면 그때까지 기다리고(마감 동시호가 체결가가 시세에 실리는 시간), 그 뒤 SPY 일봉의 마지막 날짜가 뉴욕 오늘인지
확인한다(최대 20분, 1분 간격). KIS 해외 일봉은 장중에도 '오늘' 행을 채워 주므로 날짜 확인은 시세가 아예 하루 밀린
경우만 거른다 — 확정 여부는 시각(16:04 ET)으로 판단한다. 휴장일이면 오늘 행이 끝내 없으므로 20분 뒤 그대로 진행한다.
마감 직후(16:00~19:00 ET 평일)가 아닌 실행(예약 대체 실행·주말·수동)은 기다리지 않는다.
"""

import datetime as dt
import time
import zoneinfo

NY = zoneinfo.ZoneInfo("America/New_York")
READY = dt.time(16, 4)          # 이 시각 전이면 기다린다
CHECK_UNTIL = dt.time(19, 0)    # 마감 직후 창 — 이 시각 뒤 실행은 기다리지 않는다
MAX_WAIT_MIN = 20
STEP_SEC = 60


def main() -> None:
    now = dt.datetime.now(NY)
    if now.weekday() >= 5 or not (dt.time(15, 30) <= now.time() < CHECK_UNTIL):
        print(f"뉴욕 {now:%a %H:%M} — 마감 직후 실행이 아니라 기다리지 않음")
        return
    ready = now.replace(hour=READY.hour, minute=READY.minute, second=0, microsecond=0)
    if now < ready:
        wait = (ready - now).total_seconds()
        print(f"뉴욕 {now:%H:%M:%S} — 종가가 실리는 {READY:%H:%M} ET까지 {wait:.0f}초 대기")
        time.sleep(wait)

    from signal_bot import kis_client as kc   # 인증이 필요한 import는 실제로 확인할 때만
    today = dt.datetime.now(NY).date()
    deadline = time.time() + MAX_WAIT_MIN * 60
    while True:
        try:
            last = kc.fetch_ohlcv("SPY", gubn="0", min_rows=1)["date"].max().date()
        except Exception as e:   # 조회 실패는 다음 단계(fetch_universe)의 재시도·경고에 맡긴다
            print(f"SPY 확인 실패({e}) → 그대로 진행")
            return
        if last >= today:
            print(f"SPY 일봉 {last} 확인 — 뉴욕 {dt.datetime.now(NY):%H:%M:%S} 수집 시작")
            return
        if time.time() > deadline:
            print(f"SPY 마지막 일봉 {last} — {MAX_WAIT_MIN}분 안에 오늘({today}) 행이 없어(휴장일?) 그대로 진행")
            return
        time.sleep(STEP_SEC)


if __name__ == "__main__":
    main()

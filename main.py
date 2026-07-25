"""KIS 매수신호 알림 시스템 진입점.

일일 실행 순서:
1. signal_bot/fetch_universe.py 로 최신 시세 조회 (STEP 3)
2. main.py (본 파일) 로 스코어링 + 콘솔 리포트 + JSON 이력 저장 (STEP 7)
3. (STEP 8) 텔레그램 알림
"""

from signal_bot.pipeline import main

if __name__ == "__main__":
    main()

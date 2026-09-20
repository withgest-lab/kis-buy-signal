"""KIS 매수신호 알림 시스템 진입점 (MDD + RSI/MFI/다이버전스).

일일 실행 순서:
1. signal_bot/fetch_universe.py 로 최신 일봉 조회
2. signal_bot/baseline_fetch.py 로 20년치 베이스라인 갱신(내부 staleness로 보통 생략)
3. main.py (본 파일) 로 MDD단계+RSI/MFI/다이버전스 계산 + 콘솔 리포트 + JSON 이력 저장 + 텔레그램 알림
4. signal_bot/export_dashboard.py 로 대시보드 데이터 생성
"""

from signal_bot.pipeline import main

if __name__ == "__main__":
    main()

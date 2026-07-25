"""STEP 8 검증:
1. 텔레그램 연결 테스트 (실제 메시지 발송)
2. 상태 변화 감지 로직 검증 (합성 데이터, 실제 history.json은 건드리지 않음)
3. 중복 알림 방지 로직 검증 + 실제 알림 형태 발송
"""

from signal_bot import alerts
from signal_bot.notifier import send_telegram_message


def check_connection():
    print("=== 1. 텔레그램 연결 테스트 ===")
    send_telegram_message("[테스트] KIS 매수신호 알림 시스템 연결 확인 (STEP 8)")
    print("발송 완료 - 텔레그램에서 메시지 수신 확인해주세요.")


def check_state_change_logic():
    print("\n=== 2. 상태 변화 감지 로직 검증 (합성 데이터) ===")
    history = {
        "2026-07-23": {
            "TEST": {"category": "테스트", "symb": "TEST", "date": "2026-07-23",
                     "close": 100.0, "score": 40.0, "verdict": "무시", "signals": "-"},
            "STAY70": {"category": "테스트", "symb": "STAY70", "date": "2026-07-23",
                       "close": 50.0, "score": 75.0, "verdict": "강한매수후보", "signals": "-"},
        },
        "2026-07-24": {
            "TEST": {"category": "테스트", "symb": "TEST", "date": "2026-07-24",
                     "close": 105.0, "score": 78.0, "verdict": "강한매수후보", "signals": "다이버전스"},
            "STAY70": {"category": "테스트", "symb": "STAY70", "date": "2026-07-24",
                       "close": 51.0, "score": 76.0, "verdict": "강한매수후보", "signals": "-"},
        },
    }
    new_signals = alerts.find_new_strong_signals(history, "2026-07-24")
    symbs = [r["symb"] for r in new_signals]

    assert symbs == ["TEST"], f"TEST만 감지되어야 함(어제 40점->오늘 78점). 실제: {symbs}"
    print(f"PASS: 신규 70점 진입 종목만 감지됨 -> {symbs}")
    print("  (STAY70은 어제도 이미 75점(강한매수후보)이었으므로 반복 알림 대상 아님 - 정상 제외)")

    first_day_signals = alerts.find_new_strong_signals(history, "2026-07-23")
    assert first_day_signals == [], "첫 기록일은 비교 대상(전날)이 없으므로 빈 리스트여야 함"
    print("PASS: 첫 기록일은 전날 데이터가 없어 오탐 없이 빈 리스트 반환")

    return new_signals


def check_dedup_and_send(new_signals):
    print("\n=== 3. 중복 알림 방지 검증 + 실제 알림 형태 발송 ===")
    notified = {}
    today = "2026-07-24"

    to_send_1 = alerts.filter_unnotified(new_signals, today, notified)
    assert [r["symb"] for r in to_send_1] == ["TEST"]
    print("1차 실행: 미발송 상태 -> TEST 발송 대상")

    message = alerts.format_alert_message(to_send_1, today)
    send_telegram_message(message)
    print("실제 알림 형태 메시지 발송 완료 - 텔레그램에서 확인해주세요.")

    notified = alerts.mark_notified(notified, today, [r["symb"] for r in to_send_1])

    to_send_2 = alerts.filter_unnotified(new_signals, today, notified)
    assert to_send_2 == [], f"이미 알림 보낸 종목은 재실행 시 제외되어야 함. 실제: {to_send_2}"
    print("PASS: 2차 실행(재실행 시뮬레이션) -> 이미 알림 보낸 TEST는 제외되어 중복 발송 없음")


def main():
    check_connection()
    new_signals = check_state_change_logic()
    check_dedup_and_send(new_signals)
    print("\n=== STEP 8 검증 완료 ===")


if __name__ == "__main__":
    main()

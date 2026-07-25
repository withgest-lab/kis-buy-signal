"""타겟 종목 리스트 (PROJECT_PLAN.md 섹션 13, STEP 12-5: S&P500+나스닥100 전체 확장).

개별 종목은 더 이상 손으로 고른 리스트가 아니라 signal_bot.universe_source가
관리하는 S&P500+나스닥100 중복제거 유니버스(캐시, 월 1회 갱신)를 그대로 쓴다.
섹터ETF는 계속 손으로 고른 리스트를 유지한다(지수 구성종목이 아니라서 자동
소스가 없고, 개수가 적어 유지 부담도 낮음). GICS 11개 대표 섹터 SPDR ETF를
전부 포함하도록 XLK(기술)를 추가해서 11개 섹터 커버리지를 완성했다.
"""

from signal_bot import universe_source as _us

CURATED_ETFS = [
    ("섹터ETF", "SPY"),   # S&P500 전체
    ("섹터ETF", "QQQ"),   # 나스닥100 전체
    ("섹터ETF", "DIA"),   # 다우존스
    ("섹터ETF", "IWM"),   # 러셀2000(중소형주)

    # GICS 11개 대표 섹터 SPDR ETF (전부 커버)
    ("섹터ETF", "XLK"),   # 기술
    ("섹터ETF", "XLF"),   # 금융
    ("섹터ETF", "XLE"),   # 에너지
    ("섹터ETF", "XLV"),   # 헬스케어
    ("섹터ETF", "XLI"),   # 산업재
    ("섹터ETF", "XLP"),   # 필수소비재
    ("섹터ETF", "XLY"),   # 임의소비재
    ("섹터ETF", "XLU"),   # 유틸리티
    ("섹터ETF", "XLB"),   # 소재
    ("섹터ETF", "XLRE"),  # 리츠/부동산
    ("섹터ETF", "XLC"),   # 커뮤니케이션서비스

    # 테마/성장 ETF
    ("섹터ETF", "CIBR"),
    ("섹터ETF", "BUG"),
    ("섹터ETF", "SOXX"),
    ("섹터ETF", "BOTZ"),
    ("섹터ETF", "ROBO"),
    ("섹터ETF", "AIPO"),
    ("섹터ETF", "QTUM"),
    ("섹터ETF", "VOLT"),
    ("섹터ETF", "ARKK"),
    ("섹터ETF", "ICLN"),
]

CURATED_ETF_NAMES = {
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF",
    "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF",
    "XLK": "Technology ETF", "XLF": "Financials ETF", "XLE": "Energy ETF",
    "XLV": "Health Care ETF", "XLI": "Industrials ETF", "XLP": "Consumer Staples ETF",
    "XLY": "Consumer Discretionary ETF", "XLU": "Utilities ETF", "XLB": "Materials ETF",
    "XLRE": "Real Estate ETF", "XLC": "Communication Services ETF",
    "CIBR": "Cybersecurity ETF", "BUG": "Cybersecurity ETF(BUG)",
    "SOXX": "Semiconductor ETF", "BOTZ": "Robotics&AI ETF", "ROBO": "Robotics ETF",
    "AIPO": "AI Infra ETF", "QTUM": "Quantum ETF", "VOLT": "Electrification ETF",
    "ARKK": "ARK Innovation ETF", "ICLN": "Clean Energy ETF",
}

DAILY_MIN_ROWS = 250
WEEKLY_MIN_ROWS = 104

# history.json 롤링 윈도우: 스파크라인(최근 30일)/백테스트엔 이 정도면 충분하고,
# 무한정 누적되어 저장소 용량이 불어나는 걸 막는다 (PROJECT_PLAN.md 섹션 13-2).
HISTORY_MAX_DAYS = 180

_universe = _us.get_combined_universe()

TICKERS = CURATED_ETFS + [("개별종목", entry["symb"]) for entry in _universe]

TICKER_NAMES = dict(CURATED_ETF_NAMES)
TICKER_NAMES.update({entry["symb"]: entry["name"] for entry in _universe})

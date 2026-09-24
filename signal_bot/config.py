"""타겟 종목 리스트 - MDD 우량주 매수신호 유니버스.

개별종목은 S&P500 시가총액 상위30 + 나스닥100 상위20(중복제거, signal_bot.
universe_source가 매월 갱신). 섹터ETF는 계속 손으로 고른 리스트를 유지한다
(지수 구성종목이 아니라서 자동 소스가 없고, 개수가 적어 유지 부담도 낮음).
한국 KOSPI200·삼성전자·SK하이닉스는 KR_TARGETS로 별도 추가.
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

    # 미국 산업 ETF (GICS 섹터 SPDR 밖의 세부 산업)
    ("섹터ETF", "XBI"),
    ("섹터ETF", "KRE"),
    ("섹터ETF", "ITA"),
    ("섹터ETF", "ITB"),
    ("섹터ETF", "XRT"),
    ("섹터ETF", "IYT"),
    ("섹터ETF", "XME"),
    ("섹터ETF", "GDX"),
    ("섹터ETF", "URA"),
    ("섹터ETF", "IGV"),
    ("섹터ETF", "SMH"),
    ("섹터ETF", "XOP"),
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
    "XBI": "Biotech ETF", "KRE": "Regional Banks ETF", "ITA": "Aerospace & Defense ETF",
    "ITB": "Home Construction ETF", "XRT": "Retail ETF", "IYT": "Transportation ETF",
    "XME": "Metals & Mining ETF", "GDX": "Gold Miners ETF", "URA": "Uranium ETF",
    "IGV": "Software ETF", "SMH": "Semiconductor ETF(SMH)", "XOP": "Oil & Gas Exploration ETF",
}

CURATED_ETF_DESCRIPTIONS = {
    "SPY": "S&P500 지수 전체를 추종하는 대표 ETF",
    "QQQ": "나스닥100 지수를 추종하는 대형 기술주 중심 ETF",
    "DIA": "다우존스 산업평균지수를 추종하는 ETF",
    "IWM": "러셀2000 지수를 추종하는 미국 중소형주 ETF",
    "XLK": "정보기술(IT) 섹터 대표 기업들에 투자하는 ETF",
    "XLF": "은행·보험 등 금융 섹터 대표 기업들에 투자하는 ETF",
    "XLE": "정유·가스 등 에너지 섹터 대표 기업들에 투자하는 ETF",
    "XLV": "제약·의료기기 등 헬스케어 섹터 대표 기업들에 투자하는 ETF",
    "XLI": "항공·기계 등 산업재 섹터 대표 기업들에 투자하는 ETF",
    "XLP": "식음료·생필품 등 필수소비재 섹터 대표 기업들에 투자하는 ETF",
    "XLY": "유통·외식 등 임의소비재 섹터 대표 기업들에 투자하는 ETF",
    "XLU": "전력·가스 등 유틸리티 섹터 대표 기업들에 투자하는 ETF",
    "XLB": "화학·금속 등 소재 섹터 대표 기업들에 투자하는 ETF",
    "XLRE": "리츠(REIT) 등 부동산 섹터 대표 기업들에 투자하는 ETF",
    "XLC": "통신·미디어 등 커뮤니케이션서비스 섹터 대표 기업들에 투자하는 ETF",
    "CIBR": "사이버보안 관련 기업들에 투자하는 테마 ETF",
    "BUG": "사이버보안 관련 기업들에 투자하는 테마 ETF",
    "SOXX": "반도체 설계·제조 기업들에 투자하는 테마 ETF",
    "BOTZ": "로봇·인공지능 관련 기업들에 투자하는 테마 ETF",
    "ROBO": "로봇·자동화 관련 기업들에 투자하는 테마 ETF",
    "AIPO": "AI 인프라(데이터센터·반도체 등) 관련 기업들에 투자하는 테마 ETF",
    "QTUM": "양자컴퓨팅 관련 기업들에 투자하는 테마 ETF",
    "VOLT": "전기화(전력망·배터리 등) 관련 기업들에 투자하는 테마 ETF",
    "ARKK": "파괴적 혁신 기술 기업들에 투자하는 액티브 운용 ETF",
    "ICLN": "태양광·풍력 등 클린에너지 관련 기업들에 투자하는 테마 ETF",
    "XBI": "바이오테크 기업들에 동일가중으로 투자하는 ETF",
    "KRE": "미국 지역은행 주식에 투자하는 ETF",
    "ITA": "항공우주·방위산업 기업들에 투자하는 ETF",
    "ITB": "주택건설 기업들에 투자하는 ETF",
    "XRT": "미국 소매·유통 기업들에 동일가중으로 투자하는 ETF",
    "IYT": "항공·철도·트럭 등 운송 기업들에 투자하는 ETF",
    "XME": "금속·광산 기업들에 투자하는 ETF",
    "GDX": "금광 기업들에 투자하는 ETF",
    "URA": "우라늄·원자력 관련 기업들에 투자하는 ETF",
    "IGV": "소프트웨어 기업들에 투자하는 ETF",
    "SMH": "반도체 대표 기업들에 투자하는 ETF",
    "XOP": "석유·가스 탐사·생산 기업들에 투자하는 ETF",
}

DAILY_MIN_ROWS = 250

# history.json 롤링 윈도우: 무한정 누적되어 저장소 용량이 불어나는 걸 막는다.
HISTORY_MAX_DAYS = 180

# RSI/MFI 오버솔드(과매도) 판정 임계값 - 볼린저 %B를 없앤 지금은 RSI/MFI
# 단독으로 쓰이므로, 기존 %B 결합용 35 대신 고전적인 임계값을 채택.
RSI_OVERSOLD = 30
MFI_OVERSOLD = 20

SP500_TOP_N = 30
NASDAQ100_TOP_N = 20

# 시장 전체를 대표하는 지수성 ETF만 따로 - 개별 기업 리스크가 아니라 "지금 시장이
# 조정/약세장/폭락 중 어디쯔음인지"를 절대 낙폭(%) 기준으로 감시한다. 이 시스템은
# 원래 "MDD 매수신호"(매도가 아니라 낙폭이 깊을 때를 우량 지수 ETF 장기 매수 기회로
# 보는 전략)이므로, 이 경보도 매수 기회 참고용이다. 기존 MDD 0~3단계는 종목별 과거
# 백분위 기반 상대평가라 이것과는 별개(절대 % 고정 임계값).
MDD_ALERT_TICKERS = ["SPY", "QQQ", "DIA", "SOXX"]

# 하락률 구간별 통용 명칭(웹 검색으로 확인: 5~10%=Pullback, 10~20%=Correction,
# 20%+=Bear Market/Crash. 과거 27번 약세장 평균낙폭 -35%, 2008년 -50%대,
# 1973-74년 -52%, 닷컴버블 -47% 등을 참고해 30/40/50% 단계도 추가).
# 깊은 것부터 순서대로 - 판정 시 depth가 이 리스트를 위에서부터 훑어 처음 맞는
# 항목을 "현재 단계"로 삼는다.
MDD_ALERT_LEVELS = [
    (0.50, "역사적 수준 폭락 - 우량 지수 장기매수 최적기 참고"),
    (0.40, "대규모 폭락 - 장기매수 기회 참고"),
    (0.30, "심각한 약세장 - 장기매수 기회 참고"),
    (0.25, "약세장 심화"),
    (0.20, "약세장(Bear Market) 진입"),
    (0.15, "조정 심화"),
    (0.10, "조정(Correction) 진입"),
]

# 시장 전체를 대표하는 지수성 ETF만 따로 - 개별 기업 리스크가 아니라 "지금 시장이
# 조정/약세장/폭락 중 어디쯤인지"를 절대 낙폭(%) 기준으로 감시해서 매도 등 매매판단
# 참고용으로 텔레그램+대시보드에 하이라이트한다(기존 MDD 0~3단계는 종목별 과거
# 백분위 기반 상대평가라 이것과는 별개).
MDD_ALERT_TICKERS = ["SPY", "QQQ", "DIA", "SOXX"]

# 하락률 구간별 통용 명칭(웹 검색으로 확인: 5~10%=Pullback, 10~20%=Correction,
# 20%+=Bear Market/Crash. 과거 27번 약세장 평균낙폭 -35%, 2008년 -50%대,
# 1973-74년 -52%, 닷컴버블 -47% 등을 참고해 30/40/50% 단계도 추가).
# 깊은 것부터 순서대로 - 판정 시 depth가 이 리스트를 위에서부터 훑어 처음 맞는
# 항목을 "현재 단계"로 삼는다.
MDD_ALERT_LEVELS = [
    (0.50, "역사적 수준 폭락"),
    (0.40, "대규모 폭락"),
    (0.30, "심각한 약세장"),
    (0.25, "약세장 심화"),
    (0.20, "약세장(Bear Market) 진입"),
    (0.15, "조정 심화"),
    (0.10, "조정(Correction) 진입"),
]

# 한국 종목 - KOSPI200(지수), 삼성전자·SK하이닉스(개별종목). KIS 국내주식
# API(signal_bot/kis_client_kr.py)로 조회하며, 이 두 카테고리 문자열로
# 미국/한국 API 분기를 판단한다(fetch_universe.py/baseline_fetch.py 참고).
KR_INDEX_CATEGORY = "한국지수"
KR_STOCK_CATEGORY = "한국개별종목"
KR_ETF_CATEGORY = "한국ETF"
KR_TARGETS = [
    (KR_INDEX_CATEGORY, "KOSPI200"),
    (KR_STOCK_CATEGORY, "005930"),   # 삼성전자
    (KR_STOCK_CATEGORY, "000660"),   # SK하이닉스
    (KR_STOCK_CATEGORY, "005380"),   # 현대차
    (KR_STOCK_CATEGORY, "000270"),   # 기아
    (KR_STOCK_CATEGORY, "373220"),   # LG에너지솔루션
    (KR_STOCK_CATEGORY, "207940"),   # 삼성바이오로직스
    (KR_STOCK_CATEGORY, "068270"),   # 셀트리온
    (KR_STOCK_CATEGORY, "105560"),   # KB금융
    (KR_STOCK_CATEGORY, "055550"),   # 신한지주
    (KR_STOCK_CATEGORY, "086790"),   # 하나금융지주
    (KR_STOCK_CATEGORY, "035420"),   # NAVER
    (KR_STOCK_CATEGORY, "035720"),   # 카카오
    (KR_STOCK_CATEGORY, "005490"),   # POSCO홀딩스
    (KR_STOCK_CATEGORY, "006400"),   # 삼성SDI
    (KR_STOCK_CATEGORY, "051910"),   # LG화학
    (KR_STOCK_CATEGORY, "012330"),   # 현대모비스
    (KR_STOCK_CATEGORY, "012450"),   # 한화에어로스페이스
    (KR_STOCK_CATEGORY, "329180"),   # HD현대중공업
    (KR_STOCK_CATEGORY, "028260"),   # 삼성물산
    (KR_STOCK_CATEGORY, "034020"),   # 두산에너빌리티
    (KR_STOCK_CATEGORY, "015760"),   # 한국전력
    (KR_STOCK_CATEGORY, "096770"),   # SK이노베이션
    (KR_ETF_CATEGORY, "069500"),   # KODEX 200
    (KR_ETF_CATEGORY, "229200"),   # KODEX 코스닥150
    (KR_ETF_CATEGORY, "091160"),   # KODEX 반도체
    (KR_ETF_CATEGORY, "305720"),   # KODEX 2차전지산업
    (KR_ETF_CATEGORY, "091180"),   # KODEX 자동차
    (KR_ETF_CATEGORY, "091170"),   # KODEX 은행
    (KR_ETF_CATEGORY, "244580"),   # KODEX 바이오
    (KR_ETF_CATEGORY, "139260"),   # TIGER 200 IT
    (KR_ETF_CATEGORY, "117700"),   # KODEX 건설
    (KR_ETF_CATEGORY, "102970"),   # KODEX 증권
]
KR_NAMES = {
    "KOSPI200": "코스피200", "005930": "삼성전자", "000660": "SK하이닉스",
    "005380": "현대차",
    "000270": "기아",
    "373220": "LG에너지솔루션",
    "207940": "삼성바이오로직스",
    "068270": "셀트리온",
    "105560": "KB금융",
    "055550": "신한지주",
    "086790": "하나금융지주",
    "035420": "NAVER",
    "035720": "카카오",
    "005490": "POSCO홀딩스",
    "006400": "삼성SDI",
    "051910": "LG화학",
    "012330": "현대모비스",
    "012450": "한화에어로스페이스",
    "329180": "HD현대중공업",
    "028260": "삼성물산",
    "034020": "두산에너빌리티",
    "015760": "한국전력",
    "096770": "SK이노베이션",
    "069500": "KODEX 200",
    "229200": "KODEX 코스닥150",
    "091160": "KODEX 반도체",
    "305720": "KODEX 2차전지산업",
    "091180": "KODEX 자동차",
    "091170": "KODEX 은행",
    "244580": "KODEX 바이오",
    "139260": "TIGER 200 IT",
    "117700": "KODEX 건설",
    "102970": "KODEX 증권",
}

# 한국 ETF 사업요약(알림/카드 설명용) - company_info가 CURATED_ETF_DESCRIPTIONS에서 읽는다.
KR_ETF_DESCRIPTIONS = {
    "069500": "코스피200 지수를 추종하는 국내 대표 ETF(KODEX 200)",
    "229200": "코스닥150 지수를 추종하는 ETF",
    "091160": "국내 반도체 대표 기업들에 투자하는 ETF",
    "305720": "국내 2차전지 관련 기업들에 투자하는 ETF",
    "091180": "국내 자동차 관련 기업들에 투자하는 ETF",
    "091170": "국내 은행주에 투자하는 ETF",
    "244580": "국내 바이오 기업들에 투자하는 ETF",
    "139260": "코스피200 IT 업종(반도체·소프트웨어 등)에 투자하는 ETF",
    "117700": "국내 건설 기업들에 투자하는 ETF",
    "102970": "국내 증권주에 투자하는 ETF",
}
CURATED_ETF_DESCRIPTIONS.update(KR_ETF_DESCRIPTIONS)


_ranked = _us.get_top_n_targets(SP500_TOP_N, NASDAQ100_TOP_N)

TICKERS = CURATED_ETFS + [("개별종목", r["symb"]) for r in _ranked] + KR_TARGETS

TICKER_NAMES = dict(CURATED_ETF_NAMES)
TICKER_NAMES.update({r["symb"]: r["name"] for r in _ranked})
TICKER_NAMES.update(KR_NAMES)


def is_kr(category: str) -> bool:
    return category in (KR_INDEX_CATEGORY, KR_STOCK_CATEGORY, KR_ETF_CATEGORY)


def kr_kind(category: str) -> str:
    """KIS 국내 API 호출 종류: "index"(지수) 또는 "item"(개별종목)."""
    return "index" if category == KR_INDEX_CATEGORY else "item"

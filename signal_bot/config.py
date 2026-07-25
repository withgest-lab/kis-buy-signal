"""타겟 종목 리스트 (PROJECT_PLAN.md 섹션 2, 2026-07-26 92개로 확장)"""

TICKERS = [
    # 빅테크 10
    ("빅테크", "NVDA"),
    ("빅테크", "AAPL"),
    ("빅테크", "GOOGL"),
    ("빅테크", "MSFT"),
    ("빅테크", "AMZN"),
    ("빅테크", "META"),
    ("빅테크", "AVGO"),
    ("빅테크", "TSLA"),
    ("빅테크", "ORCL"),
    ("빅테크", "PLTR"),

    # 산업대장 (기존 12 + 신규 46, 산업군별 대표주 2개씩)
    ("산업대장", "CRWD"),   # 사이버보안
    ("산업대장", "PANW"),   # 사이버보안
    ("산업대장", "TSM"),    # 반도체 설계/파운드리
    ("산업대장", "ISRG"),   # 헬스케어 서비스/장비
    ("산업대장", "ROK"),    # 중장비/자동화
    ("산업대장", "IONQ"),   # 양자컴퓨팅
    ("산업대장", "BE"),     # 에너지전환/신재생
    ("산업대장", "GEV"),    # AI 데이터센터 인프라
    ("산업대장", "VRT"),    # AI 데이터센터 인프라
    ("산업대장", "COHR"),   # 네트워킹/광통신
    ("산업대장", "RKLB"),   # 우주
    ("산업대장", "LMT"),    # 항공/방산
    ("산업대장", "JPM"),    # 은행
    ("산업대장", "BAC"),    # 은행
    ("산업대장", "V"),      # 결제/핀테크
    ("산업대장", "MA"),     # 결제/핀테크
    ("산업대장", "LLY"),    # 제약
    ("산업대장", "JNJ"),    # 제약
    ("산업대장", "REGN"),   # 바이오텍
    ("산업대장", "VRTX"),   # 바이오텍
    ("산업대장", "UNH"),    # 헬스케어 서비스
    ("산업대장", "WMT"),    # 유통(필수소비재)
    ("산업대장", "COST"),   # 유통(필수소비재)
    ("산업대장", "PG"),     # 생활용품/음료
    ("산업대장", "KO"),     # 생활용품/음료
    ("산업대장", "HD"),     # 소매(임의소비재)
    ("산업대장", "NKE"),    # 소매(임의소비재)
    ("산업대장", "MCD"),    # 외식/여행
    ("산업대장", "SBUX"),   # 외식/여행
    ("산업대장", "GM"),     # 자동차
    ("산업대장", "RIVN"),   # 자동차
    ("산업대장", "XOM"),    # 전통 에너지
    ("산업대장", "CVX"),    # 전통 에너지
    ("산업대장", "CEG"),    # 차세대 원자력
    ("산업대장", "SMR"),    # 차세대 원자력
    ("산업대장", "LIN"),    # 소재/자원
    ("산업대장", "FCX"),    # 소재/자원
    ("산업대장", "CAT"),    # 중장비/자동화
    ("산업대장", "RTX"),    # 항공/방산
    ("산업대장", "NEE"),    # 유틸리티
    ("산업대장", "SO"),     # 유틸리티
    ("산업대장", "PLD"),    # 리츠/부동산
    ("산업대장", "AMT"),    # 리츠/부동산
    ("산업대장", "NFLX"),   # 미디어/엔터
    ("산업대장", "DIS"),    # 미디어/엔터
    ("산업대장", "VZ"),     # 통신
    ("산업대장", "TMUS"),   # 통신
    ("산업대장", "AMD"),    # 반도체 설계/파운드리
    ("산업대장", "ASML"),   # 반도체 장비
    ("산업대장", "AMAT"),   # 반도체 장비
    ("산업대장", "MU"),     # 메모리반도체
    ("산업대장", "SKHY"),   # 메모리반도체 (SK하이닉스)
    ("산업대장", "ANET"),   # 네트워킹/광통신
    ("산업대장", "RGTI"),   # 양자컴퓨팅
    ("산업대장", "ASTS"),   # 우주
    ("산업대장", "FSLR"),   # 에너지전환/신재생
    ("산업대장", "CRM"),    # 클라우드/SaaS
    ("산업대장", "NOW"),    # 클라우드/SaaS

    # 섹터ETF (기존 10 + 신규 14)
    ("섹터ETF", "SPY"),
    ("섹터ETF", "QQQ"),
    ("섹터ETF", "CIBR"),
    ("섹터ETF", "BUG"),
    ("섹터ETF", "SOXX"),
    ("섹터ETF", "BOTZ"),
    ("섹터ETF", "ROBO"),
    ("섹터ETF", "AIPO"),
    ("섹터ETF", "QTUM"),
    ("섹터ETF", "VOLT"),
    ("섹터ETF", "DIA"),
    ("섹터ETF", "IWM"),
    ("섹터ETF", "XLF"),
    ("섹터ETF", "XLE"),
    ("섹터ETF", "XLV"),
    ("섹터ETF", "XLI"),
    ("섹터ETF", "XLP"),
    ("섹터ETF", "XLY"),
    ("섹터ETF", "XLU"),
    ("섹터ETF", "XLB"),
    ("섹터ETF", "XLRE"),
    ("섹터ETF", "XLC"),
    ("섹터ETF", "ARKK"),
    ("섹터ETF", "ICLN"),
]

DAILY_MIN_ROWS = 250
WEEKLY_MIN_ROWS = 104

TICKER_NAMES = {
    "NVDA": "NVIDIA", "AAPL": "Apple", "GOOGL": "Alphabet", "MSFT": "Microsoft",
    "AMZN": "Amazon", "META": "Meta Platforms", "AVGO": "Broadcom", "TSLA": "Tesla",
    "ORCL": "Oracle", "PLTR": "Palantir",

    "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks", "TSM": "TSMC",
    "ISRG": "Intuitive Surgical", "ROK": "Rockwell Automation", "IONQ": "IonQ",
    "BE": "Bloom Energy", "GEV": "GE Vernova", "VRT": "Vertiv",
    "COHR": "Coherent", "RKLB": "Rocket Lab", "LMT": "Lockheed Martin",
    "JPM": "JPMorgan Chase", "BAC": "Bank of America",
    "V": "Visa", "MA": "Mastercard",
    "LLY": "Eli Lilly", "JNJ": "Johnson & Johnson",
    "REGN": "Regeneron", "VRTX": "Vertex Pharmaceuticals",
    "UNH": "UnitedHealth Group",
    "WMT": "Walmart", "COST": "Costco",
    "PG": "Procter & Gamble", "KO": "Coca-Cola",
    "HD": "Home Depot", "NKE": "Nike",
    "MCD": "McDonald's", "SBUX": "Starbucks",
    "GM": "General Motors", "RIVN": "Rivian",
    "XOM": "ExxonMobil", "CVX": "Chevron",
    "CEG": "Constellation Energy", "SMR": "NuScale Power",
    "LIN": "Linde", "FCX": "Freeport-McMoRan",
    "CAT": "Caterpillar", "RTX": "RTX Corporation",
    "NEE": "NextEra Energy", "SO": "Southern Company",
    "PLD": "Prologis", "AMT": "American Tower",
    "NFLX": "Netflix", "DIS": "Walt Disney",
    "VZ": "Verizon", "TMUS": "T-Mobile US",
    "AMD": "AMD", "ASML": "ASML", "AMAT": "Applied Materials",
    "MU": "Micron Technology", "SKHY": "SK Hynix",
    "ANET": "Arista Networks",
    "RGTI": "Rigetti Computing",
    "ASTS": "AST SpaceMobile",
    "FSLR": "First Solar",
    "CRM": "Salesforce", "NOW": "ServiceNow",

    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "CIBR": "Cybersecurity ETF",
    "BUG": "Cybersecurity ETF(BUG)", "SOXX": "Semiconductor ETF", "BOTZ": "Robotics&AI ETF",
    "ROBO": "Robotics ETF", "AIPO": "AI Infra ETF", "QTUM": "Quantum ETF", "VOLT": "Electrification ETF",
    "DIA": "Dow Jones ETF", "IWM": "Russell 2000 ETF",
    "XLF": "Financials ETF", "XLE": "Energy ETF", "XLV": "Health Care ETF",
    "XLI": "Industrials ETF", "XLP": "Consumer Staples ETF", "XLY": "Consumer Discretionary ETF",
    "XLU": "Utilities ETF", "XLB": "Materials ETF", "XLRE": "Real Estate ETF",
    "XLC": "Communication Services ETF", "ARKK": "ARK Innovation ETF", "ICLN": "Clean Energy ETF",
}

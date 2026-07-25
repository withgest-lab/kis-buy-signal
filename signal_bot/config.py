"""타겟 종목 리스트 (PROJECT_PLAN.md 섹션 2)"""

TICKERS = [
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
    ("산업대장", "CRWD"),
    ("산업대장", "PANW"),
    ("산업대장", "TSM"),
    ("산업대장", "ISRG"),
    ("산업대장", "ROK"),
    ("산업대장", "IONQ"),
    ("산업대장", "BE"),
    ("산업대장", "GEV"),
    ("산업대장", "VRT"),
    ("산업대장", "COHR"),
    ("산업대장", "RKLB"),
    ("산업대장", "LMT"),
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
    "SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF", "CIBR": "Cybersecurity ETF",
    "BUG": "Cybersecurity ETF(BUG)", "SOXX": "Semiconductor ETF", "BOTZ": "Robotics&AI ETF",
    "ROBO": "Robotics ETF", "AIPO": "AI Infra ETF", "QTUM": "Quantum ETF", "VOLT": "Electrification ETF",
}

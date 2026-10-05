"""보유 종목 → 매매 전략 종목(기초지수 ETF) 매칭 규칙.

포트폴리오 화면(portfolio/)과 매매전략 화면(portfolio-retirement-dashboard 저장소 signals/)이 **같은 규칙을 읽는다** —
export_dashboard.py가 이 목록을 docs/scores.json 의 "proxies" 로 내보내고, 두 화면은 그걸 그대로 쓴다.
(예전에는 두 화면에 SPY/QQQ 정규식이 따로 복사돼 있었다.)

해석 순서(화면 쪽): ① 티커 직접 일치(.KS/.KQ/.T 제거) → ② 아래 규칙을 위에서부터 첫 일치 → ③ 없으면 "미매칭".
  - "tk": 티커 정규식(대문자·접미사 제거 후). "re": 이름 정규식 — 이름이 운용사 접두(TIGER/KODEX/ACE/…)로 시작하는 ETF에만
    적용하며, 접두를 뗀 뒤 검사한다(개별 종목 이름이 우연히 걸리는 것을 막는다).
  - "symb": 연결할 전략 종목. None 이면 "전략 대상 아님"이고 "why" 가 그 이유(버튼 툴팁).
  - 정규식은 Python·JavaScript 양쪽에서 같게 동작하는 기본 문법만 쓴다(교대·앵커·문자 클래스).
새 규칙이 가리키는 종목은 반드시 config.TICKERS 안에 있어야 한다 — scripts/check_proxies.py 가 검사한다.
"""

# 운용사 접두(포트폴리오 ETF_ISSUER_PREFIX_RE 와 같은 목록). 화면 쪽이 이 문자열을 그대로 받아 쓴다.
ISSUER_PREFIX_RE = r"^(TIGER|KODEX|ACE|RISE|SOL|HANARO|KIWOOM|TIME|PLUS|KINDEX|ARIRANG|KBSTAR|TIMEFOLIO|KOSEF|WOORI|FOCUS|KoAct|HK)\s*"

_NO = "채권·현금성·합성 상품이라 낙폭 매수/매도 전략의 의미가 없습니다"

RULES = [
    # ── 티커로 알아보는 미국 상장 ETF(포트폴리오에 직접 보유한 경우) ──
    {"tk": r"^(VOO|IVV|SPLG|VTI|ITOT)$", "symb": "SPY"},
    {"tk": r"^(QQQM|TQQQ)$", "symb": "QQQ"},
    {"tk": r"^(SOXL|SOXX)$", "symb": "SOXX"},
    {"tk": r"^(VYM|DGRO|SCHY)$", "symb": "SCHD"},
    {"tk": r"^(IAU|GLDM)$", "symb": "GLD"},
    {"tk": r"^(IEI|SHY|BND|AGG)$", "symb": "IEF"},
    {"tk": r"^(TLH|EDV|VGLT)$", "symb": "TLT"},
    {"tk": r"^(VNQ|SCHH)$", "symb": "XLRE"},
    {"tk": r"^(FXI|KWEB)$", "symb": "MCHI"},

    # ── 이름으로 알아보는 한국 상장 ETF (접두 제거 후) ──
    # 전략 의미가 없는 것(먼저 걸러야 아래 넓은 규칙에 안 잡힘)
    {"re": r"(단기채권|단기통안채|TDF|국고채|중장기국채|200미국채혼합|CD금리|머니마켓|MMF)", "symb": None, "why": _NO},

    # 미국 대표 지수 — 레버리지·인버스·환헤지(H)·액티브 변형도 같은 기초지수
    {"re": r"S&P\s?500", "symb": "SPY"},
    {"re": r"나스닥\s?100", "symb": "QQQ"},
    {"re": r"미국\s?빅테크\s?TOP\s?7", "symb": "QQQ"},
    {"re": r"미국\s?테크\s?TOP\s?10", "symb": "XLK"},
    {"re": r"^테크\s?TOP\s?10", "symb": "XLK"},
    {"re": r"미국\s?다우존스30", "symb": "DIA"},

    # 반도체: 미국 필라델피아 지수 → SOXX, 국내 반도체 → KODEX 반도체
    {"re": r"필라델피아", "symb": "SOXX"},
    {"re": r"미국\s?(AI)?반도체", "symb": "SOXX"},
    {"re": r"(반도체|AI반도체)", "symb": "091160"},

    # 배당·리츠·금·채권·해외
    {"re": r"미국\s?배당", "symb": "SCHD"},
    {"re": r"(골드|금현물|KRX금)", "symb": "GLD"},
    {"re": r"미국채\s?10년|미국\s?국채\s?10년", "symb": "IEF"},
    {"re": r"미국\s?(30년|장기)\s?(국)?채|미국채\s?30년", "symb": "TLT"},
    {"re": r"리츠|부동산", "symb": "XLRE"},
    {"re": r"(차이나|중국)", "symb": "MCHI"},
    {"re": r"(일본|니케이|닛케이|TOPIX)", "symb": "EWJ"},

    # 테마
    {"re": r"미국\s?AI\s?전력", "symb": "AIPO"},
    {"re": r"AI\s?전력", "symb": "VOLT"},
    {"re": r"글로벌\s?AI\s?&?\s?로보틱스|글로벌\s?AI\s?액티브|글로벌\s?로봇", "symb": "BOTZ"},
    {"re": r"로봇|로보틱스|휴머노이드", "symb": "ROBO"},
    {"re": r"사이버보안", "symb": "CIBR"},
    {"re": r"미국\s?(방산|우주)", "symb": "ITA"},
    {"re": r"(방산|우주|항공)", "symb": "012450"},   # 국내 방산·우주 → 한화에어로스페이스
    {"re": r"(우라늄)", "symb": "URA"},
    {"re": r"(원자력|SMR)", "symb": "034020"},       # 국내 원자력 → 두산에너빌리티
    {"re": r"조선", "symb": "329180"},
    {"re": r"2차전지|배터리", "symb": "305720"},
    {"re": r"신재생|클린에너지", "symb": "ICLN"},
    {"re": r"(자동차|모빌리티)", "symb": "091180"},
    {"re": r"소프트웨어", "symb": "IGV"},
    {"re": r"(게임|콘텐츠|컨텐츠|미디어)", "symb": "XLC"},
    {"re": r"(화장품|필수소비재|경기방어|생활소비재)", "symb": "XLP"},
    {"re": r"미국\s?헬스케어", "symb": "XLV"},
    {"re": r"(바이오|헬스케어)", "symb": "244580"},   # 국내 바이오·헬스케어 → KODEX 바이오
    {"re": r"(철강|소재)", "symb": "XME"},
    {"re": r"(에너지화학)", "symb": "XLB"},
    {"re": r"(건설)", "symb": "117700"},
    {"re": r"(은행|금융|보험)", "symb": "091170"},
    {"re": r"증권", "symb": "102970"},
    {"re": r"(운송)", "symb": "IYT"},
    {"re": r"(중공업)", "symb": "329180"},
    {"re": r"(경기소비재)", "symb": "XLY"},
    {"re": r"(산업재)", "symb": "XLI"},
    {"re": r"(^IT$|\sIT$|200\s?IT)", "symb": "139260"},

    # 그룹주·국내 대표 지수·커버드콜(기초지수 기준)
    {"re": r"삼성그룹", "symb": "005930"},
    {"re": r"현대차그룹", "symb": "005380"},
    {"re": r"LG그룹", "symb": "051910"},
    {"re": r"코스닥\s?150", "symb": "229200"},
    {"re": r"(^200|\s200|코스피|레버리지$|^인버스|지주회사|코리아\s?TOP|고배당|K-?뉴딜|BBIG|커버드콜)", "symb": "069500"},
]


# ── 같은 알고리즘의 파이썬판(검사·테스트용). 화면(JavaScript)은 이 로직을 그대로 옮긴 것이다. ──
import re as _re

_PREFIX = _re.compile(ISSUER_PREFIX_RE, _re.I)


def normalize_ticker(ticker: str) -> str:
    return _re.sub(r"\.(KS|KQ|T)$", "", (ticker or "").strip().upper())


def resolve(name: str, ticker: str, universe: set[str]):
    """-> ("direct"|"proxy"|"none"|"unmatched", symb|None, why|None)"""
    t = normalize_ticker(ticker)
    if t and t in universe:
        return ("direct", t, None)
    nm = (name or "").strip()
    is_etf = bool(_PREFIX.match(nm))   # 이름 규칙은 ETF(운용사 접두)에만 — "메리츠화재" 같은 개별 종목이 "리츠"에 걸리면 안 된다
    stripped = _PREFIX.sub("", nm)
    for r in RULES:
        if "tk" in r and t and _re.search(r["tk"], t, _re.I):
            hit = r
        elif "re" in r and is_etf and stripped and _re.search(r["re"], stripped, _re.I):
            hit = r
        else:
            continue
        if hit["symb"] is None:
            return ("none", None, hit.get("why"))
        return ("proxy", hit["symb"], None)
    return ("unmatched", None, None)

"""ETF_PROXY 규칙 점검: python -m signal_bot.check_proxies [stocks.csv 경로]

1) 규칙이 가리키는 종목이 전부 유니버스(config.TICKERS)에 있는지(없으면 실패 종료)
2) (선택) 포트폴리오 stocks.csv의 한국 ETF 전체를 규칙에 돌려 [직접/대응/대상 아님/미매칭] 집계
"""
import csv
import sys

from signal_bot import proxies
from signal_bot.config import TICKERS

UNIVERSE = {s for _c, s in TICKERS}


def main(csv_path: str | None) -> int:
    missing = sorted({r["symb"] for r in proxies.RULES if r["symb"] and r["symb"] not in UNIVERSE})
    if missing:
        print("규칙이 가리키는데 유니버스에 없는 종목:", missing)
        return 1
    print(f"규칙 {len(proxies.RULES)}개 — 가리키는 종목 모두 유니버스({len(UNIVERSE)}종목)에 있음")
    if not csv_path:
        return 0
    tally = {"direct": [], "proxy": [], "none": [], "unmatched": []}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["category"] != "stock_kr":
                continue
            kind, symb, _why = proxies.resolve(row["name"], row["ticker"], UNIVERSE)
            tally[kind].append(f'{row["name"]}→{symb or "-"}')
    for k, v in tally.items():
        print(f"{k}: {len(v)}")
    for k in ("none", "unmatched"):
        for x in tally[k]:
            print(f"  [{k}] {x}")
    for x in tally["proxy"]:
        print("  [proxy]", x)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))

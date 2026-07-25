"""STEP 5 검증: NVDA로 파생 신호 계산 후 최근 6개월간 발생 횟수 확인."""

import pandas as pd

from signal_bot import indicators as ind
from signal_bot import signals as sig

DATA_DIR = "signal_bot/data"
SIX_MONTHS_TRADING_DAYS = 126


def main():
    daily = pd.read_csv(f"{DATA_DIR}/NVDA_daily.csv", parse_dates=["date"])

    daily["rsi"] = ind.rsi(daily["close"])
    daily["mfi"] = ind.mfi(daily["high"], daily["low"], daily["close"], daily["volume"])
    daily = pd.concat([daily, ind.bollinger(daily["close"])], axis=1)

    div_rsi = sig.bullish_divergence(daily["close"], daily["rsi"])
    div_mfi = sig.bullish_divergence(daily["close"], daily["mfi"])
    squeeze_exp = sig.bollinger_squeeze_expansion(daily["bandwidth"])
    mfi_leads = sig.mfi_leads_rsi_rebound(daily["rsi"], daily["mfi"])
    vol_ratio = sig.volume_exhaustion_ratio(daily["volume"])

    daily["div_rsi"] = div_rsi["detected"]
    daily["div_mfi"] = div_mfi["detected"]
    daily["squeeze_exp"] = squeeze_exp
    daily["mfi_leads"] = mfi_leads
    daily["vol_exhaustion"] = vol_ratio < 1.0

    recent = daily.tail(SIX_MONTHS_TRADING_DAYS)

    print(f"=== 최근 {SIX_MONTHS_TRADING_DAYS}거래일(약 6개월) 신호 발생 횟수 ===")
    print(f"RSI 다이버전스   : {int(recent['div_rsi'].sum())}회")
    print(f"MFI 다이버전스   : {int(recent['div_mfi'].sum())}회")
    print(f"볼린저 스퀴즈확장 : {int(recent['squeeze_exp'].sum())}회")
    print(f"MFI 선행반등     : {int(recent['mfi_leads'].sum())}회")
    print(f"거래량 소진      : {int(recent['vol_exhaustion'].sum())}회")

    for name, col in [("RSI 다이버전스", "div_rsi"), ("MFI 다이버전스", "div_mfi"),
                       ("볼린저 스퀴즈확장", "squeeze_exp"), ("MFI 선행반등", "mfi_leads")]:
        dates = recent.loc[recent[col], "date"].dt.strftime("%Y-%m-%d").tolist()
        print(f"\n{name} 발생일: {dates}")


if __name__ == "__main__":
    main()

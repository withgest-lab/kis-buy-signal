"""매수 판단·비트코인 일봉·단계 가드 단위 테스트 (가상 시계열만 사용).

    uv run python -m unittest signal_bot.test_buy_view -v
"""

import unittest

import numpy as np
import pandas as pd

from signal_bot import buy_view as bv
from signal_bot import mdd
from signal_bot.crypto_client import fold_weekends


def _depth(close: np.ndarray) -> np.ndarray:
    return mdd.compute_drawdown(pd.Series(close))["drawdown"].to_numpy()


class MovesTest(unittest.TestCase):
    def test_up_down_net_and_retrace(self):
        # 1년(252봉) 전 100 → 중간 고점 200 → 지금 150
        c = np.concatenate([np.full(10, 90.0), [100.0], np.linspace(100, 200, 120), np.linspace(200, 150, 132)])
        m = bv.moves(c)["252"]
        self.assertAlmostEqual(m["up"], 1.0, places=4)
        self.assertAlmostEqual(m["down"], -0.25, places=4)
        self.assertAlmostEqual(m["net"], 0.5, places=4)
        self.assertAlmostEqual(bv.retrace(c), 0.5, places=4)
        self.assertIsNone(bv.moves(c)["756"])          # 3년치가 없으면 None

    def test_retrace_none_without_rise(self):
        c = np.linspace(200, 100, 300)
        self.assertIsNone(bv.retrace(c))


class DaysDeeperTest(unittest.TestCase):
    def test_share_uses_only_days_before_current_drawdown(self):
        # 4년 동안 0~-40% 오르내린 뒤 신고가, 그 다음 -30% 하락 중
        rng = np.linspace(0, 8 * np.pi, 4 * 252)
        hist = 100 * (1 + 0.2 * np.sin(rng))
        c = np.concatenate([hist, [hist.max() * 1.01], hist.max() * 1.01 * np.linspace(1, 0.7, 30)])
        share, years = bv.days_deeper(_depth(c))
        d = _depth(c)
        start = bv.current_episode_start(d)
        self.assertAlmostEqual(share, float(np.mean(d[:start] <= d[-1])), places=4)
        self.assertGreater(years, 3.9)

    def test_none_at_new_high(self):
        c = np.linspace(100, 200, 900)
        self.assertEqual(bv.days_deeper(_depth(c))[0], None)


class VerdictTest(unittest.TestCase):
    def test_order(self):
        self.assertEqual(bv.verdict(3, False, False, 0.01, 0.0), "unknown")
        self.assertEqual(bv.verdict(3, True, True, 0.01, 0.9), "record")
        self.assertEqual(bv.verdict(2, True, False, 0.01, 0.31), "hot")
        self.assertEqual(bv.verdict(2, True, False, 0.10, 0.30), "strong")
        self.assertEqual(bv.verdict(2, True, False, 0.11, 0.0), "split")
        self.assertEqual(bv.verdict(2, True, False, None, None), "split")
        self.assertEqual(bv.verdict(1, True, False, 0.01, 0.0), "watch")
        self.assertEqual(bv.verdict(0, True, False, 0.5, 0.0), "wait")


class WalkForwardTest(unittest.TestCase):
    def _series(self, seed: int, n: int) -> np.ndarray:
        r = np.random.default_rng(seed).normal(0.0004, 0.02, n)
        return 100 * np.exp(np.cumsum(r))

    def test_no_lookahead(self):
        # 앞 2000봉이 같고 뒤가 다른 두 시계열 - 앞 구간의 매일 판단은 같아야 한다(미래를 안 본다).
        # 약 1년 주기로 오르내리며 신고가를 갱신하는 시계열이라 낙폭 국면이 충분히 쌓여 판단이 실제로 나온다.
        t = np.arange(2600)
        a = 100 * np.exp(0.0006 * t + 0.15 * np.sin(t / 40.0) + np.random.default_rng(1).normal(0, 0.004, len(t)))
        b = np.concatenate([a[:2000], a[1999] * np.exp(np.cumsum(np.random.default_rng(9).normal(-0.003, 0.03, 600)))])
        ta, _ = bv.daily_tiers(a, _depth(a))
        tb, _ = bv.daily_tiers(b, _depth(b))
        self.assertEqual(ta[:2000], tb[:2000])
        self.assertTrue(any(t is not None for t in ta[:2000]))

    def test_summary_shapes(self):
        c = self._series(3, 3000)
        acc = bv.walk_forward(c, _depth(c))
        s = bv.summarize_all(acc)
        self.assertIsNotNone(s["base"])
        self.assertEqual(s["base"]["days"], len(c) - 2 * bv.BARS_1Y)   # 첫 1년 제외 · 마지막 1년은 1년 뒤 결과 없음
        pooled = bv.pool([acc, acc])
        self.assertEqual(pooled["base"]["days"], 2 * s["base"]["days"])

    def test_pick_stats_fallback(self):
        own = {"tiers": {"split": {"n_ep": 3, "med12": 0.1}}, "base": {"med12": 0.05}}
        grp = {"tiers": {"split": {"n_ep": 40, "tickers": 12, "med12": 0.12}}, "base": {"med12": 0.1}}
        self.assertEqual(bv.pick_stats("split", own, grp, "usETF")["src"], "group")
        lone = {"tiers": {"split": {"n_ep": 3, "tickers": 1}}, "base": {"med12": 0.1}}
        st = bv.pick_stats("split", own, lone, "crypto")
        self.assertEqual((st["src"], st.get("few")), ("self", True))
        own["tiers"]["split"]["n_ep"] = 6
        self.assertEqual(bv.pick_stats("split", own, grp, "usETF")["src"], "self")
        self.assertIsNone(bv.pick_stats("unknown", own, grp, "usETF"))


class StageGuardTest(unittest.TestCase):
    def test_stage3_needs_10_episodes(self):
        pct = {"p50": -0.1, "p25": -0.2, "p10": -0.3, "count": 9}
        self.assertEqual(mdd.classify_stage(-0.5, pct), 2)
        pct["count"] = 10
        self.assertEqual(mdd.classify_stage(-0.5, pct), 3)


class SplitMismatchTest(unittest.TestCase):
    def test_detects_split_but_not_dividend_adjustment(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from signal_bot import baseline_fetch as bf
        dates = pd.bdate_range("2026-01-01", periods=300)
        close = pd.Series(np.linspace(100, 150, 300))
        with tempfile.TemporaryDirectory() as tmp:
            data, base = Path(tmp), Path(tmp) / "baseline"
            base.mkdir()
            # SPLT: 베이스라인은 분할 전 값(3배), 운영용은 수정주가 / DIVD: 배당 수정 0.5%만 차이 / NEWX: 베이스라인 없음
            pd.DataFrame({"date": dates, "close": close * 3}).to_csv(base / "SPLT_daily.csv", index=False)
            pd.DataFrame({"date": dates[-250:], "close": close[-250:]}).to_csv(data / "SPLT_daily.csv", index=False)
            pd.DataFrame({"date": dates, "close": close}).to_csv(base / "DIVD_daily.csv", index=False)
            pd.DataFrame({"date": dates[-250:], "close": close[-250:] * 0.995}).to_csv(data / "DIVD_daily.csv", index=False)
            pd.DataFrame({"date": dates[-250:], "close": close[-250:]}).to_csv(data / "NEWX_daily.csv", index=False)
            tickers = [("섹터ETF", "SPLT"), ("섹터ETF", "DIVD"), ("섹터ETF", "NEWX")]
            with mock.patch.object(bf, "BASELINE_DIR", base), mock.patch.object(bf, "DATA_DIR", data), \
                    mock.patch.object(bf, "TICKERS", tickers):
                self.assertEqual(bf.split_mismatch_symbols(), [("섹터ETF", "SPLT")])
                self.assertEqual(bf.missing_symbols(), [("섹터ETF", "NEWX")])


class HistoryFixTest(unittest.TestCase):
    def test_jp_trim_and_isrg_repair_are_idempotent(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from signal_bot import baseline_fetch as bf
        dates = pd.bdate_range("2013-01-01", "2018-12-31")
        jp = pd.DataFrame({"date": dates, "close": np.linspace(0.1, 3000, len(dates))})
        isrg_close = np.linspace(30, 60, len(dates))
        isrg_close[dates >= pd.Timestamp("2017-10-06")] *= 3     # 그날 3배로 튐(이전 값이 1/3로 잘못 수정된 상태)
        isrg = pd.DataFrame({"date": dates, "open": isrg_close, "high": isrg_close, "low": isrg_close,
                             "close": isrg_close, "volume": np.full(len(dates), 300.0)})
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            jp.to_csv(base / "7203_daily.csv", index=False)
            isrg.to_csv(base / "ISRG_daily.csv", index=False)
            tickers = [("일본개별종목", "7203"), ("개별종목", "ISRG")]
            with mock.patch.object(bf, "BASELINE_DIR", base), mock.patch.object(bf, "TICKERS", tickers):
                jumps = bf.split_like_jumps()
                self.assertEqual(list(jumps), ["ISRG"])
                self.assertEqual(jumps["ISRG"][0][0], "2017-10-06")
                self.assertEqual(bf.fix_history(), ["7203", "ISRG"])
                self.assertEqual(bf.fix_history(), [])                  # 두 번째는 바꿀 것 없음
                self.assertEqual(bf.split_like_jumps(), {})
            out_jp = pd.read_csv(base / "7203_daily.csv", parse_dates=["date"])
            self.assertEqual(out_jp["date"].min(), pd.Timestamp("2014-04-01"))
            out = pd.read_csv(base / "ISRG_daily.csv", parse_dates=["date"])
            i = int(out.index[out["date"] == pd.Timestamp("2017-10-06")][0])
            self.assertAlmostEqual(out["close"][i] / out["close"][i - 1], 1.0, delta=0.01)
            self.assertAlmostEqual(out["volume"][0], 100.0)


class FoldWeekendsTest(unittest.TestCase):
    def test_weekend_into_monday_and_trailing_weekend_dropped(self):
        days = pd.date_range("2026-11-06", "2026-11-14")   # 금(6) ~ 토(14)
        raw = pd.DataFrame({"date": days, "open": np.arange(len(days)) + 10.0, "high": np.arange(len(days)) + 20.0,
                            "low": np.arange(len(days)) + 1.0, "close": np.arange(len(days)) + 15.0,
                            "volume": np.ones(len(days))})
        out = fold_weekends(raw)
        self.assertEqual([d.weekday() for d in out["date"]], [4, 0, 1, 2, 3, 4])   # 끝의 토요일(14일)은 월요일 봉이 없어 버림
        mon = out[out["date"] == pd.Timestamp("2026-11-09")].iloc[0]
        self.assertEqual(mon["open"], 11.0)        # 토요일 시가
        self.assertEqual(mon["close"], 18.0)       # 월요일 종가
        self.assertEqual(mon["volume"], 3.0)       # 토·일·월 합
        self.assertEqual(mon["high"], 23.0)


if __name__ == "__main__":
    unittest.main()

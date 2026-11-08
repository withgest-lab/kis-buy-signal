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


def _wave(seed: int, n: int = 2600, phase: float = 0.0) -> np.ndarray:
    """약 1년 주기로 오르내리며 신고가를 갱신하는 가상 시계열(낙폭 국면이 충분히 쌓여 판단이 나온다)."""
    t = np.arange(n)
    return 100 * np.exp(0.0006 * t + 0.15 * np.sin(t / 40.0 + phase) + np.random.default_rng(seed).normal(0, 0.004, n))


def _dates(n: int) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2000-01-03", periods=n)]


class PlanTest(unittest.TestCase):
    def test_n_ep_excludes_episodes_without_outcome(self):
        # 신고가 뒤 150봉 동안 -40% - 이 하락은 1년 뒤 결과가 없으니 어떤 판단의 사례에도 들어가면 안 된다
        a = _wave(1)
        c = np.concatenate([a, [a.max() * 1.05], a.max() * 1.05 * np.linspace(1, 0.6, 150)])
        days = bv.walk_days(c, _depth(c), _dates(len(c)))
        last = int(days["eps"][-1])
        self.assertTrue(last > 0 and any(t is not None for t in days["tiers"][-150:]))
        acc = bv.walk_forward(None, None, days=days)
        for k in bv.TIERS:
            self.assertNotIn(last, acc[k]["eps"])
        self.assertTrue(any(acc[k]["eps"] for k in bv.TIERS))          # 결과가 있는 과거 하락은 그대로 센다

    def test_first_buy_and_next_buy(self):
        tiers = [None, "wait", "watch", "split", "strong", None, "watch", "hot", "watch"]
        eps = np.array([0, 1, 1, 1, 1, 0, 2, 2, 2])
        self.assertEqual(bv.anchor_indices(tiers, eps), [3])
        self.assertIsNone(bv.first_buy_in_episode(tiers, eps))          # 마지막 하락(2)엔 매수 판단이 없음
        self.assertEqual(bv.first_buy_in_episode(tiers, eps, 4), 3)
        nxt = bv._next_buy(tiers, eps)
        self.assertEqual((int(nxt[1]), int(nxt[4]), int(nxt[7])), (3, 4, -1))

    def test_long_drawdown_restarts_plan_every_year(self):
        # 하나의 하락이 3년 넘게 이어지고 매수 판단이 계속 나오면 1년마다 새 1차(3분할은 1년으로 끝난다)
        n = 3 * bv.BARS_1Y + 40
        tiers = [None] + ["split"] * (n - 1)
        eps = np.array([0] + [1] * (n - 1))
        self.assertEqual(bv.anchor_indices(tiers, eps), [1, 1 + bv.BARS_1Y, 1 + 2 * bv.BARS_1Y, 1 + 3 * bv.BARS_1Y])
        self.assertEqual(bv.first_buy_in_episode(tiers, eps), 1 + 3 * bv.BARS_1Y)
        # 1차 뒤 1년 넘게 매수 판단이 다시 안 나오면 그 3분할은 끝 - 기다리기
        tiers2 = [None, "split"] + ["watch"] * (bv.BARS_1Y + 5)
        eps2 = np.array([0] + [1] * (len(tiers2) - 1))
        self.assertIsNone(bv.first_buy_in_episode(tiers2, eps2))
        self.assertEqual(bv.first_buy_in_episode(tiers2, eps2, 100), 1)

    def _plan(self, tier, px, anchor=(290, "split"), stats=None, hot_ok=False, alt=None):
        c = np.full(300, 100.0)
        c[-1] = px
        gplan = {"n": 20, "s2": -0.10, "s3": -0.20, "lump": {"med12": 0.15, "loss": 0.2}, "ladder": None, "hot": None}
        pct = {"p50": -0.08, "p25": -0.15, "p10": -0.25, "count": 12}
        gpool = {"tiers": {"watch": {"med12": 0.05}, "strong": {"med12": 0.2}, "split": {"med12": 0.13}},
                 "base": {"med12": 0.12, "loss": 0.2}}
        stats = stats or {"src": "group", "group": "usETF", "tier": {"n_ep": 30, "tickers": 10, "med12": 0.13,
                          "loss": 0.21, "drop15": 0.3}, "base": {"med12": 0.12, "loss": 0.2, "drop15": 0.2}}
        return bv.plan(tier, c, _dates(300), 120.0, pct, anchor, stats, gplan, gpool, None, "usETF", hot_ok=hot_ok, alt=alt)

    def test_hold_when_evidence_is_worse(self):
        # 매수 판단(깊은 조정)이어도 같은 판단의 과거가 아무 때나보다 나빴으면 '추가 매수 보류' — 칩이 근거와 반대로 말하지 않게
        bad = {"src": "group", "group": "krStock", "tier": {"n_ep": 66, "tickers": 20, "med12": -0.004, "loss": 0.50, "drop15": 0.44},
               "base": {"med12": 0.069, "loss": 0.42, "drop15": 0.42}}
        p = self._plan("split", 95, stats=bad, alt={"price": 80.0, "gap": -0.158})
        self.assertEqual((p["state"], p["why"], p["cond"]["kind"], p["cond"]["price"]), ("hold", "noedge", "rare", 80.0))
        self.assertTrue(p["notes"].get("hold"))
        self.assertFalse(p["aggr"])
        # 비슷한데 손해 확률만 높아도 보류, 비슷·비슷이면 그대로 1차
        same_hi = {**bad, "tier": {**bad["tier"], "med12": 0.08, "loss": 0.46}}
        self.assertEqual(self._plan("split", 95, stats=same_hi)["state"], "hold")
        self.assertEqual(self._plan("split", 95)["state"], "t1")

    def test_plan_until_is_one_year_after_first(self):
        p = self._plan("split", 95)
        d1 = p["t1"]["date"]
        self.assertEqual(p["t1"]["until"][:4], str(int(d1[:4]) + 1))
        self.assertEqual(p["t1"]["until"][4:], d1[4:])

    def test_hot_rule_follows_its_evidence(self):
        risky = {"tier": {"med12": 0.20, "loss": 0.22, "drop15": 0.30}, "base": {"med12": 0.18, "loss": 0.22, "drop15": 0.24}}
        calm = {"tier": {"med12": 0.20, "loss": 0.22, "drop15": 0.24}, "base": {"med12": 0.18, "loss": 0.22, "drop15": 0.24}}
        self.assertTrue(bv.hot_supported(risky))       # 산 뒤 추가 하락이 더 잦았다 → 급등 뒤엔 기다리기
        self.assertFalse(bv.hot_supported(calm))       # 추가 하락도 1년 뒤도 나쁘지 않았다 → 깊이 판단으로
        self.assertTrue(bv.hot_supported(None))
        # hot_ok면 급등 뒤도 매수 판단: 오늘이 1차
        st = {"src": "self", "group": "crypto", "tier": {"n_ep": 4, "med12": 1.0, "loss": 0.4, "drop15": 0.33},
              "base": {"med12": 0.5, "loss": 0.32, "drop15": 0.55}}
        p = self._plan("hot", 100, anchor=(299, "hot"), stats=st, hot_ok=True)
        self.assertEqual((p["state"], p["why"]), ("t1", "hot"))
        self.assertEqual(bv.current_anchor(None, _dates(5), np.array([0, -0.1, -0.2, -0.25, -0.3]), "hot", extra=("hot",)), (4, "hot"))
        self.assertEqual(bv.current_anchor(None, _dates(5), np.array([0, -0.1, -0.2, -0.25, -0.3]), "hot"), (None, None))

    def test_scale_for_vol(self):
        g = {"s2": -0.11, "s3": -0.23, "vol_med": 0.28, "src": "all"}
        self.assertEqual(bv.scale_for_vol(g, 0.20), g)                     # 덜 출렁이면 그대로(좁히지 않음)
        s = bv.scale_for_vol(g, 0.56)
        self.assertEqual((s["s2"], s["s3"], s["scaled"]), (-0.22, -0.46, 2.0))
        s = bv.scale_for_vol(g, 2.8)                                         # 2.5배 한도, 3차 -80% 한도
        self.assertEqual((s["scaled"], s["s2"], s["s3"]), (2.5, -0.275, -0.575))
        self.assertEqual(bv.scale_for_vol(g, None), g)

    def test_plan_states(self):
        self.assertEqual(self._plan("split", 95)["state"], "t1")
        p2 = self._plan("split", 89)
        self.assertEqual((p2["state"], p2["lv"]["t2"], p2["lv"]["t3"]), ("t2", 90.0, 80.0))
        self.assertEqual(self._plan("split", 79)["state"], "t3")
        rb = self._plan("watch", 104)                                   # 1차가보다 3% 넘게 반등 + 지금은 매수 판단 아님
        self.assertEqual((rb["state"], rb["why"], rb["cond"]["kind"], rb["cond"]["price"]), ("wait", "rebound", "rebound", 100.0))
        near = self._plan("watch", 102)
        self.assertEqual((near["state"], near["why"], near["ev"]["src"]), ("t1", "split", "anchor"))   # 근거 = 묶음 1차 신호 결과
        hot = self._plan("hot", 100, anchor=(None, None))
        self.assertEqual((hot["state"], hot["cond"]["kind"]), ("wait", "hot"))
        w = self._plan("watch", 110, anchor=(None, None))
        self.assertEqual((w["state"], w["cond"]["kind"], w["cond"]["price"]), ("wait", "stage2", 102.0))
        self.assertIn("watch", w["notes"])                              # 묶음에서 관찰 단계가 아무 날보다 못했음
        self.assertEqual(self._plan("unknown", 90)["state"], "unknown")

    def test_aggr_needs_better_history(self):
        good = {"src": "self", "group": "usStock", "tier": {"n_ep": 7, "med12": 0.31, "loss": 0.05, "drop15": 0.33},
                "base": {"med12": 0.26, "loss": 0.17, "drop15": 0.2}}
        self.assertTrue(self._plan("strong", 95, anchor=(290, "strong"), stats=good)["aggr"])
        self.assertFalse(self._plan("split", 95, stats=good)["aggr"])     # 적극 매수 검토만
        self.assertFalse(self._plan("strong", 95, anchor=(290, "strong"))["aggr"])   # 과거가 아무 날과 비슷하면 아님

    def test_hot_release(self):
        c = np.full(300, 100.0)
        c[48:53] = [102, 104, 106, 107, 108]       # 1년 전 기준가(c[-253]=100)가 하루씩 밀리며 오른다
        c[-1] = 140.0
        hr = bv.hot_release(c)
        self.assertAlmostEqual(hr["price"], 130.0)
        self.assertAlmostEqual(hr["gap"], 130 / 140 - 1, places=4)
        self.assertEqual(hr["days"], 5)                                 # 140/108 = 1.296 ≤ 1.30

    def test_compare_boundaries(self):
        self.assertEqual(bv.compare({"med12": 0.15, "loss": 0.20}, {"med12": 0.12, "loss": 0.23}),
                         {"med": "better", "loss": "lower"})
        self.assertEqual(bv.compare({"med12": 0.14, "loss": 0.21}, {"med12": 0.12, "loss": 0.20}),
                         {"med": "same", "loss": "same"})
        self.assertEqual(bv.compare({"med12": 0.08, "loss": 0.30}, {"med12": 0.12, "loss": 0.20}),
                         {"med": "worse", "loss": "higher"})

    def test_plan_stats_shapes(self):
        walks = []
        for seed in range(4):
            c = _wave(seed, 3000, phase=seed * 1.3)
            walks.append(bv.walk_days(c, _depth(c), _dates(len(c))))
        p = bv.plan_stats(walks)
        self.assertGreaterEqual(p["n"], 1)
        self.assertLessEqual(p["s3"], p["s2"])
        self.assertLessEqual(p["s2"], 0)
        if p["ladder"]:
            self.assertLessEqual(p["ladder"]["n"], p["n"])
            self.assertLessEqual(p["ladder"]["f3"], p["ladder"]["f2"])


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

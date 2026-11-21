"""공포·탐욕 지수 병합·저장 이력 발행, 기준금리 회의 일정 단위 테스트 (가상 값만, 네트워크 없음).

    uv run python -m unittest signal_bot.test_fng_rates -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from signal_bot import fng, rates


def _payload(n=120, start=2011):
    return {"data": [[f"{start + i // 300}-{1 + (i // 25) % 12:02d}-{1 + i % 25:02d}", 50 + (i % 7), 2] for i in range(n)]}


class FngTest(unittest.TestCase):
    def test_parse_rounds_sorts_and_filters(self):
        p = {"data": [["2010-12-29", 67.04, 3], ["2010-12-27", "68", 3], ["bad", 1, 0], ["2010-12-28", 140, 4]] + _payload()["data"]}
        rows = fng.parse_rows(p)
        self.assertEqual(rows[0], ["2010-12-27", 68.0])                 # 문자열 점수도 읽고, 날짜순
        self.assertIn(["2010-12-29", 67.0], rows)                       # 소수 1자리
        self.assertNotIn("2010-12-28", [d for d, _ in rows])          # 0~100 밖은 버림
        self.assertNotIn("bad", [d for d, _ in rows])
        self.assertEqual(rows, sorted(rows))

    def test_parse_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            fng.parse_rows({"rows": []})
        with self.assertRaises(ValueError):
            fng.parse_rows({"data": [["2011-01-03", 50, 2]]})            # 너무 적음

    def test_merge_overwrites_and_keeps_old(self):
        merged = fng.merge([["2010-12-31", 40.0], ["2011-01-03", 60.0]], [["2011-01-03", 61.5], ["2011-01-04", 62.0]])
        self.assertEqual(merged, [["2010-12-31", 40.0], ["2011-01-03", 61.5], ["2011-01-04", 62.0]])

    def test_write_falls_back_to_history_when_fetch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist = Path(tmp) / "fng_history.json"
            hist.write_text(json.dumps({"data": [["2026-11-20", 9.7]]}), encoding="utf-8")
            out = Path(tmp) / "fng.json"
            with mock.patch.object(fng, "HISTORY_PATH", hist):
                def boom():
                    raise RuntimeError("offline")
                n, stale = fng.write(out, fetch=boom)
            self.assertTrue(stale)
            self.assertEqual(n, 1)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["data"], [["2026-11-20", 9.7]])

    def test_write_merges_and_saves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist = Path(tmp) / "fng_history.json"
            out = Path(tmp) / "fng.json"
            with mock.patch.object(fng, "HISTORY_PATH", hist):
                n, stale = fng.write(out, fetch=lambda: _payload())
            self.assertFalse(stale)
            self.assertEqual(n, len(json.loads(hist.read_text(encoding="utf-8"))["data"]))


class MeetingsTest(unittest.TestCase):
    def test_meetings_sorted_unique_and_cover_rate_changes(self):
        m = rates.load_meetings()
        self.assertEqual(m, sorted(set(m)))
        self.assertGreater(len(m), 150)
        # 2007년 이후 금리가 바뀐 날은 모두 정례 회의 0~3일 뒤이거나, 알려진 정례 밖 변경 4번
        from datetime import date
        steps = json.loads(rates.SEED_PATH.read_text(encoding="utf-8"))["steps"]
        md = [date.fromisoformat(x) for x in m]
        off = [d for d, *_ in steps if d >= "2007" and not any(0 <= (date.fromisoformat(d) - x).days <= 3 for x in md)]
        self.assertEqual(off[:4], ["2008-01-22", "2008-10-08", "2020-03-04", "2020-03-16"])


if __name__ == "__main__":
    unittest.main()

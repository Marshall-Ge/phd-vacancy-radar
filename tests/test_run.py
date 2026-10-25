from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from phd_radar.models import Batch, Position, SourceResult
from phd_radar.run import run
from phd_radar.state import State, load_state, save_state
from phd_radar.timeutil import now_utc

CONFIG = """
[profile]
name = "test"
topics = ["information systems", "digital transformation", "management and organization"]
core_topics = ["information systems", "digital transformation", "management and organization"]
methods = ["quantitative"]
domain_terms = ["management", "digital", "data"]
country_bonus = { NL = 3.0, UK = 1.0 }

[monitor]
digest_every_days = 5
digest_hour = 0
timezone = "Asia/Shanghai"
alert_score = 6.0
award_alert_score = 8.0
startup_email = true
state_file = "state.json"

[notify]
provider = "none"
to = ["test@example.com"]
"""


def make_position(pid: str = "p1", title: str = "PhD in Information Systems") -> Position:
    return Position(
        id=pid,
        title=title,
        institution="TU Delft",
        country="NL",
        url=f"https://example.com/{pid}",
        source="test",
        published=now_utc() - timedelta(days=1),
        deadline=now_utc() + timedelta(days=20),
        salary="EUR 3204 gross",
        description="digital transformation and management",
    )


class RunFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "config.toml").write_text(CONFIG, encoding="utf-8")
        self.args = argparse.Namespace(mode="check", config=str(self.dir / "config.toml"), dry_run=False, verbose=False)
        self.state_path = self.dir / "state.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, positions):
        batch = Batch(
            positions=positions,
            awards=[],
            sources=[SourceResult(name="test", kind="test", ok=True, positions=positions)],
        )
        with mock.patch("phd_radar.run.collect", return_value=batch), mock.patch(
            "phd_radar.run.send_email", return_value="none"
        ) as sender:
            code = run(self.args)
        return code, [c.args[1] for c in sender.call_args_list]

    def test_first_run_baseline_no_alert(self):
        code, subjects = self._run([make_position("p1")])
        self.assertEqual(code, 0)
        self.assertEqual(len(subjects), 1)
        self.assertIn("监控已启动", subjects[0])
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertTrue(state["first_run_done"])
        self.assertIn("p1", state["seen_positions"])

    def test_new_high_score_sends_alert(self):
        self._run([make_position("p1")])
        code, subjects = self._run([make_position("p1"), make_position("p2")])
        self.assertEqual(code, 0)
        self.assertTrue(any("新项目" in s for s in subjects), subjects)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIn("p2", state["alerted"])

    def test_stop_pauses_and_resume(self):
        self._run([make_position("p1")])
        self.args.mode = "stop"
        with mock.patch("phd_radar.run.collect", side_effect=AssertionError("should not collect")):
            code = run(self.args)
        self.assertEqual(code, 0)
        state, _ = load_state(self.state_path)
        self.assertTrue(state.paused)

        self.args.mode = "check"
        with mock.patch("phd_radar.run.collect", side_effect=AssertionError("should not collect")):
            code = run(self.args)
        self.assertEqual(code, 0)

        self.args.mode = "resume"
        code = run(self.args)
        self.assertEqual(code, 0)
        state, _ = load_state(self.state_path)
        self.assertFalse(state.paused)

    def test_reset_clears_state(self):
        self._run([make_position("p1")])
        self.args.mode = "reset"
        code = run(self.args)
        self.assertEqual(code, 0)
        state, _ = load_state(self.state_path)
        self.assertEqual(state.seen_positions, {})
        self.assertFalse(state.first_run_done)
        self.assertFalse(state.paused)

    def test_digest_after_five_days(self):
        self._run([make_position("p1")])
        state, _ = load_state(self.state_path)
        state.last_digest_at = now_utc() - timedelta(days=6)
        save_state(self.state_path, state)
        code, subjects = self._run([])
        self.assertEqual(code, 0)
        self.assertTrue(any(("汇总" in s or "本期无新增" in s) for s in subjects), subjects)


if __name__ == "__main__":
    unittest.main()

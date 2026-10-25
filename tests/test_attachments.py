from __future__ import annotations

import csv
import io
import unittest
from datetime import datetime, timedelta, timezone

from phd_radar.config import Monitor, Notify, load_config
from phd_radar.models import Award, Position
from phd_radar.report import build_attachments, build_csv

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def sample_data():
    pos = Position(
        id="p1", title="PhD in Information Systems", institution="TU Delft", country="NL",
        url="https://example.com/p1", source="AT", published=NOW, deadline=NOW + timedelta(days=20),
        salary="EUR 3204", description="digital transformation", topics=["information systems"],
        methods=["quantitative"], score=7.5,
    )
    award = Award(
        id="a1", title="Digital Platform Project", pi="Prof X", institution="Uni Y", country="DE",
        programme="DFG", url="https://example.com/a1", source="GEPRIS", start_year=2026,
        end_year=2028, summary="platform governance", topics=["information systems"], score=9.0,
    )
    return [pos], [award]


class AttachmentTests(unittest.TestCase):
    def test_csv_has_bom_and_rows(self):
        positions, awards = sample_data()
        data = build_csv(positions, awards)
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(rows[0][0], "类型")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], "项目")
        self.assertEqual(rows[2][0], "funding")

    def test_both_attachments(self):
        cfg = load_config("config.toml")
        cfg.monitor = Monitor(digest_attachment="both")
        positions, awards = sample_data()
        files = build_attachments(cfg, positions, awards, NOW)
        names = [f.filename for f in files]
        self.assertEqual(len(files), 2)
        self.assertTrue(names[0].endswith(".csv"))
        self.assertTrue(names[1].endswith(".html"))
        self.assertIn(b"PhD in Information Systems", files[1].content)

    def test_none_mode(self):
        cfg = load_config("config.toml")
        cfg.monitor = Monitor(digest_attachment="none")
        positions, awards = sample_data()
        self.assertEqual(build_attachments(cfg, positions, awards, NOW), [])


if __name__ == "__main__":
    unittest.main()

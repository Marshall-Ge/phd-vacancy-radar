from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from phd_radar.config import Profile
from phd_radar.models import Award, Position
from phd_radar.scoring import score_award, score_position
from phd_radar.textutil import infer_country, match_topics, parse_loose_date

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
PROFILE = Profile(
    topics=[
        "information systems",
        "digital transformation",
        "business analytics",
        "management and organization",
        "artificial intelligence",
        "platform",
    ],
    methods=["quantitative", "causal inference", "experiment"],
    core_topics=["information systems", "digital transformation", "business analytics", "management and organization", "platform"],
    domain_terms=["management", "business", "digital", "data", "analytics"],
    negative_domains=["law", "legal", "biology", "physics"],
    country_bonus={"NL": 3.0, "DK": 3.0, "DE": 2.0, "UK": 1.0},
)


def make_position(title: str, country: str = "NL", description: str = "") -> Position:
    return Position(
        id="x",
        title=title,
        institution="Test University",
        country=country,
        url="https://example.com",
        source="test",
        published=NOW - timedelta(days=1),
        deadline=NOW + timedelta(days=20),
        salary="€3,204 gross",
        description=description,
    )


class TextTests(unittest.TestCase):
    def test_ai_word_boundary(self):
        self.assertEqual(match_topics("decision-making under certainty", PROFILE.topics), [])
        self.assertIn("artificial intelligence", match_topics("PhD in AI governance", PROFILE.topics))

    def test_country_inference(self):
        self.assertEqual(infer_country("Technical University of Denmark"), "DK")
        self.assertEqual(infer_country("TU Delft"), "NL")
        self.assertEqual(infer_country("University of Warwick"), "UK")
        self.assertEqual(infer_country("Frankfurt School of Finance"), "DE")

    def test_date_parsing(self):
        self.assertEqual(parse_loose_date("9 Nov ’26").year, 2026)
        self.assertEqual(parse_loose_date("2026-11-09").month, 11)


class ScoringTests(unittest.TestCase):
    def test_relevant_nl_position(self):
        pos = score_position(make_position("PhD in Information Systems and Digital Transformation"), PROFILE, NOW)
        self.assertGreaterEqual(pos.score, 7.0)

    def test_engineering_title_dropped(self):
        pos = score_position(
            make_position("PhD in Digital Twins for Flood-Resilient Infrastructure", description="asset management"),
            PROFILE,
            NOW,
        )
        self.assertEqual(pos.score, 0.0)

    def test_negative_domain_penalty(self):
        pos = score_position(
            make_position("PhD in Law and Digital Transformation", description="legal system"),
            PROFILE,
            NOW,
        )
        self.assertLess(pos.score, 6.0)

    def test_award_requires_core_topic(self):
        award = Award(
            id="a",
            title="Digitalisation in legal professions",
            pi="Prof X",
            institution="Uni",
            country="DE",
            programme="DFG",
            url="https://example.com",
            source="test",
            summary="law and legal system",
            start_year=2025,
            end_year=2027,
        )
        self.assertEqual(score_award(award, PROFILE, NOW).score, 0.0)


if __name__ == "__main__":
    unittest.main()

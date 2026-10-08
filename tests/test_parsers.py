import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from crawler.fetching import classify
from crawler.parsers import ExtractionError, IneligibleListing, discover, expired_page, parse_detail, salary


FIXTURES = Path(__file__).with_name("fixtures")
LINKEDIN = "https://uk.linkedin.com/jobs/view/software-engineer-iii-java-at-jpmorganchase-4447742577"
REED = "https://www.reed.co.uk/jobs/software-engineer/57336545"
CLOCK = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.linkedin = (FIXTURES / "linkedin-detail.html").read_text()
        self.reed = (FIXTURES / "reed-detail.html").read_text()

    def test_linkedin_board_identity_and_visible_description(self):
        listing = parse_detail("linkedin", self.linkedin, LINKEDIN, CLOCK).content
        self.assertEqual(listing["source_job_id"], "4447742577")
        self.assertEqual(listing["location"], "Glasgow, Scotland, United Kingdom")
        self.assertEqual(listing["work_type"], "full time")
        self.assertEqual(listing["description"], "Build secure Python services.\nDesign reliable systems.\nWork with engineers.")
        self.assertIn("company-logo_100_100", listing["company_logo_url"])
        self.assertNotIn("&amp;", listing["company_logo_url"])

    def test_reed_visible_fields_override_structured_or_related_fields(self):
        listing = parse_detail("reed", self.reed, REED, CLOCK).content
        self.assertEqual(listing["location"], "Taunton, Somerset")
        self.assertEqual(listing["company"], "IBM SIXworks Limited")
        self.assertEqual(listing["work_type"], "contract")
        self.assertIsNone(listing["salary_min"])
        self.assertNotIn("Full job description", listing["description"])
        self.assertNotIn("Unrelated", listing["description"])

    def test_visible_salary_units_and_single_or_one_sided_ranges(self):
        self.assertEqual(salary("£350 - £500 per day", {}), (Decimal(350), Decimal(500), "day"))
        self.assertEqual(salary("£40k - £60k per annum", {}), (Decimal(40000), Decimal(60000), "year"))
        self.assertEqual(salary("Up to £25 per hour", {}), (None, Decimal(25), "hour"))
        self.assertEqual(salary("From £60,000 per annum", {}), (Decimal(60000), None, "year"))
        self.assertEqual(salary("£70,000 per annum", {}), (Decimal(70000), Decimal(70000), "year"))
        self.assertEqual(salary("£50,000 - 60,000 per annum plus £10,000 bonus", {}),
                         (Decimal(50000), Decimal(60000), "year"))
        self.assertEqual(salary("£40-60k per annum", {}), (Decimal(40000), Decimal(60000), "year"))

    def test_training_course_is_not_a_vacancy(self):
        with self.assertRaisesRegex(IneligibleListing, "training_course"):
            parse_detail("reed", self.reed.replace("Competitive salary", "Training Course"), REED, CLOCK)

    def test_non_uk_and_ambiguous_remote_are_rejected(self):
        foreign = self.linkedin.replace('"addressCountry": "GB"', '"addressCountry": "US"')
        with self.assertRaises(IneligibleListing):
            parse_detail("linkedin", foreign, LINKEDIN, CLOCK)
        remote = foreign.replace("Glasgow, Scotland, United Kingdom</span>", "Remote</span>")
        with self.assertRaises(IneligibleListing):
            parse_detail("linkedin", remote, LINKEDIN, CLOCK)
        eligible = remote.replace('"employmentType": "FULL_TIME"',
                                  '"applicantLocationRequirements": {"name": "United Kingdom"}, "employmentType": "FULL_TIME"')
        self.assertEqual(parse_detail("linkedin", eligible, LINKEDIN, CLOCK).content["location"], "Remote")
        restricted = self.linkedin.replace('"employmentType": "FULL_TIME"',
                                           '"applicantLocationRequirements": {"name": "United States"}, "jobLocationType": "TELECOMMUTE", "employmentType": "FULL_TIME"')
        with self.assertRaises(IneligibleListing):
            parse_detail("linkedin", restricted, LINKEDIN, CLOCK)

    def test_canonical_id_mismatch_is_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_detail("linkedin", self.linkedin, LINKEDIN.replace("4447742577", "12345"), CLOCK)

    def test_relative_date_estimate_is_stable_across_refreshes(self):
        page = self.linkedin.replace('"datePosted": "2026-10-05T09:50:50Z",', "")
        first = parse_detail("linkedin", page, LINKEDIN, CLOCK)
        self.assertEqual(first.content["posted_at"], CLOCK - timedelta(days=2))
        refreshed = parse_detail("linkedin", page.replace("2 days ago", "3 days ago"), LINKEDIN,
                                 CLOCK + timedelta(days=1), first.content["posted_at"])
        self.assertEqual(first.content_hash, refreshed.content_hash)

    def test_related_expired_job_is_not_current_listing_removal(self):
        self.assertFalse(expired_page("linkedin", self.linkedin))
        page = self.linkedin.replace("</body>", '<span class="topcard__flavor--closed">No longer accepting applications</span></body>')
        self.assertTrue(expired_page("linkedin", page))

    def test_challenge_with_http_200_is_blocked(self):
        self.assertIsNotNone(classify(200, "<title>Additional Verification Required</title>"))
        self.assertIsNone(classify(200, self.linkedin))

    def test_discovery_dedupes_tracking_links_and_ignores_external_urls(self):
        page = f'<a href="{REED}?tracking=one">Job</a><a href="{REED}?tracking=two">Job</a>'
        page += '<a href="https://example.com/jobs/software-engineer/57336545">External</a>'
        found, _ = discover("reed", page, "https://www.reed.co.uk/jobs/software-engineer-jobs")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].url, REED)


if __name__ == "__main__":
    unittest.main()

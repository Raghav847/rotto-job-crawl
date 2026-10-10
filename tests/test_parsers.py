import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from crawler.fetching import classify
from crawler.parsers import ExtractionError, IneligibleListing, description_salary, discover, expired_page, parse_detail, plain_description, salary


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

    def test_source_employer_reference_is_bound_and_separate_from_board_identity(self):
        listing = parse_detail("linkedin", self.linkedin, LINKEDIN, CLOCK)
        self.assertEqual(listing.matching_evidence, {"kind": "jsonld_employer_reference", "issuer": "JPMorganChase", "reference": "210773394"})
        self.assertEqual(listing.content["source_job_id"], "4447742577")
        board_id = self.linkedin.replace('"value": "210773394"', '"value": "4447742577"')
        self.assertIsNone(parse_detail("linkedin", board_id, LINKEDIN, CLOCK).matching_evidence)
        wrong_issuer = self.linkedin.replace('"name": "JPMorganChase", "value"', '"name": "Unrelated Employer", "value"')
        self.assertIsNone(parse_detail("linkedin", wrong_issuer, LINKEDIN, CLOCK).matching_evidence)
        self.assertIsNone(parse_detail("reed", self.reed, REED, CLOCK).matching_evidence)

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
        self.assertEqual(salary("£100,000.00/yr - £130,000.00/yr", {}),
                         (Decimal(100000), Decimal(130000), "year"))
        self.assertEqual(salary("£25/hr - £30/hr", {}), (Decimal(25), Decimal(30), "hour"))
        self.assertEqual(salary("£350 - £500 Annual leave Full-time", {}),
                         (Decimal(350), Decimal(500), None))

    def test_description_pay_is_extracted_without_guessing_period(self):
        self.assertEqual(description_salary("Salary: £61,500 - £78,800\nThe Role\nBuild systems.\nPay Range\n£61,500.00-£78,800.00"),
                         (Decimal(61500), Decimal(78800), None))
        page = self.linkedin.replace("Build <strong>secure</strong> Python services.",
                                     "Salary: £61,500 - £78,800. Build secure Python services.")
        result = parse_detail("linkedin", page, LINKEDIN, CLOCK).content
        self.assertEqual(result["salary_min"], 61500)
        self.assertEqual(result["salary_max"], 78800)
        self.assertIsNone(result["salary_period"])

    def test_explicit_gbp_prefix_and_suffix_ranges(self):
        self.assertEqual(salary("GBP 111k - 145k per year", None), (Decimal(111000), Decimal(145000), "year"))
        self.assertEqual(description_salary("Starting salary: 111K - 145K GBP + RSUs"),
                         (Decimal(111000), Decimal(145000), None))
        self.assertEqual(description_salary("Salary: 111K - 145K USD"), (None, None, None))
        self.assertEqual(description_salary("Salary and benefits include 3600 GBP free shares each year."),
                         (None, None, None))

    def test_redundant_thousands_notation_requires_source_corroboration(self):
        description = "Starting salary: £111,000 - £145,000k + RSUs\nStarting salary: 111K - 145K GBP + RSUs"
        self.assertEqual(description_salary(description), (Decimal(111000), Decimal(145000), None))
        # Preserve the literal source amount without arbitrary caps or guessing when alone.
        self.assertEqual(description_salary("Salary: £111,000 - £145,000k"),
                         (Decimal(111000), Decimal(145000000), None))

    def test_unresolved_explicit_salary_conflicts_remain_null(self):
        self.assertEqual(description_salary("Salary: £111,000 - £145,000k\nSalary: 112K - 150K GBP"),
                         (None, None, None))

    def test_description_benefits_and_assets_are_not_salary(self):
        for sentence in (
            "Competitive salary. Colleagues receive up to £3,600 of free shares each year.",
            "Our company manages £121.5 billion of assets. We offer competitive salary.",
            "Salary and benefits include £3,600 free shares each year.",
            "Salary benefits include an annual bonus of £10,000.",
        ):
            with self.subTest(sentence=sentence):
                self.assertEqual(description_salary(sentence), (None, None, None))

    def test_dedicated_pay_range_takes_precedence_over_conflicting_description(self):
        page = self.linkedin.replace("</body>", '<div class="compensation__salary">£100,000.00/yr - £130,000.00/yr</div></body>')
        page = page.replace("Build <strong>secure</strong> Python services.", "Salary: up to £140,000 a year. Build secure services.")
        result = parse_detail("linkedin", page, LINKEDIN, CLOCK).content
        self.assertEqual((result["salary_min"], result["salary_max"], result["salary_period"]), (100000, 130000, "year"))

    def test_adjacent_inline_words_remain_readable(self):
        self.assertEqual(plain_description("<p>You <span>can</span><strong>inspire</strong><em>change</em>.</p>"),
                         "You can inspire change.")
        self.assertEqual(plain_description("<p>At <strong>Example</strong>, build services.</p>"),
                         "At Example, build services.")

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

    def test_mandatory_overseas_relocation_overrides_uk_recruitment_metadata(self):
        page = self.linkedin.replace("Software Engineer III - Java", "Software Engineer - Australia")
        page = page.replace("Build <strong>secure</strong> Python services.",
                            "You must be genuine about wanting to move to Australia. These positions are based in Melbourne.")
        with self.assertRaises(IneligibleListing):
            parse_detail("linkedin", page, LINKEDIN, CLOCK)
        # An overseas market/company mention without mandatory relocation remains UK.
        page = page.replace("You must be genuine about wanting to move to Australia.", "Support our Australia market from the Glasgow office.")
        page = page.replace("These positions are based in Melbourne.", "These positions are based in Glasgow.")
        self.assertEqual(parse_detail("linkedin", page, LINKEDIN, CLOCK).content["location"], "Glasgow, Scotland, United Kingdom")

    def test_between_salary_and_related_vacancy_footer(self):
        self.assertEqual(description_salary("Salary£85,000 - £100,000\nSalary between £85,000 and £100,000, depending on experience."),
                         (Decimal(85000), Decimal(100000), None))
        text = plain_description("<p>Build the main role.</p><p>Application guidance.</p><h2>More technology opportunities</h2><p>Related data role £60,000 View role</p><p>Other role £90,000 View role</p>")
        self.assertEqual(text, "Build the main role.\nApplication guidance.")

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

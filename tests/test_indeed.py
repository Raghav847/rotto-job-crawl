import unittest
import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.indeed import parse_embedded
from crawler.parsers import ExtractionError, IneligibleListing, discover, expired_page, parse_detail


PAGE = Path(__file__).with_name("fixtures") / "indeed-detail.html"
CLOCK = datetime(2026, 10, 8, tzinfo=timezone.utc)
URL = "https://uk.indeed.com/jobs?q=engineer&l=United+Kingdom&vjk=selected456"


class IndeedParserTests(unittest.TestCase):
    def setUp(self):
        self.page = PAGE.read_text()

    def test_selected_pane_identity_and_exact_description_boundaries(self):
        row = parse_detail("indeed", self.page, URL, CLOCK).content
        self.assertEqual(row["source_job_id"], "selected456")
        self.assertEqual(row["title"], "Python Engineer")
        self.assertEqual(row["company"], "Example Engineering")
        self.assertEqual(row["location"], "Manchester")
        self.assertEqual(row["description"], "Build Python services for a UK engineering team.\nMaintain reliable systems.")
        self.assertEqual(row["salary_min"], 60000)
        self.assertEqual(row["salary_max"], 80000)
        self.assertEqual(row["work_type"], "full time")
        self.assertEqual(row["posted_at"], datetime(2026, 10, 2, tzinfo=timezone.utc))
        self.assertEqual(row["company_logo_url"], "https://cdn.example.org/company-logo.png")

    def test_different_requested_id_cannot_receive_default_pane_content(self):
        with self.assertRaises(ExtractionError):
            parse_detail("indeed", self.page, URL.replace("selected456", "other123"), CLOCK)

    def test_job_country_not_board_locale_is_eligibility_evidence(self):
        soup = BeautifulSoup(self.page, "html.parser")
        script = soup.select_one("#mosaic-data")
        script.string = script.get_text().replace('"jobkey":"selected456","country":"GB"', '"jobkey":"selected456","country":"US"')
        with self.assertRaises(IneligibleListing):
            parse_detail("indeed", str(soup), URL, CLOCK)

    def test_missing_full_pane_and_expired_metadata_are_rejected(self):
        with self.assertRaises(ExtractionError):
            parse_embedded("<h1>Search cards only</h1>", CLOCK)
        with self.assertRaises(IneligibleListing):
            parse_detail("indeed", self.page.replace('"expired":false', '"expired":true'), URL, CLOCK)

    def test_rendered_logo_identity_must_match_html_snapshot(self):
        with self.assertRaises(ExtractionError):
            parse_detail("indeed", self.page, URL, CLOCK,
                         rendered_metadata={"source_job_id": "other123", "company_logo_url": "https://cdn.example.org/other.png"})

    def test_sponsored_card_ids_do_not_depend_on_opaque_click_urls(self):
        rows, _ = discover("indeed", self.page, "https://uk.indeed.com/jobs")
        self.assertEqual([row.source_job_id for row in rows], ["other123", "selected456"])
        self.assertEqual(rows[1].url, "https://uk.indeed.com/viewjob?jk=selected456")

    def test_banner_is_not_used_as_a_logo(self):
        soup = BeautifulSoup(self.page, "html.parser")
        soup.select_one("[data-testid='company-logo']").decompose()
        row = parse_detail("indeed", str(soup), URL, CLOCK).content
        self.assertIsNone(row["company_logo_url"])

    def test_expired_flag_applies_only_to_the_identified_selected_job(self):
        expired = self.page.replace('"expired":false', '"expired":true')
        self.assertTrue(expired_page("indeed", expired, "selected456"))
        self.assertFalse(expired_page("indeed", expired, "other123"))

    def test_image_set_logo_uses_logo_url_not_banner(self):
        page = self.page.replace('background-image:url("https://cdn.example.org/company-logo.png")',
                                 'background-image:image-set(url("https://cdn.example.org/company-logo.png") 1x)')
        self.assertEqual(parse_detail("indeed", page, URL, CLOCK).content["company_logo_url"],
                         "https://cdn.example.org/company-logo.png")

    def test_branding_json_supplies_logo_when_image_loading_is_disabled(self):
        page = self.page.replace('<div data-testid="company-logo">',
                                 '<div data-testid="company-logo" aria-label="Example Engineering logo">')
        page = page.replace('background-image:url("https://cdn.example.org/company-logo.png")', "background-image:none")
        page = page.replace("</head>", '<script>const branding={"logoAltText":"Example Engineering logo","logoUrl":"https://cdn.example.org/square-logo.png"};</script></head>')
        row = parse_detail("indeed", page, URL, CLOCK, rendered_metadata={"source_job_id": "selected456", "logo_present": True}).content
        self.assertEqual(row["company_logo_url"], "https://cdn.example.org/square-logo.png")

    def test_selected_job_not_in_search_results_uses_bound_view_payload(self):
        soup = BeautifulSoup(self.page, "html.parser")
        soup.select_one("#mosaic-data").decompose()
        payload = {"jobKey": "selected456", "jobCountry": "GB", "country": "US", "loggedIn": False,
                   "datePublished": None, "jobLocation": "Manchester",
                   "jobInfoWrapperModel": {"jobInfoModel": {
                       "jobInfoHeaderModel": {"formattedLocation": "Manchester", "companyName": "Example Engineering", "remoteLocation": False},
                       "showExpiredHeader": False}}}
        script = soup.new_tag("script")
        script.string = "const view = " + json.dumps(payload) + ";"
        soup.head.append(script)
        previous = datetime(2026, 10, 2, tzinfo=timezone.utc)
        row = parse_detail("indeed", str(soup), URL, CLOCK, previous).content
        self.assertEqual(row["source_job_id"], "selected456")
        self.assertEqual(row["location"], "Manchester")
        self.assertEqual(row["posted_at"], previous)
        with self.assertRaises(IneligibleListing):
            parse_detail("indeed", str(soup).replace('"jobCountry": "GB"', '"jobCountry": "US"'), URL, CLOCK)
        with self.assertRaises(ExtractionError):
            parse_detail("indeed", str(soup).replace('"jobKey": "selected456"', '"jobKey": "other123"'), URL, CLOCK)


if __name__ == "__main__":
    unittest.main()

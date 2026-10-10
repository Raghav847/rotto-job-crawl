import unittest
from datetime import datetime, timezone
from pathlib import Path

from crawler.models import Observation
from crawler.quarantine import quarantine_relocation
from crawler.reconcile import reconcile, stored_rows
from tests.support import isolated_database


class QuarantineTests(unittest.TestCase):
    def test_explicit_relocation_repair_archives_row_without_expiry_claim(self):
        with isolated_database() as connection:
            clock = datetime(2026, 10, 9, tzinfo=timezone.utc)
            description = "You must be genuine about wanting to move to Australia. These roles are in Melbourne."
            raw = {"source": "linkedin", "source_job_id": "123456789", "url": "https://www.linkedin.com/jobs/view/123456789",
                   "title": "Engineer - Australia", "company": "Example Engineering", "location": "United Kingdom",
                   "description": description, "work_type": "full time"}
            reconcile(connection, Observation.from_dict({"source": "linkedin", "observed_at": clock, "details": [raw]}))
            before = stored_rows(connection)["linkedin:123456789"]
            markup = '<link rel="canonical" href="https://www.linkedin.com/jobs/view/123456789"><h1>Engineer - Australia</h1><div class="show-more-less-html__markup">' + description + '</div>'
            self.assertTrue(quarantine_relocation(connection, "linkedin:123456789", Path("saved-public-capture.html"), markup))
            self.assertEqual(stored_rows(connection), {})
            archived = connection.execute("SELECT * FROM listing_quarantine WHERE job_id='linkedin:123456789'").fetchone()
            self.assertEqual(archived["snapshot"]["content_hash"], before["content_hash"])
            self.assertIsNone(archived["snapshot"]["removed_at"])
            self.assertEqual(archived["reason"], "non_uk_relocation")

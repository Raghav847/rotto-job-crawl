"""Normalized observations shared by source adapters and offline fixtures."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit


CONTENT_FIELDS = (
    "source", "source_job_id", "url", "title", "company", "company_logo_url",
    "location", "work_type", "salary_min", "salary_max", "salary_period",
    "posted_at", "description",
)
SOURCES = {"indeed", "linkedin", "reed"}


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An observation timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def job_id(source, source_job_id):
    if source not in SOURCES or not str(source_job_id):
        raise ValueError("Invalid source listing identity")
    return f"{source}:{source_job_id}"


@dataclass(frozen=True)
class Listing:
    content: dict

    @classmethod
    def from_dict(cls, raw):
        values = {field: raw.get(field) for field in CONTENT_FIELDS}
        if raw.get("source_job_id") is None:
            raise ValueError("Missing source_job_id")
        values["source_job_id"] = str(values["source_job_id"])
        job_id(values["source"], values["source_job_id"])
        for field in ("url", "title", "location", "description"):
            if not isinstance(values[field], str) or not values[field].strip():
                raise ValueError(f"Missing required listing content: {field}")
        if urlsplit(values["url"]).scheme not in ("http", "https"):
            raise ValueError("Listing URL must be public HTTP(S)")
        for field in ("company", "company_logo_url"):
            if values[field] is not None and not isinstance(values[field], str):
                raise ValueError(f"Invalid {field}")
        if values["work_type"] not in (None, "full time", "part time", "contract", "temporary"):
            raise ValueError("Invalid normalized work_type")
        if values["salary_period"] not in (None, "year", "day", "hour"):
            raise ValueError("Invalid normalized salary_period")
        for field in ("salary_min", "salary_max"):
            if values[field] is not None:
                values[field] = Decimal(str(values[field]))
                if not values[field].is_finite():
                    raise ValueError("Salary must be finite")
        if values["salary_min"] is not None and values["salary_max"] is not None:
            if values["salary_min"] > values["salary_max"]:
                raise ValueError("Salary minimum exceeds maximum")
        if values["posted_at"] is not None:
            values["posted_at"] = timestamp(values["posted_at"])
        return cls(values)

    @property
    def id(self):
        return job_id(self.content["source"], self.content["source_job_id"])

    @property
    def content_hash(self):
        def normalize(value):
            if isinstance(value, Decimal):
                return format(value.normalize(), "f") if value else "0"
            if isinstance(value, datetime):
                return timestamp(value).isoformat()
            return value
        content = {key: normalize(value) for key, value in self.content.items()}
        encoded = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    source: str
    scope: str
    observed_at: datetime
    discovery_complete: bool
    discovered: frozenset[str]
    details: tuple[Listing, ...]
    failed_details: frozenset[str]
    confirmed_removed: frozenset[str]

    @classmethod
    def from_dict(cls, raw):
        source = raw["source"]
        if source not in SOURCES:
            raise ValueError("Unknown source")
        details = tuple(Listing.from_dict(value) for value in raw.get("details", []))
        if any(detail.content["source"] != source for detail in details):
            raise ValueError("Detail source differs from observation source")
        detail_ids = [detail.content["source_job_id"] for detail in details]
        if len(detail_ids) != len(set(detail_ids)):
            raise ValueError("Duplicate detail IDs within one observation")
        discovered = frozenset(str(value) for value in raw.get("discovered_source_job_ids", []))
        failed = frozenset(str(value) for value in raw.get("failed_detail_source_job_ids", []))
        removed = frozenset(str(value) for value in raw.get("confirmed_removed_source_job_ids", []))
        if removed & (discovered | set(detail_ids)) or failed & set(detail_ids):
            raise ValueError("Conflicting successful, failed, or removed observations")
        for identity in discovered | failed | removed:
            job_id(source, identity)
        return cls(source, raw.get("scope", "uk"), timestamp(raw["observed_at"]),
                   bool(raw.get("discovery_complete", False)), discovered, details, failed, removed)

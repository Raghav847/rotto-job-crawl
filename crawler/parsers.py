"""Source-aware extraction from public discovery and job-detail HTML."""

import html
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from crawler.models import Listing, timestamp


class ExtractionError(ValueError):
    pass


class IneligibleListing(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    source_job_id: str
    url: str


def source_id(source, url):
    parsed = urlsplit(url)
    domains = {"linkedin": "linkedin.com", "reed": "reed.co.uk", "indeed": "indeed.com"}
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not (host == domains[source] or host.endswith("." + domains[source])):
        raise ExtractionError("URL does not belong to the expected source")
    if source == "indeed":
        identity = parse_qs(parsed.query).get("jk") or parse_qs(parsed.query).get("vjk")
        if identity and re.fullmatch(r"[\w-]+", identity[0]):
            return identity[0]
    else:
        pattern = r"/jobs/view/(?:[^/]*-)?(\d+)/?$" if source == "linkedin" else r"/jobs/[^/]+/(\d+)/?$"
        match = re.search(pattern, parsed.path)
        if match:
            return match[1]
    raise ExtractionError("Missing board-owned job ID")


def clean_url(source, url):
    identity = source_id(source, url)
    if source == "indeed":
        return f"https://uk.indeed.com/viewjob?jk={identity}"
    parsed = urlsplit(url)
    return f"https://{parsed.hostname}{parsed.path.rstrip('/')}"


def discover(source, text, base):
    soup = BeautifulSoup(text, "html.parser")
    found = {}
    for link in soup.select("a[href]"):
        try:
            url = clean_url(source, urljoin(base, link["href"]))
            identity = source_id(source, url)
        except ExtractionError:
            continue
        found.setdefault(identity, Candidate(identity, url))
    next_url = None
    if source == "reed":
        link = soup.select_one("link[rel='next'], [data-qa='rel-page-next']")
        if link and link.get("href"):
            next_url = urljoin(base, link["href"])
            if urlsplit(next_url).hostname != urlsplit(base).hostname:
                next_url = None
    return list(found.values()), next_url


def job_postings(soup):
    postings = []

    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            kind = value.get("@type")
            if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
                postings.append(value)
            for item in value.values():
                if isinstance(item, (list, dict)):
                    walk(item)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            walk(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
    return postings


def text_of(soup, selector):
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else None


def plain_description(value):
    soup = BeautifulSoup(str(value), "html.parser")
    for node in soup.select("script, style, noscript, button"):
        node.decompose()
    for node in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "br"]):
        node.insert_before("\n")
        node.insert_after("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text().splitlines() if line.strip()]
    while lines and lines[0] in ("Full job description", "Job Description", "Job description", "Description"):
        lines.pop(0)
    return "\n".join(line for line in lines if line)


def work_type(value):
    if isinstance(value, list):
        value = " ".join(value)
    normalized = re.sub(r"[-_]", " ", value or "").lower()
    # Contract/temporary take precedence when a source also gives working hours.
    for needle, result in (("temporary", "temporary"), ("contract", "contract"),
                           ("part time", "part time"), ("full time", "full time")):
        if needle in normalized:
            return result
    return None


def salary(text, structured):
    period = None
    if text:
        lower = text.lower()
        for pattern, unit in ((r"annum|annual|year", "year"), (r"\bday\b|daily", "day"),
                              (r"\bhour\b|hourly", "hour")):
            if re.search(pattern, lower):
                period = unit
                break
        amount = r"(\d[\d,]*(?:\.\d+)?)\s*([kK]?)"
        range_match = re.search(r"£\s*" + amount + r"\s*(?:-|–|—|\bto\b)\s*£?\s*" + amount, text)
        if range_match:
            low, low_suffix, high, high_suffix = range_match.groups()
            low = Decimal(low.replace(",", ""))
            high = Decimal(high.replace(",", ""))
            if low_suffix or high_suffix and low < 1000:
                low *= 1000
            if high_suffix:
                high *= 1000
            return low, high, period
        matches = re.findall(r"£\s*" + amount, text)
        values = [Decimal(number.replace(",", "")) * (1000 if suffix else 1) for number, suffix in matches]
        if values:
            if re.search(r"up to|maximum", lower):
                return None, values[0], period
            if re.search(r"from|minimum|starting", lower):
                return values[0], None, period
            return values[0], values[0], period
        # A visible nonnumeric salary such as "Competitive" overrides stale JSON-LD.
        return None, None, None
    if isinstance(structured, dict):
        value = structured.get("value")
        if isinstance(value, (int, float, str)):
            return value, value, None
        if isinstance(value, dict):
            period = {"YEAR": "year", "DAY": "day", "HOUR": "hour"}.get(str(value.get("unitText", "")).upper())
            exact = value.get("value")
            return value.get("minValue", exact), value.get("maxValue", exact), period
    return None, None, None


def countries(value):
    if isinstance(value, list):
        return set().union(*(countries(item) for item in value))
    if isinstance(value, dict):
        if "address" in value:
            return countries(value["address"])
        if "addressCountry" in value:
            return countries(value["addressCountry"])
        return countries(value.get("name", ""))
    return {str(value).strip().lower()} if value else set()


def is_uk_workplace(posting, location, description):
    uk = {"gb", "uk", "united kingdom", "great britain"}
    workplace = countries(posting.get("jobLocation"))
    visible_uk = bool(re.search(r"\b(?:United Kingdom|UK|England|Scotland|Wales|Northern Ireland)\b", location, re.I))
    remote = bool(re.search(r"\bremote\b|work from home", location, re.I)) or posting.get("jobLocationType") == "TELECOMMUTE"
    if remote:
        requirements = countries(posting.get("applicantLocationRequirements"))
        eligible = requirements & uk
        if requirements and not eligible:
            return False
        explicit = re.search(
            r"(?:must be|need to be|applicants? (?:must be|based)|candidates? (?:must be|based))\s+(?:based\s+)?(?:in\s+)?(?:the\s+)?(?:UK|United Kingdom)\b"
            r"|\bUK[- ]based\s+(?:workers|applicants|candidates|employees)\b"
            r"|\bremote\s+(?:within|from|in|anywhere in)\s+(?:the\s+)?(?:UK|United Kingdom)\b",
            description, re.I,
        )
        places = posting.get("jobLocation") or []
        places = places if isinstance(places, list) else [places]
        physical_uk = any(countries(place) & uk and place.get("address", {}).get("addressLocality")
                          and not re.search(r"remote|work from home", place["address"]["addressLocality"], re.I)
                          for place in places if isinstance(place, dict) and isinstance(place.get("address"), dict))
        return bool(eligible or visible_uk or explicit or physical_uk)
    if workplace and not workplace & uk:
        return False
    if workplace & uk and workplace - uk:
        places = posting.get("jobLocation", [])
        places = places if isinstance(places, list) else [places]
        return any(countries(place) & uk and str(place.get("address", {}).get("addressLocality", "")).lower() in location.lower()
                   for place in places if isinstance(place, dict) and place.get("address", {}).get("addressLocality"))
    return bool(workplace & uk or visible_uk)


def expired_page(source, text):
    soup = BeautifulSoup(text, "html.parser")
    for node in soup.select(".jobs-similar-jobs, [data-qa='similar-jobs-container'], .show-more-less-html__markup, [data-qa='job-description'], #jobDescriptionText"):
        node.decompose()
    selectors = ".topcard__flavor--closed, [data-qa='job-expired-message'], .jobsearch-JobExpired, .closed-job, .alert"
    messages = [node.get_text(" ", strip=True) for node in soup.select(selectors)]
    messages.append(soup.title.get_text(" ", strip=True) if soup.title else "")
    return any(re.search(r"(?:this job|this vacancy|job listing) (?:has expired|is no longer available)|no longer accepting applications", message, re.I)
               for message in messages)


def parse_detail(source, text, requested_url, observed_at, previous_posted_at=None):
    identity = source_id(source, requested_url)
    soup = BeautifulSoup(text, "html.parser")
    canonical = soup.select_one("link[rel='canonical']")
    url = clean_url(source, requested_url)
    if canonical and canonical.get("href"):
        canonical_url = urljoin(requested_url, canonical["href"])
        if source_id(source, canonical_url) != identity:
            raise ExtractionError("Canonical listing ID differs from requested listing")
        url = clean_url(source, canonical_url)
    postings = job_postings(soup)
    if len(postings) != 1:
        raise ExtractionError("Expected exactly one current-page JobPosting")
    posting = postings[0]
    if source == "reed":
        identifier = posting.get("identifier") or {}
        if isinstance(identifier, dict) and identifier.get("value") is not None and str(identifier["value"]) != identity:
            raise ExtractionError("Structured Reed listing ID differs from requested listing")
    title_selector = {"linkedin": "h1.topcard__title", "reed": "h1[data-qa='job-title']", "indeed": "h1"}[source]
    title = text_of(soup, title_selector) or posting.get("title")
    organization = posting.get("hiringOrganization") or {}
    company = organization.get("name") if isinstance(organization, dict) else None
    if source == "linkedin":
        company = text_of(soup, ".topcard__org-name-link") or company
        location = text_of(soup, ".topcard__flavor.topcard__flavor--bullet")
        description_node = soup.select_one(".show-more-less-html__markup")
        employment = None
        for node in soup.select(".description__job-criteria-item"):
            heading = text_of(node, ".description__job-criteria-subheader")
            if heading and heading.lower() == "employment type":
                employment = text_of(node, ".description__job-criteria-text")
        salary_text = text_of(soup, ".salary.compensation__salary, .compensation__salary")
        logo_node = soup.select_one(".top-card-layout__entity-info img[data-delayed-url], img.artdeco-entity-image--square-5[data-delayed-url]")
        logo = logo_node.get("data-delayed-url") if logo_node else organization.get("logo")
    elif source == "reed":
        location = text_of(soup, "[data-qa='job-metadata-location']")
        description_node = soup.select_one("[data-qa='job-description']")
        employment = text_of(soup, "[data-qa='job-metadata']")
        salary_text = text_of(soup, "[data-qa='job-metadata-salary']")
        if salary_text and "training course" in salary_text.lower():
            raise IneligibleListing("training_course")
        logo_node = soup.select_one("img[data-qa='company-logo-image']")
        logo = logo_node.get("src") if logo_node else organization.get("logo")
    else:
        location = text_of(soup, "[data-testid='job-location']")
        description_node = soup.select_one("#jobDescriptionText")
        employment = None
        salary_text = None
        logo = organization.get("logo")
    if not description_node:
        raise ExtractionError("Missing full visible description")
    description = plain_description(description_node)
    if not location:
        raise ExtractionError("Missing visible listing location")
    if not is_uk_workplace(posting, location, description):
        raise IneligibleListing("uk_eligibility_unconfirmed")
    if posting.get("validThrough"):
        try:
            if timestamp(posting["validThrough"]) < observed_at:
                raise IneligibleListing("structured_expiry_in_past")
        except ValueError as exc:
            if isinstance(exc, IneligibleListing):
                raise
            # Some boards give date-only validity. Never infer removal from it.
            pass
    posted = posting.get("datePosted")
    if not posted:
        relative = text_of(soup, ".posted-time-ago__text, [data-qa='job-posted-by']") or ""
        match = re.search(r"(\d+)\s*(minute|hour|day|week|month)s?\s+ago", relative, re.I)
        if match:
            units = {"minute": 60, "hour": 3600, "day": 86400, "week": 604800, "month": 2592000}
            posted = previous_posted_at or observed_at - timedelta(seconds=int(match[1]) * units[match[2].lower()])
        elif re.search(r"\b(?:today|just now)\b", relative, re.I):
            posted = previous_posted_at or observed_at
        elif re.search(r"\byesterday\b", relative, re.I):
            posted = previous_posted_at or observed_at - timedelta(days=1)
    if isinstance(posted, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", posted):
        posted += "T00:00:00Z"
    minimum, maximum, period = salary(salary_text, posting.get("baseSalary"))
    if isinstance(logo, dict):
        logo = logo.get("url") or logo.get("contentUrl")
    if logo:
        logo = html.unescape(urljoin(url, logo))
        if urlsplit(logo).scheme not in ("http", "https"):
            logo = None
    return Listing.from_dict({
        "source": source, "source_job_id": identity, "url": url, "title": title,
        "company": company, "company_logo_url": logo, "location": location,
        "work_type": work_type(employment or posting.get("employmentType")),
        "salary_min": minimum, "salary_max": maximum, "salary_period": period,
        "posted_at": posted, "description": description,
    })


if __name__ == "__main__":
    import argparse
    from datetime import datetime, timezone
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Inspect extraction from saved HTML without network requests")
    parser.add_argument("source", choices=("linkedin", "reed", "indeed"))
    parser.add_argument("page", type=Path)
    parser.add_argument("url")
    args = parser.parse_args()
    listing = parse_detail(args.source, args.page.read_text(), args.url, datetime.now(timezone.utc))
    print(json.dumps({key: value for key, value in listing.content.items() if key != "description"}, default=str, indent=2))
    print(f"Description: {len(listing.content['description'])} characters")
    print(listing.content["description"][:600])

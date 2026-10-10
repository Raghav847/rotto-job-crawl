"""Source-aware extraction from public discovery and job-detail HTML."""

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    posted_at: datetime | None = None


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


def discovery_artefacts(soup, result_ids):
    """Hidden inactive/preview nodes absent from a successfully decoded result set."""
    if not result_ids:
        return set()
    return {link["data-jk"] for link in soup.select("a[data-jk]")
            if link["data-jk"] not in result_ids and re.fullmatch(r"[\w-]+", link["data-jk"])
            and any(node.get("aria-hidden") == "true" for node in [link, *link.parents] if hasattr(node, "get"))}


def discover(source, text, base, *, rejected_ids=None, verified_ids=None):
    soup = BeautifulSoup(text, "html.parser")
    found = {}
    if source == "indeed":
        from crawler.indeed import cards
        dates = {}
        results = cards(soup)
        result_ids = {str(card["jobkey"]) for card in results if isinstance(card, dict) and card.get("jobkey") is not None
                      and re.fullmatch(r"[\w-]+", str(card["jobkey"]))}
        artefacts = discovery_artefacts(soup, result_ids)
        if rejected_ids is not None:
            rejected_ids.update(artefacts)
        if verified_ids is not None:
            verified_ids.update(result_ids)
        for card in results:
            if not isinstance(card, dict):
                continue
            published = card.get("pubDate")
            if isinstance(published, (int, float)) and not isinstance(published, bool) and published > 0:
                try:
                    dates[str(card.get("jobkey"))] = datetime.fromtimestamp(published / 1000, timezone.utc)
                except (ValueError, OverflowError, OSError):
                    pass
        for link in soup.select("a[data-jk]"):
            identity = link.get("data-jk", "")
            if identity not in artefacts and re.fullmatch(r"[\w-]+", identity):
                found.setdefault(identity, Candidate(identity, f"https://uk.indeed.com/viewjob?jk={identity}", dates.get(identity)))
        if found:
            return list(found.values()), discovery_next_url(source, soup, base)
    for link in soup.select("a[href]"):
        try:
            url = clean_url(source, urljoin(base, link["href"]))
            identity = source_id(source, url)
        except ExtractionError:
            continue
        if source != "indeed" or identity not in artefacts:
            found.setdefault(identity, Candidate(identity, url))
    return list(found.values()), discovery_next_url(source, soup, base)


def discovery_next_url(source, soup, base):
    selector = {"reed": "link[rel='next'], [data-qa='rel-page-next'], a[aria-label='Next page']",
                "indeed": "a[data-testid='pagination-page-next'], a[aria-label='Next page'], a[aria-label='Next Page']",
                "linkedin": "a[rel='next'], link[rel='next']"}[source]
    link = soup.select_one(selector)
    if not link or not link.get("href"):
        return None
    url = urljoin(base, link["href"])
    parsed, origin = urlsplit(url), urlsplit(base)
    if parsed.scheme != "https" or parsed.username or parsed.hostname != origin.hostname:
        return None
    if source in ("reed", "indeed") and not parsed.path.startswith("/jobs"):
        return None
    return url


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
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text(" ").splitlines() if line.strip()]
    lines = [re.sub(r"\s+([,;:!?])", r"\1", line) for line in lines]
    lines = [re.sub(r"\s+\.(?=\s|$)", ".", line) for line in lines]
    while lines and lines[0] in ("Full job description", "Job Description", "Job description", "Description"):
        lines.pop(0)
    description = "\n".join(line for line in lines if line)
    # Some employers paste a whole careers page into the listing description. Keep
    # application guidance, but exclude an explicitly labelled multi-vacancy footer.
    marker = re.search(r"(?im)^\s*(?:More technology opportunities|Similar roles worth exploring|Related vacancies|Other open positions)\s*$", description)
    if marker and len(re.findall(r"\bView role\b", description[marker.start():], re.I)) >= 2:
        description = description[:marker.start()].rstrip()
    return description


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


def gbp_text(text):
    """Recognize explicit GBP prefix/suffix amounts without assuming a currency."""
    amount = r"\d[\d,]*(?:\.\d+)?\s*[kK]?"
    text = re.sub(r"\bGBP\s*(?=\d)", "£", text, flags=re.I)
    return re.sub(r"(?<![\w£$€])(" + amount + r"(?:\s*(?:-|–|—|\bto\b)\s*" + amount + r")?)\s+GBP\b",
                  r"£\1", text, flags=re.I)


def salary(text, structured):
    period = None
    if text:
        text = gbp_text(text)
        lower = text.lower()
        for pattern, unit in ((r"\b(?:per\s+annum|per\s+year|a\s+year|yearly)\b|/\s*(?:yr|year)\b|\bannual(?:ly)?\b(?!\s+(?:leave|holidays?))", "year"),
                              (r"\b(?:per\s+day|a\s+day|daily)\b|/\s*day\b", "day"),
                              (r"\b(?:per\s+hour|an?\s+hour|hourly)\b|/\s*(?:hr|hour)\b", "hour")):
            if re.search(pattern, lower):
                period = unit
                break
        amount = r"(\d[\d,]*(?:\.\d+)?)\s*([kK]?)"
        frequency = r"(?:\s*(?:/\s*(?:yr|year|hr|hour|day)|(?:per|an?)\s+(?:annum|year|hour|day)))?"
        range_match = re.search(r"£\s*" + amount + frequency + r"\s*(?:-|–|—|\bto\b)\s*£?\s*" + amount, text, re.I)
        if not range_match:
            range_match = re.search(r"\bbetween\s+£\s*" + amount + frequency + r"\s+and\s+£?\s*" + amount, text, re.I)
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


def description_salary(description):
    """Only explicit pay statements; never company assets, shares or benefit amounts."""
    label = re.compile(r"\b(?:annual\s+(?:base\s+)?salary|base\s+salary|salary(?:\s+and\s+benefits)?|pay\s+range|base\s+pay|remuneration)\s*[:\-]?", re.I)
    candidates = []
    grouped_k = re.compile(r"(£?\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?)\s*[kK]\b")
    pending_heading = False

    def collect(candidate):
        candidate = gbp_text(candidate)
        if explicit_amount(candidate):
            value = salary(candidate, None)
            # Keep literal interpretation unless a separate explicit statement corroborates
            # the variant without redundant thousands. Never impose a guessed salary cap.
            alternate = salary(grouped_k.sub(r"\1", candidate), None) if grouped_k.search(candidate) else None
            candidates.append((value, alternate))

    def explicit_amount(candidate):
        amount = re.search(r"£\s*\d[\d,]*(?:\.\d+)?\s*[kK]?", candidate)
        if not amount or amount.start() > 80:
            return False
        before, after = candidate[:amount.start()], candidate[amount.end():]
        if re.search(r"shares|equity|assets|turnover|revenue|pension|bonus|training|course", before, re.I):
            return False
        if re.match(r"\s*(?:(?:of|in|free|annual)\s+)*(?:shares|equity|bonus|billion|million|pension)\b", after, re.I):
            return False
        return True
    for line in description.splitlines():
        match = label.search(line)
        if match:
            # Isolate pay wording from surrounding prose and experience requirements.
            candidate = line[match.start():]
            collect(candidate)
            pending_heading = bool(re.fullmatch(r"\s*(?:base\s+salary|salary|pay\s+range|remuneration)\s*[:\-]?\s*", line, re.I))
        elif pending_heading:
            collect(line)
            pending_heading = False
    candidates = [(value, alternate) for value, alternate in candidates if value[0] is not None or value[1] is not None]
    clean_bounds = {(value[0], value[1]) for value, alternate in candidates if alternate is None}
    candidates = [alternate if alternate is not None and (alternate[0], alternate[1]) in clean_bounds
                  and (value[0], value[1]) not in clean_bounds else value for value, alternate in candidates]
    if not candidates:
        return None, None, None
    bounds = {(minimum, maximum) for minimum, maximum, _ in candidates}
    if len(bounds) != 1:
        return None, None, None
    periods = {period for _, _, period in candidates if period is not None}
    minimum, maximum = next(iter(bounds))
    return minimum, maximum, next(iter(periods)) if len(periods) == 1 else None


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


def non_uk_relocation(title, description):
    destinations = r"Australia|New Zealand|Canada|United States|USA|United Arab Emirates|Singapore|Qatar|Saudi Arabia|South Africa"
    country = re.search(r"\b(" + destinations + r")\b", title or "", re.I)
    if not country:
        return False
    return bool(re.search(r"\b(?:must|need to|required to|expected to)\b[^.!?\n]{0,100}\b(?:move|relocate)\s+to\s+" + re.escape(country[1]) + r"\b",
                          description, re.I))


def is_uk_workplace(posting, location, description):
    if non_uk_relocation(posting.get("title"), description):
        return False
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


def expired_page(source, text, expected_id=None):
    soup = BeautifulSoup(text, "html.parser")
    if source == "indeed" and soup.select_one("[data-testid='viewjob-main-content']"):
        from crawler.indeed import cards, pane_identity, selected_view_model
        identity = pane_identity(soup.select_one("[data-testid='viewjob-main-content']"))
        if expected_id and identity != expected_id:
            return False
        selected = [card for card in cards(soup) if str(card.get("jobkey")) == identity]
        if len(selected) == 1 and selected[0].get("expired") is True:
            return True
        view = selected_view_model(soup, identity)
        if view and view.get("jobInfoWrapperModel", {}).get("jobInfoModel", {}).get("showExpiredHeader") is True:
            return True
    for node in soup.select(".jobs-similar-jobs, [data-qa='similar-jobs-container'], .show-more-less-html__markup, [data-qa='job-description'], #jobDescriptionText, .simple-job-description-html"):
        node.decompose()
    selectors = ".topcard__flavor--closed, [data-qa='job-expired-message'], .jobsearch-JobExpired, .closed-job, .alert"
    messages = [node.get_text(" ", strip=True) for node in soup.select(selectors)]
    messages.append(soup.title.get_text(" ", strip=True) if soup.title else "")
    return any(re.search(r"(?:this job|this vacancy|job listing) (?:has expired|is no longer available)|no longer accepting applications", message, re.I)
               for message in messages)


def parse_detail(source, text, requested_url, observed_at, previous_posted_at=None, rendered_metadata=None):
    from crawler.matching_evidence import structured_reference
    identity = source_id(source, requested_url)
    soup = BeautifulSoup(text, "html.parser")
    if source == "indeed" and soup.select_one("[data-testid='viewjob-main-content']"):
        from crawler.indeed import parse_embedded
        return parse_embedded(text, observed_at, identity, previous_posted_at, rendered_metadata)
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
    if minimum is None and maximum is None:
        minimum, maximum, period = description_salary(description)
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
        "matching_evidence": structured_reference(source, identity, company, organization, posting.get("identifier")),
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

"""Extract the complete, public job pane embedded in Indeed search HTML."""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from crawler.models import Listing


def provider_data(soup):
    result = {}
    decoder = json.JSONDecoder()
    pattern = r"window\.mosaic\.providerData\[(?:\"|')([^\"']+)(?:\"|')\]\s*=\s*"
    for script in soup.find_all("script"):
        text = script.get_text()
        for match in re.finditer(pattern, text):
            try:
                value, _ = decoder.raw_decode(text[match.end():])
            except ValueError:
                continue
            result[match[1]] = value
    return result


def cards(soup):
    data = provider_data(soup).get("mosaic-provider-jobcards", {})
    return data.get("metaData", {}).get("mosaicProviderJobCardsModel", {}).get("results", [])


def pane_identity(pane):
    identities = set()
    for link in pane.select("a[href]"):
        identity = parse_qs(urlsplit(link["href"]).query).get("fromjk", [])
        identities.update(value for value in identity if re.fullmatch(r"[\w-]+", value))
    return next(iter(identities)) if len(identities) == 1 else None


def declared_logo(soup, label):
    """Read the source's branding JSON without loading the logo image."""
    if not label:
        return None
    decoder = json.JSONDecoder()
    for script in soup.find_all("script"):
        text = script.get_text()
        for match in re.finditer(r'"logoAltText"\s*:', text):
            position = match.start()
            for _ in range(20):
                position = text.rfind("{", 0, position)
                if position < 0:
                    break
                try:
                    value, length = decoder.raw_decode(text[position:])
                except ValueError:
                    continue
                if position + length <= match.start() or not isinstance(value, dict):
                    continue
                if str(value.get("logoAltText", "")).strip().casefold() == label.strip().casefold():
                    logo = value.get("logoUrl")
                    if isinstance(logo, str) and logo:
                        return logo
    return None


def parse_embedded(text, observed_at, expected_id=None, previous_posted_at=None, rendered_metadata=None):
    # Local imports avoid a module cycle with the generic parser's Indeed dispatch.
    from crawler.parsers import ExtractionError, IneligibleListing, is_uk_workplace, plain_description, salary, text_of, work_type

    soup = BeautifulSoup(text, "html.parser")
    pane = soup.select_one("[data-testid='viewjob-main-content']")
    if not pane:
        raise ExtractionError("Missing complete Indeed job pane")
    identity = pane_identity(pane)
    if not identity or expected_id and identity != expected_id:
        raise ExtractionError("Indeed pane does not identify the requested listing")
    matches = [card for card in cards(soup) if str(card.get("jobkey")) == identity]
    if len(matches) != 1:
        raise ExtractionError("Missing unambiguous metadata for the selected Indeed job")
    card = matches[0]
    if card.get("expired") is True:
        raise IneligibleListing("explicitly_expired")
    description_node = pane.select_one(".simple-job-description-html, #jobDescriptionText")
    if not description_node:
        raise ExtractionError("Missing full Indeed description")
    description = plain_description(description_node)
    title = text_of(pane, "[data-testid='vj-job-title']")
    company_link = next((link for link in pane.select("a[href]")
                         if parse_qs(urlsplit(link["href"]).query).get("fromjk") == [identity]), None)
    company = company_link.get_text(" ", strip=True) if company_link else card.get("company")
    location = card.get("formattedLocation")
    posting = {"jobLocation": {"address": {"addressCountry": card.get("country"),
                                           "addressLocality": card.get("jobLocationCity")}}}
    if card.get("remoteLocation"):
        posting["jobLocationType"] = "TELECOMMUTE"
    if not location or not is_uk_workplace(posting, location, description):
        raise IneligibleListing("uk_eligibility_unconfirmed")
    summary = text_of(pane, "[data-testid='structured-job-summary']")
    minimum, maximum, period = salary(summary, None)
    posted = None
    if isinstance(card.get("pubDate"), (int, float)):
        posted = datetime.fromtimestamp(card["pubDate"] / 1000, timezone.utc)
    else:
        relative = str(card.get("formattedRelativeTime", ""))
        match = re.search(r"(\d+)\+?\s*(day|hour|minute)s?\s+ago", relative, re.I)
        if match:
            posted = previous_posted_at or observed_at - timedelta(seconds=int(match[1]) * {"day": 86400, "hour": 3600, "minute": 60}[match[2].lower()])
    logo = None
    logo_keys = {"logoUrl", "companyLogoUrl", "featuredCompanyLogo", "featuredCompanyLogoUrl", "featuredCompanyIconUrl"}

    def find_logo(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in logo_keys and isinstance(item, str) and item:
                    return item
                if isinstance(item, dict):
                    found = find_logo(item)
                    if found:
                        return found
        return None

    logo_container = pane.select_one("[data-testid='company-logo']")
    if logo_container:
        logo_node = logo_container.select_one("img[src]")
        logo = logo_node.get("src") if logo_node else None
        if not logo:
            styles = "\n".join(node.get_text() for node in soup.find_all("style"))
            for node in [logo_container, *logo_container.select("[style]")]:
                match = re.search(r"background-image\s*:[^;]*?url\((['\"]?)(.*?)\1\)", node.get("style", ""))
                if match:
                    logo = match[2]
                    break
            if not logo:
                for node in [logo_container, *logo_container.find_all(True)]:
                    for classname in node.get("class", []):
                        for rule in re.findall(r"\." + re.escape(classname) + r"\s*\{([^}]+)\}", styles):
                            match = re.search(r"background-image\s*:[^;]*?url\((['\"]?)(.*?)\1\)", rule)
                            if match:
                                logo = match[2]
                                break
                        if logo:
                            break
                    if logo:
                        break
    if not logo and logo_container:
        logo = declared_logo(soup, logo_container.get("aria-label"))
    logo = logo or find_logo(card.get("featuredCompanyAttributes", {}))
    if rendered_metadata:
        if rendered_metadata.get("source_job_id") not in (None, identity):
            raise ExtractionError("Rendered metadata belongs to a different Indeed job")
        logo = rendered_metadata.get("company_logo_url") or logo
        if rendered_metadata.get("logo_present") and not logo:
            raise ExtractionError("Visible Indeed logo URL was not extracted")
    if logo:
        logo = urljoin("https://uk.indeed.com/", logo)
        if urlsplit(logo).scheme not in ("http", "https"):
            logo = None
    return Listing.from_dict({
        "source": "indeed", "source_job_id": identity,
        "url": f"https://uk.indeed.com/viewjob?jk={identity}", "title": title, "company": company or None,
        "company_logo_url": logo, "location": location, "work_type": work_type(summary),
        "salary_min": minimum, "salary_max": maximum, "salary_period": period,
        "posted_at": posted, "description": description,
    })

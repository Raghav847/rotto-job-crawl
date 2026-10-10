"""Offline source-evidence inventory for field-by-field review, not accuracy grading."""

import argparse
import json
import re
import textwrap
import random
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.database import connect, database_url
from crawler.exporting import json_value
from crawler.indeed import cards, pane_identity, selected_view_model
from crawler.parsers import job_postings, source_id
from crawler.reconcile import stored_rows


def text(soup, selector):
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else None


def evidence(source, markup):
    soup = BeautifulSoup(markup, "html.parser")
    postings = job_postings(soup)
    posting = postings[0] if len(postings) == 1 else {}
    if source == "indeed":
        pane = soup.select_one("[data-testid='viewjob-main-content']")
        if not pane:
            return None
        identity = pane_identity(pane)
        selected = [card for card in cards(soup) if str(card.get("jobkey")) == identity]
        card = selected[0] if len(selected) == 1 else {}
        view = selected_view_model(soup, identity) or {}
        header = view.get("jobInfoWrapperModel", {}).get("jobInfoModel", {}).get("jobInfoHeaderModel", {})
        title = text(pane, "[data-testid='vj-job-title']")
        location = card.get("formattedLocation") or header.get("formattedLocation") or view.get("jobLocation")
        description = pane.select_one(".simple-job-description-html, #jobDescriptionText")
        summary = text(pane, "[data-testid='structured-job-summary']")
        country = card.get("country") or view.get("jobCountry")
        date = card.get("pubDate") or view.get("datePublished")
        company = card.get("company") or header.get("companyName")
        logo = pane.select_one("[data-testid='company-logo']")
        logos = {"logo_container_label": logo.get("aria-label") if logo else None,
                 "company_images_model": header.get("companyImagesModel")}
    else:
        canonical = soup.select_one("link[rel='canonical']")
        try:
            identity = source_id(source, canonical["href"]) if canonical else None
        except ValueError:
            return None
        title = text(soup, "h1")
        location = text(soup, ".topcard__flavor.topcard__flavor--bullet" if source == "linkedin" else "[data-qa='job-metadata-location']")
        description = soup.select_one(".show-more-less-html__markup" if source == "linkedin" else "[data-qa='job-description']")
        summary = [node.get_text(" ", strip=True) for node in soup.select(".description__job-criteria-item")] if source == "linkedin" else text(soup, "[data-qa='job-metadata']")
        country = posting.get("jobLocation")
        date = posting.get("datePosted")
        company = posting.get("hiringOrganization")
        logos = {"source_logos": [{"alt": node.get("alt"), "src": node.get("src"), "delayed_url": node.get("data-delayed-url")}
                                  for node in soup.select(".top-card-layout__entity-info img, img.artdeco-entity-image--square-5, img[data-qa='company-logo-image']")[:3]]}
    if not identity or not description:
        return None
    clean = BeautifulSoup(str(description), "html.parser")
    for node in clean.select("script, style, button, noscript"):
        node.decompose()
    full_text = clean.get_text(" ", strip=True)
    salary_hints = []
    for match in re.finditer(r"£|\b(?:GBP|salary|per annum|per hour|per day)\b", full_text, re.I):
        if len(salary_hints) < 12:
            salary_hints.append(full_text[max(0, match.start() - 60):match.start() + 180])
    structured_description = posting.get("description")
    structured_text = BeautifulSoup(structured_description, "html.parser").get_text(" ", strip=True) if isinstance(structured_description, str) else None
    return {"id": f"{source}:{identity}", "title": title, "location": location,
             "company": company, "employment_metadata": summary, "country_evidence": country,
             "date_evidence": date, "source_identifier": posting.get("identifier"),
             "structured_salary": posting.get("baseSalary"),
            "visible_salary": text(soup, ".compensation__salary, .salary, [data-qa='job-metadata-salary']") if source != "indeed" else summary,
             "description_salary_hints": salary_hints, "source_description_characters": len(full_text),
             "structured_description_characters": len(structured_text) if structured_text is not None else None,
             "structured_description_end": structured_text[-250:] if structured_text else None,
             "source_description": full_text,
             "description_start": full_text[:400], "description_end": full_text[-400:], **logos}


def description_tokens(markup, source):
    soup = BeautifulSoup(markup, "html.parser")
    selector = {"indeed": "[data-testid='viewjob-main-content'] .simple-job-description-html",
                "linkedin": ".show-more-less-html__markup", "reed": "[data-qa='job-description']"}[source]
    node = soup.select_one(selector)
    if not node:
        return []
    for element in node.select("script, style, button, noscript"):
        element.decompose()
    # Remove standalone presentation headings, not employer prose such as "Description - ...".
    headings = {"Full job description", "Job Description", "Job description", "Description"}
    for fragment in list(node.find_all(string=True)):
        if not fragment.strip():
            continue
        if fragment.strip() in headings:
            fragment.extract()
        else:
            break
    value = node.get_text(" ", strip=True)
    line_reference = node.get_text("\n", strip=True)
    for label in ("More technology opportunities", "Similar roles worth exploring", "Related vacancies", "Other open positions"):
        if re.search(r"(?m)^\s*" + re.escape(label) + r"\s*$", line_reference):
            position = value.find(label)
            if position >= 0 and len(re.findall(r"\bView role\b", value[position:], re.I)) >= 2:
                value = value[:position].rstrip()
                break
    for heading in node.find_all(True):
        label = heading.get_text(" ", strip=True)
        if label in ("More technology opportunities", "Similar roles worth exploring", "Related vacancies", "Other open positions"):
            position = value.find(label)
            if position >= 0 and len(re.findall(r"\bView role\b", value[position:], re.I)) >= 2:
                value = value[:position].rstrip()
                break
    return re.findall(r"\w+", value.casefold())


def inventory(run=None):
    found = {}
    root = Path("output/runs")
    folders = [run] if run else sorted(root.iterdir()) if root.exists() else []
    for folder in folders:
        if not folder.is_dir():
            continue
        for page in sorted(folder.glob("*-*-detail.html")):
            pieces = page.stem.split("-", 2)
            if len(pieces) != 3 or pieces[1] not in ("linkedin", "reed"):
                continue
            item = evidence(pieces[1], page.read_text())
            if item:
                found[item["id"]] = {"capture": str(page), **item}
        for page in sorted((folder / "indeed-browser").glob("*.html")):
            item = evidence("indeed", page.read_text())
            if item:
                found[item["id"]] = {"capture": str(page), **item}
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="Restrict evidence to one saved run")
    parser.add_argument("--ids", nargs="+", help="Review only these source:id values")
    parser.add_argument("--observed-in-run", action="store_true", help="Select successful detail observations from --run events")
    parser.add_argument("--sample-per-source", type=int, default=0, help="Select a reproducible stratified random review sample")
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--quiet", action="store_true", help="Print aggregate triage only; keep full per-row evidence in ignored files")
    parser.add_argument("--label", default="", help="Keep named all-row/sample evidence files side by side")
    args = parser.parse_args()
    if args.label and not re.fullmatch(r"[A-Za-z0-9_-]+", args.label):
        parser.error("--label must contain only letters, digits, underscores or hyphens")
    prefix = args.label + "-" if args.label else ""
    captured = inventory(args.run)
    with connect(database_url()) as connection:
        rows = stored_rows(connection)
    if args.ids:
        missing = set(args.ids) - rows.keys()
        if missing:
            raise ValueError(f"Unknown stored IDs: {sorted(missing)}")
        rows = {identity: rows[identity] for identity in args.ids}
    if args.observed_in_run:
        if not args.run:
            parser.error("--observed-in-run requires --run")
        events = [json.loads(line) for line in (args.run / "events.jsonl").read_text().splitlines()]
        ids = {event["source"] + ":" + event["source_job_id"] for event in events if event["kind"] == "stored"}
        rows = {identity: row for identity, row in rows.items() if identity in ids}
    if args.sample_per_source < 0:
        parser.error("--sample-per-source must be nonnegative")
    if args.sample_per_source:
        rng = random.Random(args.seed)
        selected = []
        for source in ("indeed", "linkedin", "reed"):
            available = sorted(identity for identity, row in rows.items() if row["source"] == source)
            selected.extend(rng.sample(available, min(args.sample_per_source, len(available))))
        rows = {identity: rows[identity] for identity in selected}
    search_dates = {}
    if args.run:
        for page in sorted((args.run / "indeed-browser").glob("*-discovery.html")):
            for card in cards(BeautifulSoup(page.read_text(), "html.parser")):
                if isinstance(card.get("pubDate"), (int, float)) and card["pubDate"] > 0:
                    search_dates.setdefault(f"indeed:{card.get('jobkey')}", []).append({
                        "capture": str(page), "posted_at": datetime.fromtimestamp(card["pubDate"] / 1000, timezone.utc),
                        "job_types": card.get("jobTypes"),
                        "salary_snippet": card.get("salarySnippet")})
    reviews = []
    for identity, row in rows.items():
        item = captured.get(identity)
        stored = {key: value for key, value in row.items() if key != "description"}
        review = {"id": identity, "stored": stored, "source_evidence": item,
                   "review_status": "needs_manual_review" if item else "capture_missing"}
        if identity in search_dates:
            review["discovery_date_evidence"] = search_dates[identity]
            dates = {item["posted_at"] for item in search_dates[identity]}
            review["discovery_date_agrees"] = row["posted_at"] in dates
            review["discovery_dates_conflict"] = len(dates) > 1
        if item:
            review["title_agrees"] = row["title"] == item["title"]
            review["location_agrees"] = row["location"] == item["location"]
            reference = description_tokens(Path(item["capture"]).read_text(), row["source"])
            stored_tokens = re.findall(r"\w+", row["description"].casefold())
            review["description_words_agree"] = reference == stored_tokens
            if not review["description_words_agree"]:
                changes = []
                for kind, a, b, c, d in SequenceMatcher(None, reference, stored_tokens, autojunk=False).get_opcodes():
                    if kind != "equal" and len(changes) < 3:
                        changes.append({"source_words": reference[max(0, a - 5):b + 5], "stored_words": stored_tokens[max(0, c - 5):d + 5]})
                review["description_differences"] = changes
                if not args.quiet:
                    print(json.dumps({"id": identity, "description_differences": changes}))
        review["triage_flags"] = []
        for key in ("title_agrees", "location_agrees", "description_words_agree", "discovery_date_agrees"):
            if review.get(key) is False:
                review["triage_flags"].append(key)
        if not item:
            review["triage_flags"].append("capture_missing")
        elif item:
            from crawler.parsers import non_uk_relocation
            if non_uk_relocation(item["title"], item["source_description"]):
                review["triage_flags"].append("non_uk_relocation")
            if re.search(r"More technology opportunities|Similar roles worth exploring", row["description"], re.I):
                review["triage_flags"].append("related_vacancy_footer")
            if row["salary_min"] is None and row["salary_max"] is None and re.search(r"\bsalary\s+between\s*£\s*\d", item["source_description"], re.I):
                review["triage_flags"].append("explicit_between_salary_missing")
            company = item["company"].get("name") if isinstance(item["company"], dict) else item["company"]
            if company is not None and (row["company"] or "").strip() != company.strip():
                review["triage_flags"].append("company_disagrees")
            logos = item.get("source_logos") or []
            logo = (logos[0].get("delayed_url") or logos[0].get("src")) if logos else None
            if row["source"] == "indeed":
                images = item.get("company_images_model")
                logo = images.get("logoUrl") if isinstance(images, dict) else None
            if logo and row["company_logo_url"] != logo:
                review["triage_flags"].append("logo_disagrees")
            date = item.get("date_evidence")
            if isinstance(date, (int, float)):
                expected_date = datetime.fromtimestamp(date / 1000, timezone.utc)
                if row["posted_at"] != expected_date:
                    review["triage_flags"].append("posted_at_disagrees")
            elif isinstance(date, str):
                try:
                    expected_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    if expected_date.tzinfo and row["posted_at"] != expected_date:
                        review["triage_flags"].append("posted_at_disagrees")
                except ValueError:
                    review["triage_flags"].append("source_date_requires_review")
            employment = item.get("employment_metadata") or ""
            employment = " ".join(employment) if isinstance(employment, list) else employment
            normalized_employment = employment.casefold().replace("-", " ")
            expected_type = next((value for value in ("contract", "temporary", "part time", "full time")
                                  if re.search(r"\b" + value + r"\b", normalized_employment)), None)
            if expected_type is not None and row["work_type"] != expected_type:
                review["triage_flags"].append("work_type_disagrees")
            pay = item.get("structured_salary")
            if isinstance(pay, dict) and isinstance(pay.get("value"), dict):
                value = pay["value"]
                for field, key in (("salary_min", "minValue"), ("salary_max", "maxValue")):
                    expected = value.get(key, value.get("value"))
                    if expected is not None and (row[field] is None or float(expected) != float(row[field])):
                        review["triage_flags"].append(field + "_structured_conflict")
        reviews.append(review)
    folder = Path("output/reviews")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (prefix + "source-evidence.json")
    path.write_text(json.dumps({"created_at": datetime.now(timezone.utc), "rows": reviews}, default=json_value, indent=2) + "\n")
    triage = {"created_at": datetime.now(timezone.utc), "rows": len(reviews), "seed": args.seed,
              "sample_per_source": args.sample_per_source,
              "flagged": [{"id": item["id"], "flags": item["triage_flags"]} for item in reviews if item["triage_flags"]],
              "scope": "Independent source evidence triage, not an automatic validity or accuracy grade"}
    (folder / (prefix + "triage.json")).write_text(json.dumps(triage, default=json_value, indent=2) + "\n")
    metadata_lines = []
    for review in reviews:
        if review["source_evidence"]:
            (folder / (review["id"].replace(":", "-") + "-description.txt")).write_text(
                textwrap.fill(review["source_evidence"]["source_description"], width=100) + "\n")
            source_metadata = {key: value for key, value in review["source_evidence"].items()
                               if key not in ("source_description", "description_start", "description_end", "description_salary_hints")}
            metadata_lines.extend([review["id"],
                                   textwrap.fill("Stored: " + json.dumps(review["stored"], default=json_value, ensure_ascii=False), width=120),
                                   textwrap.fill("Source: " + json.dumps(source_metadata, default=json_value, ensure_ascii=False), width=120),
                                   "Description words agree: " + str(review.get("description_words_agree")), ""])
            if "discovery_date_evidence" in review:
                metadata_lines.extend(["Discovery dates: " + ", ".join(sorted({item["posted_at"].isoformat() for item in review["discovery_date_evidence"]})),
                                       "Discovery date agrees: " + str(review["discovery_date_agrees"]),
                                       "Discovery dates conflict: " + str(review["discovery_dates_conflict"]),
                                       "Discovery types: " + json.dumps([item.get("job_types") for item in review["discovery_date_evidence"]], ensure_ascii=False),
                                       "Discovery salary: " + json.dumps([item.get("salary_snippet") for item in review["discovery_date_evidence"]], ensure_ascii=False), ""])
    (folder / (prefix + "source-metadata.txt")).write_text("\n".join(metadata_lines))
    print(f"Prepared {len(reviews)} review records; {sum(item['source_evidence'] is not None for item in reviews)} have source captures")
    print(path)
    print(f"Evidence triage: {len(triage['flagged'])}/{len(reviews)} flagged; seed={args.seed}, sample/source={args.sample_per_source}")
    print(f"Description word streams agree for {sum(item.get('description_words_agree', False) for item in reviews)}/{len(reviews)} records (formatting-sensitive check, not an accuracy score)")
    dated = [item for item in reviews if "discovery_date_agrees" in item]
    if dated:
        print(f"Discovery dates agree for {sum(item['discovery_date_agrees'] for item in dated)}/{len(dated)} records; {sum(item['discovery_dates_conflict'] for item in dated)} conflicting source-date sets")
    for review in [] if args.quiet else reviews:
        item = review["source_evidence"]
        if item:
            print(json.dumps({"id": review["id"], "stored_salary": [review["stored"][key] for key in ("salary_min", "salary_max", "salary_period")],
                              "visible_salary": item["visible_salary"], "structured_salary": item["structured_salary"],
                              "description_salary_hints": item["description_salary_hints"],
                              "title_agrees": review["title_agrees"], "location_agrees": review["location_agrees"],
                              "description_words_agree": review["description_words_agree"]}, default=json_value))


if __name__ == "__main__":
    main()

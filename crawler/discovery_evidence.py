"""Offline discovery-page evidence inspection; no network requests."""

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from crawler.parsers import discover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("linkedin", "reed", "indeed"))
    parser.add_argument("page", type=Path)
    args = parser.parse_args()
    soup = BeautifulSoup(args.page.read_text(), "html.parser")
    candidates, next_url = discover(args.source, str(soup), f"https://{'www.linkedin.com' if args.source == 'linkedin' else 'www.reed.co.uk' if args.source == 'reed' else 'uk.indeed.com'}/jobs")
    artefacts = []
    if args.source == "indeed":
        from crawler.indeed import cards
        result_ids = {str(card.get("jobkey")) for card in cards(soup)}
        for link in soup.select("a[data-jk]"):
            if link["data-jk"] not in result_ids:
                hidden = any(node.get("aria-hidden") == "true" for node in [link, *link.parents] if hasattr(node, "get"))
                artefacts.append({"id": link["data-jk"], "in_result_metadata": False, "aria_hidden": hidden,
                                  "title": link.get_text(" ", strip=True)[:150]})
    print(json.dumps({"title": soup.title.get_text(" ", strip=True) if soup.title else None,
                      "candidates": len(candidates), "first_ids": [item.source_job_id for item in candidates[:5]],
                      "unverified_indeed_nodes": artefacts,
                      "next_url": next_url,
                      "linkedin_result_cards": len(soup.select(".jobs-search__results-list > li")),
                      "headings": [node.get_text(" ", strip=True)[:200] for node in soup.select("h1")],
                      "location_controls": [{key: node.get(key) for key in ("name", "id", "value", "placeholder") if node.get(key)}
                                            for node in soup.select("input, select")
                                            if re.search(r"location|where|town", str(node.attrs), re.I)],
                      "location_links": sorted({node["href"].split("?")[0] for node in soup.select("a[href]")
                                                if "-jobs-in-" in node["href"]})[:20]}))
    for node in soup.find_all(True):
        selected = {key: str(value)[:1000] for key, value in node.attrs.items()
                    if re.search(r"url|endpoint|results|page|pagination", key, re.I)}
        if selected and any(re.search(r"seeMoreJob|api/|next|pagination|pageno|start=|results-url", key + value, re.I)
                            for key, value in selected.items()):
            print(json.dumps({"tag": node.name, "text": node.get_text(" ", strip=True)[:100], "attributes": selected}))
        if node.name == "a" and ("next" in node.get("rel", []) or re.search(r"next|page [2-9]", str(node.get("aria-label", "")), re.I)):
            print(json.dumps({"paging_link": node.get("href"), "rel": node.get("rel"), "aria": node.get("aria-label")}))


if __name__ == "__main__":
    main()

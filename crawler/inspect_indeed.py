"""Compact offline evidence inspection for Indeed HTML and captured requests."""

import argparse
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path)
    parser.add_argument("--metadata", action="store_true")
    args = parser.parse_args()
    soup = BeautifulSoup(args.page.read_text(), "html.parser")
    print("Title:", soup.title.get_text(" ", strip=True) if soup.title else None)
    pane = soup.select_one("[data-testid='viewjob-main-content']")
    if pane:
        logo = pane.select_one("[data-testid='company-logo']")
        if logo:
            print("Logo markup:", str(logo)[:4000])
        for link in pane.select("a[href]"):
            print(json.dumps({"pane_link": link.get_text(" ", strip=True)[:100], "url": link["href"][:500]}))
        for node in pane.select("[data-testid]"):
            key = node.get("data-testid")
            if key != "viewjob-job-content":
                print(json.dumps({"pane_field": key, "text": node.get_text(" ", strip=True)[:150],
                                  "attributes": {name: str(value)[:250] for name, value in node.attrs.items()
                                                 if name in ("href", "src", "alt", "data-jk", "data-jobkey")}}))
    first_card = soup.select_one("a[data-jk]")
    first_key = first_card.get("data-jk") if first_card else None
    for selector in ("h1", "h2.jobTitle", "a[data-jk]", "a.jcs-JobTitle", "#jobDescriptionText",
                     "[data-testid*='company']", "[data-testid*='location']", "[data-testid*='salary']"):
        for node in soup.select(selector)[:10]:
            if args.metadata:
                continue
            print(json.dumps({"selector": selector, "text": node.get_text(" ", strip=True)[:500],
                              "attributes": {key: str(value)[:500] for key, value in node.attrs.items()
                                             if key in ("href", "data-jk", "data-testid", "id")}}))
    for script in soup.find_all("script"):
        text = script.get_text()
        for match in list(re.finditer(r"/_logo/|companyLogoUrl|logoUrl", text))[:5]:
            print("Logo source context:", text[max(0, match.start() - 100):match.end() + 250])
        if args.metadata:
            print(json.dumps({"all_script_id": script.get("id"), "type": script.get("type"),
                              "characters": len(text), "prefix": text[:150],
                              "first_job_id_present": bool(first_key and first_key in text)}))
        if any(marker in text for marker in ("mosaic.providerData", "__INITIAL_DATA__", "_initialData", "jobDescription")):
            print(json.dumps({"script_id": script.get("id"), "characters": len(text), "prefix": text[:250]}))
        for match in re.finditer(r"window\.mosaic\.providerData\[(?:\"|')([^\"']+)(?:\"|')\]\s*=\s*", text):
            try:
                value, _ = json.JSONDecoder().raw_decode(text[match.end():])
            except ValueError:
                continue
            print(json.dumps({"provider": match[1], "keys": list(value) if isinstance(value, dict) else None}))
            if match[1] == "mosaic-provider-jobcards":
                model = value.get("metaData", {}).get("mosaicProviderJobCardsModel", {})
                print(json.dumps({"jobcards_model_keys": list(model)}))
                results = model.get("results", [])
                if results:
                    for card in results[:2]:
                        print(json.dumps({"card_detail_fields": {key: card.get(key) for key in (
                            "jobkey", "jobTypes", "featuredCompanyAttributes", "salarySnippet", "enhancedAttributesModel"
                        )}}))
                    print(json.dumps({"first_card_fields": {
                        key: value if isinstance(value, (str, int, float, bool)) and len(str(value)) < 300 else type(value).__name__
                        for key, value in results[0].items() if not re.search(r"token|cookie|session|ctk|tk|csrf|tracking|link", key, re.I)
                    }}))

            def walk(node, path=""):
                if isinstance(node, list):
                    for index, item in enumerate(node[:2]):
                        walk(item, f"{path}[{index}]")
                elif isinstance(node, dict):
                    if any(key in node for key in ("jobKey", "jobInfoModel", "jobInfoWrapperModel", "sanitizedJobDescription", "jobDescription", "jobTitle")):
                        print(json.dumps({"path": path, "fields": {
                            key: value if isinstance(value, (str, int, float, bool)) and len(str(value)) < 300 else type(value).__name__
                            for key, value in node.items() if not re.search(r"token|cookie|session|ctk|tk|csrf", key, re.I)
                        }}))
                    for key, item in node.items():
                        if isinstance(item, (list, dict)):
                            walk(item, path + "." + key)
            walk(value, match[1])
    for node in soup.select("[data-testid], [id]"):
        key = node.get("data-testid") or node.get("id") or ""
        if re.search(r"description|jobinfo|jobheader|jobcomponent", key, re.I):
            print(json.dumps({"field": key, "text": node.get_text(" ", strip=True)[:300]}))
            parent = node.parent
            for level in range(3):
                if parent:
                    print(json.dumps({"parent_level": level, "tag": parent.name, "attributes": parent.attrs,
                                      "prefix": str(parent)[:1000]}))
                    parent = parent.parent
    if not args.metadata:
        print("Visible text excerpt:", soup.get_text(" ", strip=True)[-5000:])


if __name__ == "__main__":
    main()

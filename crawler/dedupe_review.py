"""Freeze manually labelled real-source pairs and evaluate them offline. No board requests."""

import argparse
import json
import re
from pathlib import Path

from crawler.accuracy_review import description_tokens, inventory
from crawler.database import connect, database_url
from crawler.dedupe import compare, profile
from crawler.exporting import json_value
from crawler.models import CONTENT_FIELDS, Listing
from crawler.matching_evidence import structured_reference
from crawler.reconcile import stored_rows


def reference_evidence(item, row):
    return structured_reference(row["source"], row["source_job_id"], row.get("company"),
                                item.get("company"), item.get("source_identifier"))


def freeze(labels_path, destination):
    labels = json.loads(labels_path.read_text())
    captured = inventory()
    with connect(database_url()) as connection:
        rows = stored_rows(connection)
    ids = sorted({pair[side] for pair in labels["pairs"] for side in ("left", "right")})
    snapshots = {}
    for identity in ids:
        row = rows[identity]
        evidence = captured.get(identity)
        if not evidence or not row["title"] == evidence["title"] or not row["location"] == evidence["location"]:
            raise ValueError(f"Missing or inconsistent source evidence for {identity}")
        if description_tokens(Path(evidence["capture"]).read_text(), row["source"]) != re.findall(r"\w+", row["description"].casefold()):
            raise ValueError(f"Captured description differs from the stored source snapshot for {identity}")
        snapshots[identity] = {"id": identity, **{key: row[key] for key in CONTENT_FIELDS},
                               "matching_evidence": reference_evidence(evidence, row),
                               "capture": evidence["capture"]}
    destination.write_text(json.dumps({"version": labels["version"], "scope": labels["scope"],
                                       "rows": snapshots, "pairs": labels["pairs"]}, default=json_value,
                                      ensure_ascii=False, indent=2) + "\n")
    print(f"Froze {len(ids)} source listings and {len(labels['pairs'])} independently labelled pairs: {destination}")


def evaluate(fixture):
    true_positive = false_positive = false_negative = true_negative = 0
    decisions = []
    unresolved = []
    for pair in fixture["pairs"]:
        if pair.get("duplicate") is None:
            unresolved.append({key: pair[key] for key in ("name", "left", "right", "reason")})
            continue
        left, right = (fixture["rows"][pair[side]] for side in ("left", "right"))
        decision = compare(profile({**left, **Listing.from_dict(left).content}),
                           profile({**right, **Listing.from_dict(right).content}))
        true_positive += int(decision.matched and pair["duplicate"])
        false_positive += int(decision.matched and not pair["duplicate"])
        false_negative += int(not decision.matched and pair["duplicate"])
        true_negative += int(not decision.matched and not pair["duplicate"])
        decisions.append({"name": pair["name"], "expected_duplicate": pair["duplicate"], "matched": decision.matched,
                          "reason": decision.reason, "scores": decision.scores})
    return {"pairs": len(decisions), "true_positive": true_positive, "false_positive": false_positive,
            "false_negative": false_negative, "true_negative": true_negative,
            "precision": true_positive / (true_positive + false_positive) if true_positive + false_positive else None,
            "recall": true_positive / (true_positive + false_negative) if true_positive + false_negative else None,
            "scope": fixture["scope"], "decisions": decisions, "unresolved": unresolved}


def rank_unlabelled(labels_path, limit):
    from crawler.dedupe import dice
    labels = json.loads(labels_path.read_text())
    labelled = {tuple(sorted((pair["left"], pair["right"]))) for pair in labels["pairs"]}
    with connect(database_url()) as connection:
        rows = stored_rows(connection)
    captured = inventory()
    features = {identity: profile({**row, "matching_evidence": reference_evidence(captured[identity], row) if identity in captured else None})
                for identity, row in rows.items()}
    candidates = []
    ids = sorted(rows)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            a, b = features[left], features[right]
            if (left, right) in labelled or a["source"] == b["source"] or not a["company_key"] or a["company_key"] != b["company_key"]:
                continue
            if a["role_family"] != b["role_family"] or a["location_key"] != b["location_key"]:
                continue
            overlap = dice(a["tokens"], b["tokens"])
            if overlap < 0.5:
                continue
            decision = compare(a, b)
            candidates.append({"left": left, "right": right, "left_title": rows[left]["title"], "right_title": rows[right]["title"],
                               "description_overlap": round(overlap, 4), "matched": decision.matched, "reason": decision.reason})
    return sorted(candidates, key=lambda item: -item["description_overlap"])[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Freeze the current DB/captured evidence for the manual label manifest")
    parser.add_argument("--labels", type=Path, default=Path("tests/fixtures/real_dedupe_labels.json"))
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/real_dedupe_pairs.json"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--rank-unlabelled", type=int, default=0, help="Rank unused cross-board candidate pairs for independent inspection")
    args = parser.parse_args()
    if args.rank_unlabelled:
        result = {"unlabelled_candidates": rank_unlabelled(args.labels, args.rank_unlabelled),
                  "scope": "Candidate ranking only; matching predictions are not ground-truth labels"}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return
    if args.freeze:
        freeze(args.labels, args.fixture)
    result = evaluate(json.loads(args.fixture.read_text()))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

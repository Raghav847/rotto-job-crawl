"""Explainable vacancy matching and incremental, stable canonical grouping."""

import math
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb


RULE_VERSION = 2
LEGAL_SUFFIXES = {"ltd", "limited", "plc", "llc", "inc", "incorporated", "corp", "corporation", "co", "llp"}
UNKNOWN_COMPANIES = {"confidential", "companyconfidential", "privateadvertiser", "undisclosed", "unknown"}
STOP_WORDS = set("""a an and are as at be been being by can could for from has have how in into is it its
    of on or our that the their them these they this those to we were what when where which who will with
    you your us all also any both each every more most other some such than then there through within
    about across join opportunity opportunities equal employer employee employees employment diversity
    inclusion inclusive benefits benefit pension holiday leave application apply candidate candidates
    company organisation organization team teams role roles position positions job jobs work working
    offer offers offering experience experienced excellent competitive support supporting talented
    looking seeking exciting passionate innovative innovation committed commitment successful success
    great new people ability strong skills skill required requirements responsibility responsibilities
    business businesses customer customers client clients service services deliver delivering delivery
    development develop developing engineer engineering software years year ensure including knowledge
    understanding environment environments solutions solution industry industries based part full time""".split())
TECH = {"python", "java", "csharp", "dotnet", "cpp", "javascript", "typescript", "golang", "ruby", "php",
        "scala", "rust", "kotlin", "swift", "react", "angular", "vue", "postgresql", "mysql", "sql",
        "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "linux", "spark", "kafka", "redis"}
TITLE_NOISE = {"software", "engineer", "engineering", "developer", "development", "senior", "junior", "lead",
               "principal", "staff", "associate", "graduate", "full", "time", "remote", "hybrid", "uk",
               "united", "kingdom", "england", "scotland", "wales", "contract", "permanent", "fm", "fmd"}


def normalize(value):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    replacements = {r"c\+\+": " cpp ", r"c#": " csharp ", r"\.net\b": " dotnet ",
                    r"\bback[ -]end\b": "backend", r"\bfront[ -]end\b": "frontend",
                    r"\bfull[ -]stack\b": "fullstack", r"\bpostgres\b": "postgresql",
                    r"\bjs\b": "javascript", r"\bgo\b": "golang", r"\bsr\.?\b": "senior",
                    r"\bjr\.?\b": "junior", r"\bdevelopers?\b": "engineer",
                    r"\b(?:building|builds)\b": "build", r"\b(?:designing|designs)\b": "design",
                    r"\b(?:maintaining|maintains)\b": "maintain", r"\btesting\b": "test",
                    r"\b(?:automating|automation)\b": "automate", r"\b(?:optimising|optimizing|optimise|optimized)\b": "optimize"}
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def company_key(value):
    text = unicodedata.normalize("NFKC", value or "").casefold()
    words = re.findall(r"[^\W_]+", text)
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    key = "".join(word for word in words if word not in ("the", "and"))
    return key if key and key not in UNKNOWN_COMPANIES else None


def location_key(value):
    text = normalize(value)
    text = re.sub(r"^(?:hybrid work in|hybrid in|based in|on site in)\s+", "", text)
    if re.search(r"\bremote\b|work from home", text):
        return "remote"
    first = (value or "").split(",")[0]
    first = re.sub(r"\b[A-Z]{1,2}\d[A-Z\d]?(?:\s*\d[A-Z]{2})?\b", "", first, flags=re.I)
    first = normalize(first)
    first = re.sub(r"^(?:hybrid work in|hybrid in|based in|on site in)\s+", "", first)
    if first in ("united kingdom", "uk", "england", "scotland", "wales"):
        return "uk"
    if first in ("greater london", "east london", "west london", "north london", "south london", "central london"):
        return "london"
    return first or "uk"


def role_family(title):
    words = set(normalize(title).split())
    for family, alternatives in (
        ("manager", {"manager", "director", "head"}), ("nurse", {"nurse", "nursing"}),
        ("scientist", {"scientist"}), ("analyst", {"analyst"}), ("accountant", {"accountant", "accounting"}),
        ("engineer", {"engineer", "engineering", "swe", "devops", "sdet"}),
        ("designer", {"designer", "design"}), ("administrator", {"administrator", "administration"}),
    ):
        if words & alternatives:
            return family
    return " ".join(sorted(words - TITLE_NOISE)) or normalize(title)


def role_text(description):
    paragraphs = []
    skip = False
    for line in description.splitlines():
        heading = normalize(line).strip()
        if len(heading.split()) <= 7:
            if re.fullmatch(r"(?:about us|about the company|who we are|benefits|our benefits|what we offer|why join us|how to apply|privacy|equal opportunities)", heading):
                skip = True
                continue
            if re.search(r"responsibilities|requirements|qualifications|your role|the role|essential skills|what you will|what youll", heading):
                skip = False
        if skip or re.search(r"equal opportunity employer|regardless of (?:race|gender)|privacy (?:notice|policy)", line, re.I):
            continue
        paragraphs.append(line)
    return normalize(" ".join(paragraphs))


def legal_employer(description):
    # Only an explicit applicant-employment declaration, not customers/partners/clients.
    match = re.search(r"\byou(?:['’]ll| will)\s+be employed by\s+([^,\n.;]{3,160})", description, re.I)
    if not match:
        return None
    name = match[1].strip()
    if not re.search(r"\b(?:Limited|Ltd|PLC|LLP|LLC|Inc|Corporation)\s*$", name, re.I):
        return None
    return company_key(name)


def structured_reference_key(row, evidence, legal):
    if not evidence or evidence.get("kind") != "jsonld_employer_reference":
        return None
    issuer = company_key(evidence.get("issuer"))
    if not issuer or issuer != company_key(row.get("company")):
        return None
    reference = evidence["reference"]
    if reference == str(row.get("source_job_id")):
        return None
    # Verified public Tesco recruitment-channel suffixes. No generic suffix stripping
    # or company aliasing: both the issuer and explicit legal-employer declaration bind it.
    channels = {"tesco": "TescoUK", "tescotechnology": "Technology"}
    if row["source"] == "linkedin" and legal == "tescostores" and issuer in channels:
        match = re.fullmatch(r"([0-9]{4,})" + re.escape(channels[issuer]), reference, re.I)
        if match:
            return "tesco_recruitment|" + legal + "|" + match[1]
    return "employer|" + issuer + "|" + reference


def trusted_recruitment_brands(left, right):
    return (left.get("legal_employer_key") == right.get("legal_employer_key") == "tescostores"
            and {left["company_key"], right["company_key"]} <= {"tesco", "tescotechnology"})


def profile(row, evidence=None):
    if evidence is None:
        evidence = row.get("matching_evidence")
    legal = legal_employer(row["description"])
    full_text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", row["description"])).strip().casefold()
    title = normalize(row["title"])
    words = title.split()
    references = set()
    pattern = r"\b(?:job|requisition|vacancy|position|req)\s*(?:id|ref(?:erence)?|number|no\.?|#)\s*[:#-]?\s*([a-z0-9][a-z0-9_./-]{3,})"
    for reference in re.findall(pattern, row["description"], re.I):
        reference = reference.rstrip("./-").lower()
        if any(character.isdigit() for character in reference):
            references.add(reference)
    text = role_text(row["description"])
    tokens = [word for word in text.split() if word not in STOP_WORDS and (len(word) > 2 or word in TECH)]
    counts = dict(Counter(tokens))
    title_tokens = sorted(set(words) - {"f", "m", "d", "fm", "fmd", "and", "or", "the", "uk", "hybrid", "remote"})
    levels = {"junior", "senior", "lead", "principal", "staff", "associate", "graduate"} & set(words)
    technologies = TECH & set(words)
    if technologies & {"dotnet", "csharp"}:
        technologies |= {"dotnet", "csharp"}
    teams = set()
    for name in re.findall(r"(?:our|the|within(?: the)?|join(?: the| our)?)\s+([A-Z][A-Za-z0-9&/-]*(?:\s+[A-Z][A-Za-z0-9&/-]*){0,4})\s+(?:team|Team|department|Department)\b", row["description"]):
        teams.update(set(normalize(name).split()) - {"engineering", "engineer", "development", "software", "technology"})
    posted = row.get("posted_at")
    postcode = re.search(r"\b([A-Z]{1,2}\d[A-Z\d]?)(?:\s*\d[A-Z]{2})?\b", row["location"], re.I)
    return {
        "id": row["id"], "source": row["source"], "company_key": company_key(row.get("company")),
        "legal_employer_key": legal, "source_reference_key": structured_reference_key(row, evidence, legal),
        "full_description_hash": hashlib.sha256(full_text.encode()).hexdigest(),
        "role_family": role_family(row["title"]), "location_key": location_key(row["location"]),
        "postcode": postcode[1].lower() if postcode else None,
        "title_tokens": title_tokens, "title_numbers": sorted(word for word in words if word.isdigit()),
        "levels": sorted(levels), "technologies": sorted(technologies), "references": sorted(references),
        "teams": sorted(teams),
        "tokens": counts, "shingles": sorted({" ".join(tokens[index:index + 3]) for index in range(len(tokens) - 2)}),
        "description_length": len(text), "work_type": row.get("work_type"),
        "salary_period": row.get("salary_period"),
        "salary_min": float(row["salary_min"]) if row.get("salary_min") is not None else None,
        "salary_max": float(row["salary_max"]) if row.get("salary_max") is not None else None,
        "posted_at": posted.timestamp() if isinstance(posted, datetime) else None,
        "removed": row.get("removed_at") is not None,
    }


def dice(left, right):
    left, right = set(left), set(right)
    return 2 * len(left & right) / (len(left) + len(right)) if left and right else 0.0


def contradiction(left, right):
    body_reference_match = bool(set(left["references"]) & set(right["references"]))
    source_reference_match = bool(left.get("source_reference_key") and left.get("source_reference_key") == right.get("source_reference_key"))
    reference_match = body_reference_match or source_reference_match
    if left["company_key"] and right["company_key"] and left["company_key"] != right["company_key"] and not trusted_recruitment_brands(left, right):
        return "different_company"
    if left["references"] and right["references"] and not body_reference_match:
        return "different_requisition"
    if left.get("source_reference_key") and right.get("source_reference_key") and not source_reference_match:
        return "different_source_requisition"
    if left["role_family"] != right["role_family"]:
        return "different_role_family"
    if left["location_key"] != right["location_key"] and not ({left["location_key"], right["location_key"]} & {"remote", "uk"}):
        return "different_workplace"
    if not reference_match:
        if left["title_numbers"] and right["title_numbers"] and left["title_numbers"] != right["title_numbers"]:
            return "different_title_identifier"
        if left["levels"] and right["levels"] and not set(left["levels"]) & set(right["levels"]):
            return "different_seniority"
        if left["technologies"] and right["technologies"] and not set(left["technologies"]) & set(right["technologies"]):
            return "different_title_specialization"
        if left["teams"] and right["teams"] and not set(left["teams"]) & set(right["teams"]):
            return "different_named_team"
        if left["postcode"] and right["postcode"] and left["postcode"] != right["postcode"]:
            return "different_postcode_area"
        if {left["work_type"], right["work_type"]} == {"full time", "part time"}:
            return "different_hours"
        if left["salary_period"] and left["salary_period"] == right["salary_period"]:
            a = left["salary_min"] or left["salary_max"]
            b = right["salary_min"] or right["salary_max"]
            if a and b and max(a, b) / min(a, b) >= 2:
                return "incompatible_salary_scale"
        if (left["removed"] or right["removed"]) and left["posted_at"] and right["posted_at"]:
            if abs(left["posted_at"] - right["posted_at"]) > 180 * 86400:
                return "historical_repost"
    return None


@dataclass(frozen=True)
class Decision:
    matched: bool
    reason: str
    scores: dict


def compare(left, right):
    conflict = contradiction(left, right)
    if conflict:
        return Decision(False, conflict, {})
    if not left["company_key"] or not right["company_key"]:
        return Decision(False, "unknown_company", {})
    title = dice(left["title_tokens"], right["title_tokens"])
    source_reference = bool(left.get("source_reference_key") and left.get("source_reference_key") == right.get("source_reference_key"))
    if left["company_key"] != right["company_key"]:
        corroborated = (trusted_recruitment_brands(left, right) and source_reference
                        and left["source"] == right["source"] == "linkedin"
                        and left["source_reference_key"].startswith("tesco_recruitment|")
                        and left["title_tokens"] == right["title_tokens"]
                        and left["location_key"] == right["location_key"]
                        and left["location_key"] not in ("remote", "uk")
                        and left["full_description_hash"] == right["full_description_hash"]
                        and min(left["description_length"], right["description_length"]) >= 600)
        return Decision(bool(corroborated), "scoped_recruitment_channel" if corroborated else "unverified_employer_brand",
                        {"title": round(title, 4)} if corroborated else {})
    references = set(left["references"]) & set(right["references"])
    if source_reference and title >= 0.4:
        return Decision(True, "structured_employer_reference", {"title": round(title, 4)})
    if references and title >= 0.4:
        return Decision(True, "employer_reference", {"title": round(title, 4)})
    if left["source"] == right["source"]:
        return Decision(False, "same_source_without_reference", {})
    a, b = left["tokens"], right["tokens"]
    if min(len(a), len(b)) < 25 or min(left["description_length"], right["description_length"]) < 220:
        return Decision(False, "insufficient_distinctive_text", {})
    def weight(word, count):
        return (1 + math.log(count)) * (2 if word in TECH else 1)
    va, vb = {word: weight(word, count) for word, count in a.items()}, {word: weight(word, count) for word, count in b.items()}
    cosine = sum(va[word] * vb[word] for word in va.keys() & vb.keys()) / (
        math.sqrt(sum(value ** 2 for value in va.values())) * math.sqrt(sum(value ** 2 for value in vb.values())))
    overlap = dice(a, b)
    shingles = dice(left["shingles"], right["shingles"])
    scores = {"title": round(title, 4), "description_cosine": round(cosine, 4),
              "description_overlap": round(overlap, 4), "description_shingles": round(shingles, 4)}
    remote_mismatch = left["location_key"] != right["location_key"] and "remote" in (left["location_key"], right["location_key"])
    if remote_mismatch and cosine < 0.94:
        return Decision(False, "uncertain_remote_workplace", scores)
    strong = title >= 0.55 and cosine >= 0.88 and overlap >= 0.68 and shingles >= 0.35
    reworded = title >= 0.75 and cosine >= 0.86 and overlap >= 0.78
    variant = title >= 0.25 and cosine >= 0.95 and overlap >= 0.88 and shingles >= 0.65 and len(set(a) & set(b) & TECH) >= 2
    return Decision(strong or reworded or variant, "distinctive_description" if strong or reworded or variant else "weak_similarity", scores)


def register_group(connection, identity, created_at):
    connection.execute("INSERT INTO canonical_groups (id, created_at) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                       (identity, created_at))


def record_evidence(connection, left, right, decision):
    if left["id"] > right["id"]:
        left, right = right, left
    connection.execute(
        "INSERT INTO dedupe_evidence (left_id, right_id, left_hash, right_hash, rule_version, reason, scores) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (left_id, right_id) DO UPDATE SET "
        "left_hash = EXCLUDED.left_hash, right_hash = EXCLUDED.right_hash, rule_version = EXCLUDED.rule_version, "
        "reason = EXCLUDED.reason, scores = EXCLUDED.scores",
        (left["id"], right["id"], left["content_hash"], right["content_hash"], RULE_VERSION, decision.reason, Jsonb(decision.scores)),
    )


def group_members(connection, canonical_id):
    rows = connection.execute(
        "SELECT j.*, f.profile FROM jobs j LEFT JOIN dedupe_features f ON f.job_id = j.id "
        "WHERE j.canonical_job_id = %s ORDER BY j.id", (canonical_id,),
    ).fetchall()
    return [(row, {**(row["profile"] or profile(row)), "removed": row["removed_at"] is not None}) for row in rows]


def deduplicate_listing(connection, identity):
    row = connection.execute("SELECT * FROM jobs WHERE id = %s", (identity,)).fetchone()
    if not row:
        return
    raw_evidence = connection.execute("SELECT kind, issuer, reference FROM listing_match_evidence WHERE job_id = %s AND content_hash = %s",
                                      (identity, row["content_hash"])).fetchone()
    evidence_hash = hashlib.sha256(json.dumps(raw_evidence, sort_keys=True).encode()).hexdigest() if raw_evidence else ""
    existing = connection.execute("SELECT content_hash, rule_version, evidence_hash FROM dedupe_features WHERE job_id = %s", (identity,)).fetchone()
    if existing and existing["content_hash"] == row["content_hash"] and existing["rule_version"] == RULE_VERSION and existing["evidence_hash"] == evidence_hash:
        return
    current = profile(row, raw_evidence)
    connection.execute("DELETE FROM dedupe_evidence WHERE left_id = %s OR right_id = %s", (identity, identity))
    register_group(connection, row["canonical_job_id"], row["first_seen_at"])
    connection.execute(
        "INSERT INTO dedupe_features (job_id, content_hash, rule_version, company_key, role_family, location_key, profile, legal_employer_key, evidence_hash) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (job_id) DO UPDATE SET "
        "content_hash = EXCLUDED.content_hash, rule_version = EXCLUDED.rule_version, company_key = EXCLUDED.company_key, "
        "role_family = EXCLUDED.role_family, location_key = EXCLUDED.location_key, profile = EXCLUDED.profile, "
        "legal_employer_key = EXCLUDED.legal_employer_key, evidence_hash = EXCLUDED.evidence_hash",
        (identity, row["content_hash"], RULE_VERSION, current["company_key"], current["role_family"], current["location_key"],
         Jsonb(current), current["legal_employer_key"], evidence_hash),
    )
    # Keep established identity on wording-only edits, but detach clear contradictions.
    peers = [(peer, features) for peer, features in group_members(connection, row["canonical_job_id"]) if peer["id"] != identity]
    if peers and any(contradiction(current, features) for _, features in peers):
        seed = str(uuid5(NAMESPACE_URL, identity))
        if connection.execute("SELECT 1 FROM jobs WHERE canonical_job_id = %s AND id <> %s LIMIT 1", (seed, identity)).fetchone():
            seed = str(uuid5(NAMESPACE_URL, identity + ":" + row["content_hash"]))
        register_group(connection, seed, row["first_seen_at"])
        connection.execute("UPDATE jobs SET canonical_job_id = %s WHERE id = %s", (seed, identity))
        row["canonical_job_id"] = seed
    if not current["company_key"]:
        return
    candidates = connection.execute(
        "SELECT j.id, j.canonical_job_id, j.removed_at, f.profile FROM dedupe_features f JOIN jobs j ON j.id = f.job_id "
        "WHERE (f.company_key = %s OR (f.legal_employer_key = %s AND %s::text IS NOT NULL)) AND f.role_family = %s AND f.rule_version = %s AND j.id <> %s "
        "AND (f.location_key = %s OR f.location_key IN ('remote', 'uk') OR %s IN ('remote', 'uk')) ORDER BY j.id",
        (current["company_key"], current["legal_employer_key"], current["legal_employer_key"], current["role_family"], RULE_VERSION,
         identity, current["location_key"], current["location_key"]),
    ).fetchall()
    groups = {row["canonical_job_id"]}
    for candidate in candidates:
        decision = compare(current, {**candidate["profile"], "removed": candidate["removed_at"] is not None})
        if decision.matched:
            groups.add(candidate["canonical_job_id"])
    ordered = connection.execute(
        "SELECT id FROM canonical_groups WHERE id = ANY(%s) ORDER BY created_order", (sorted(groups),),
    ).fetchall()
    accepted = []
    for group in ordered:
        members = group_members(connection, group["id"])
        if not accepted:
            # The existing group is always included, even after a source hides metadata.
            if group["id"] == row["canonical_job_id"] or all(compare(current, features).matched for _, features in members):
                accepted = members
                winner = group["id"]
            continue
        # Complete-link verification prevents A~B and B~C from blindly merging A!C.
        if all(left["id"] == right["id"] or compare(a, b).matched
               for left, a in accepted for right, b in members):
            for left, a in accepted:
                for right, b in members:
                    if left["id"] == right["id"]:
                        continue
                    decision = compare(a, b)
                    record_evidence(connection, left, right, decision)
            connection.execute("UPDATE jobs SET canonical_job_id = %s WHERE canonical_job_id = %s AND canonical_job_id <> %s",
                               (winner, group["id"], winner))
            accepted.extend(members)
    canonical = connection.execute("SELECT canonical_job_id FROM jobs WHERE id = %s", (identity,)).fetchone()["canonical_job_id"]
    for peer, features in group_members(connection, canonical):
        if peer["id"] != identity:
            decision = compare(current, features)
            if not decision.matched:
                decision = Decision(True, "historical_identity_without_contradiction", decision.scores)
            record_evidence(connection, row, peer, decision)


def backfill(connection):
    """Index legacy/new-rule rows without re-fetching pages or altering lifecycle counts."""
    total = 0
    while True:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(74201931)")
            rows = connection.execute(
                "SELECT j.id FROM jobs j LEFT JOIN dedupe_features f ON f.job_id = j.id "
                "WHERE f.job_id IS NULL OR f.content_hash <> j.content_hash OR f.rule_version <> %s "
                "ORDER BY j.first_seen_at, j.id LIMIT 100", (RULE_VERSION,),
            ).fetchall()
            for row in rows:
                deduplicate_listing(connection, row["id"])
        total += len(rows)
        if len(rows) < 100:
            return total

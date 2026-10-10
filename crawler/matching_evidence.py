"""Extract a public employer reference only after its listing identity has been verified."""

from crawler.dedupe import company_key


def structured_reference(source, identity, company, organization, identifier):
    # Reed's JobId is the board ID; no employer-reference interpretation is established.
    if source != "linkedin" or not isinstance(organization, dict) or not isinstance(identifier, dict):
        return None
    value, issuer = identifier.get("value"), identifier.get("name")
    if value is None or not isinstance(issuer, str) or not issuer.strip():
        return None
    reference = str(value).strip()
    if reference == str(identity) or str(identifier.get("propertyID", "")).casefold() == "jobid":
        return None
    if not company_key(issuer) or company_key(issuer) != company_key(organization.get("name")) or company_key(issuer) != company_key(company):
        return None
    if not reference or len(reference) > 512 or any(ord(character) < 32 for character in reference):
        return None
    return {"kind": "jsonld_employer_reference", "issuer": issuer.strip(), "reference": reference}

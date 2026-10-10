"""Resource policy for server-rendered public Indeed pages."""

from urllib.parse import parse_qs, urlsplit


def skip_reason(url, resource_type, mode="lean"):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    path = parsed.path.lower()
    if resource_type == "document" and host == "secure.indeed.com" and path.startswith("/auth"):
        return "account_or_anonymous_auth_gate"
    if resource_type in ("image", "font", "media"):
        return "unneeded_media"
    if resource_type == "stylesheet" and host.endswith(".indeed.com"):
        return "unneeded_stylesheet"
    if mode == "baseline":
        return None
    # Ordinary managed checks must retain their scripts, frames and requests.
    if host == "challenges.cloudflare.com" or host.endswith(".challenges.cloudflare.com") or "/cdn-cgi/" in path:
        return None
    if host == "t.indeed.com":
        query = parse_qs(parsed.query)
        if any("cloudflare-static-pages" in value for values in query.values() for value in values):
            return None
        return "unneeded_telemetry"
    if host == "c03.s3.indeed.com" and resource_type == "script":
        return "unneeded_frontend_bundle"
    if host == "d3fw5vlhllyvee.cloudfront.net" and path.startswith("/one-trust/"):
        return "unneeded_consent_ui"
    if resource_type in ("ping", "websocket"):
        return "unneeded_background_channel"
    return None

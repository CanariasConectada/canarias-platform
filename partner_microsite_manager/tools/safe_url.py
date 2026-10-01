# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""One rule for every link the public pages build from merchant data."""

import re
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")
# What a URL scheme looks like (RFC 3986), followed by its colon.
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
# ``host:port`` -- a colon that introduces a port, not a scheme.
_HOST_PORT_RE = re.compile(r"^[A-Za-z0-9.\-]+:\d+(?:[/?#]|$)")
# C0 controls and DEL: browsers drop them inside a scheme, which is how
# ``java\tscript:`` gets past a naive check.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def safe_http_url(url):
    """``url`` as an http(s) link a page can put in an ``href``/``src``,
    or ``""`` when it is anything else.

    - no scheme (``myshop.com``, ``localhost:8080``) -> ``https://`` added;
    - scheme-relative (``//host``) -> ``https:`` added;
    - ``http``/``https`` (any case) with a host -> kept;
    - any other scheme (``javascript:``, ``data:``, ``vbscript:``...), a
      control character anywhere, or whitespace inside the scheme -> ``""``.
    """
    url = (url or "").strip()
    if not url or _CONTROL_RE.search(url):
        return ""
    if url.startswith("//"):
        url = "https:" + url
    match = _SCHEME_RE.match(url)
    if match:
        if match.group(1).lower() not in ALLOWED_SCHEMES:
            if not _HOST_PORT_RE.match(url):
                return ""
            url = "https://" + url
    elif ":" in url.split("/", 1)[0]:
        # Something before the first slash has a colon but is not a valid
        # scheme (``java script:``, ``:foo``): refuse rather than guess.
        return ""
    else:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES or not parts.netloc:
        return ""
    return url

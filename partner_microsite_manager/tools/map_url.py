# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Turn any Google Maps link into a URL Google lets us put in an iframe.

Merchants and admins paste whatever the Google Maps "Share" button gives
them: a ``maps.app.goo.gl`` short link, a ``/maps/place/...`` page, a search.
Google answers all of those with ``X-Frame-Options: SAMEORIGIN``, so the
microsite iframe showed the browser's "can't open this page" instead of a
map. Only the embed endpoints (``/maps/embed`` and ``/maps?...&output=embed``)
may be framed.

Everything here is pure except :func:`resolve_short_map_url`, the only
function that touches the network; :func:`to_embeddable_map_url` receives it
as a parameter so callers (and tests) decide whether resolving is allowed.
"""

import html
import logging
import re
from urllib.parse import parse_qs, quote_plus, unquote_plus, urljoin, urlsplit

import requests

from odoo.addons.website_map_embed.models.res_partner import MAP_EMBED_URL

_logger = logging.getLogger(__name__)

DEFAULT_ZOOM = 17
RESOLVE_TIMEOUT = 5
RESOLVE_MAX_REDIRECTS = 5

# google.com, www.google.es, maps.google.co.uk, ...
_GOOGLE_HOST_RE = re.compile(
    r"^(?:[a-z0-9-]+\.)*google\.(?:[a-z]{2,3}|co\.[a-z]{2}|com\.[a-z]{2})$"
)
_SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl")
_PRECISE_COORDS_RE = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_AT_COORDS_RE = re.compile(
    r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:,(\d+(?:\.\d+)?)z)?"
)
# Query parameters that carry "what to show", in order of preference.
_QUERY_PARAMS = ("q", "query", "destination", "daddr", "ll")


def _host(url):
    return (urlsplit(url).hostname or "").lower()


def is_google_host(host):
    return bool(_GOOGLE_HOST_RE.match(host or ""))


def is_short_map_url(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "maps.app.goo.gl":
        return True
    return host == "goo.gl" and parts.path.startswith("/maps")


def is_google_maps_url(url):
    """True for any http(s) Google Maps link, embeddable or not (short too).

    The scheme is part of the answer: callers put these links in ``src`` and
    ``href`` attributes, and ``javascript://www.google.com/maps`` is not one.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if is_short_map_url(url):
        return True
    if not is_google_host(host):
        return False
    return host.startswith("maps.") or parts.path.startswith("/maps")


def is_embeddable_map_url(url):
    """True when Google serves ``url`` in a frame (embed endpoints only)."""
    parts = urlsplit(url)
    if not is_google_host((parts.hostname or "").lower()):
        return False
    if parts.path.startswith("/maps/embed"):
        return True
    return "embed" in parse_qs(parts.query).get("output", [])


def is_share_link(url):
    """True for a Google Maps link that is not itself an embed URL.

    Those are the links worth keeping for a "View on Google Maps" button;
    an embed URL (even an HTML-escaped copy of one) opens a bare map.
    """
    url = html.unescape(_with_scheme(url))
    return is_google_maps_url(url) and not is_embeddable_map_url(url)


def _with_scheme(url):
    url = (url or "").strip()
    if url.startswith("//"):
        return "https:" + url
    if url and not urlsplit(url).scheme:
        return "https://" + url
    return url


def _embed(query, zoom=None):
    try:
        zoom = int(float(zoom)) if zoom else DEFAULT_ZOOM
    except ValueError:
        zoom = DEFAULT_ZOOM
    zoom = min(max(zoom, 1), 21)
    return MAP_EMBED_URL.format(query=quote_plus(query, safe=","), zoom=zoom)


def _path_segments(path):
    return [unquote_plus(s) for s in path.split("/") if s]


def _convert_google_url(url):
    """Embeddable form of a (non-short) Google Maps URL, or ``None``."""
    parts = urlsplit(url)
    unquoted = unquote_plus(url)
    segments = _path_segments(parts.path)
    params = parse_qs(parts.query)
    at = _AT_COORDS_RE.search(unquoted)
    zoom = at.group(3) if at else None

    # 1. The pin itself: /place/.../data=...!3d<lat>!4d<lng>.
    precise = _PRECISE_COORDS_RE.search(unquoted)
    if precise:
        return _embed(f"{precise.group(1)},{precise.group(2)}", zoom)

    # 2. What the link names: /place/<name>, /search/<query>, /dir/../<to>.
    kind, text = None, ""
    for kind in ("place", "search", "dir"):
        if kind in segments:
            rest = segments[segments.index(kind) + 1 :]
            rest = [s for s in rest if not s.startswith(("@", "data="))]
            if rest:
                text = rest[-1] if kind == "dir" else rest[0]
            break
    else:
        kind = None
    # A place page is centred on its pin, so its @ is the place itself.
    if kind == "place" and at:
        return _embed(f"{at.group(1)},{at.group(2)}", zoom)
    # 3. ?q= / ?query= / ?destination= ...
    if not text:
        for name in _QUERY_PARAMS:
            value = params.get(name, [""])[0].strip()
            if value:
                text = value
                break
    if text:
        return _embed(text, zoom or params.get("z", [None])[0])
    # 4. Only a viewport: /maps/@lat,lng,zoom.
    if at:
        return _embed(f"{at.group(1)},{at.group(2)}", zoom)
    return None


def to_embeddable_map_url(url, resolver=None):
    """Best embeddable form of ``url``; the input itself when none exists.

    - Google embed URLs are kept (HTML-escaped ``&amp;`` separators, copied
      from an iframe's source, are decoded: once QWeb escapes the attribute
      again they would reach Google as literal ``amp;`` parameters);
    - other Google Maps URLs become ``maps.google.com/maps?q=...&output=embed``;
    - short links go through ``resolver`` (``url -> final url or None``)
      first; without a resolver, or when it fails, the input is returned;
    - anything else (non-Google, non-https, junk) is returned untouched: the
      scheme constraint on the field judges it, not this function.
    """
    original = (url or "").strip()
    if not original:
        return original
    candidate = _with_scheme(original)
    if urlsplit(candidate).scheme.lower() not in ("http", "https"):
        return original
    if not is_google_maps_url(candidate):
        return original
    if is_short_map_url(candidate):
        resolved = resolver(candidate) if resolver else None
        if not resolved or is_short_map_url(resolved):
            return original
        candidate = resolved
    if "&amp;" in candidate:
        candidate = html.unescape(candidate)
    if is_embeddable_map_url(candidate):
        if candidate.startswith("http://"):
            candidate = "https://" + candidate[len("http://") :]
        return candidate if candidate != _with_scheme(original) else original
    return _convert_google_url(candidate) or original


def _allowed_hop(url):
    host = _host(url)
    return urlsplit(url).scheme == "https" and (
        host in _SHORT_HOSTS or is_google_host(host)
    )


def resolve_short_map_url(
    url, timeout=RESOLVE_TIMEOUT, max_redirects=RESOLVE_MAX_REDIRECTS
):
    """Follow a short Maps link's redirects; the first Maps URL it reaches.

    One request per hop, no cookies, redirects read by hand so every hop can
    be checked: the chain may only visit Google hosts over https (a short
    link is user input, and this runs on the server). Stops as soon as a
    hop is a regular Maps URL -- its page is never downloaded, so Google's
    consent wall never comes into play. Returns ``None`` on any failure.
    """
    current = url
    try:
        for _hop in range(max_redirects):
            if not _allowed_hop(current):
                _logger.warning("Map link %s redirected off Google: %s", url, current)
                return None
            if not is_short_map_url(current):
                if _host(current) == "consent.google.com":
                    target = parse_qs(urlsplit(current).query).get("continue", [""])[0]
                    if target and _allowed_hop(target):
                        current = target
                        continue
                    return None
                return current
            response = requests.get(
                current,
                allow_redirects=False,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; map-link-resolver)"},
                stream=True,
            )
            response.close()
            location = response.headers.get("Location")
            if response.status_code not in (301, 302, 303, 307, 308) or not location:
                return None
            current = urljoin(current, location)
        return (
            current if _allowed_hop(current) and not is_short_map_url(current) else None
        )
    except requests.RequestException as error:
        _logger.warning("Could not resolve map link %s: %s", url, error)
        return None

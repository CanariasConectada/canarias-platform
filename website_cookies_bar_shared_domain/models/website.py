# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import api, models

SHARED_DOMAIN_PARAM = "website.cookies_bar_shared_domain"
CONSENT_COOKIE = "website_cookies_bar"

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_MAX_DOMAIN_LENGTH = 253

# Second-level labels registries use to build public suffixes under a country
# code ("co.uk", "com.es", "gob.es"...). A cookie scoped to one of those would
# be shared with every unrelated site registered below it. This is a
# heuristic, NOT the Public Suffix List: browsers hold the real list and refuse
# such a `Domain=` on their own, and the frontend falls back to a host-only
# cookie when the browser does refuse it.
_PUBLIC_SECOND_LEVEL_LABELS = frozenset(
    {
        "ac",
        "co",
        "com",
        "edu",
        "go",
        "gob",
        "gov",
        "int",
        "mil",
        "ne",
        "net",
        "nom",
        "or",
        "org",
    }
)


def normalize_shared_domain(value):
    """Return the registrable domain held by ``value``, or ``""`` if invalid.

    Accepted: a bare ASCII hostname with at least two labels
    (``example.com``); case, surrounding blanks, one leading dot and one
    trailing dot are forgiven. An internationalised name must be given in its
    punycode form.

    Rejected (``""``): anything carrying a scheme, a path, a port, userinfo or
    blanks; a single label (``es``, ``localhost``); an IP address; a
    public-suffix-like pair such as ``co.uk`` or ``com.es``.
    """
    domain = (value or "").strip().lower()
    if domain.startswith("."):
        domain = domain[1:]
    if domain.endswith("."):
        domain = domain[:-1]
    if not domain or len(domain) > _MAX_DOMAIN_LENGTH:
        return ""
    labels = domain.split(".")
    if len(labels) < 2:
        return ""
    # Also rules out scheme, path, port, userinfo, blanks and IPv6 literals:
    # none of ":/@[] " can be part of a label.
    if not all(_LABEL_RE.match(label) for label in labels):
        return ""
    # A numeric last label is an IPv4 address (or nothing registrable).
    if labels[-1].isdigit():
        return ""
    if (
        len(labels) == 2
        and len(labels[1]) == 2
        and labels[0] in _PUBLIC_SECOND_LEVEL_LABELS
    ):
        return ""
    return domain


def normalize_host(host):
    """Lowercased hostname of a ``Host`` header value, without its port."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        # IPv6 literal, "[::1]:8069": never matches a domain name anyway.
        return host.partition("]")[0] + "]"
    host = host.partition(":")[0]
    return host[:-1] if host.endswith(".") else host


def shared_domain_for_host(host, shared_domain):
    """Return ``shared_domain`` if ``host`` belongs to it, else ``""``.

    ``host`` belongs to the domain when it IS the domain or ends with
    ``"." + domain``. A plain suffix match is not enough:
    ``notcanariasconectada.es`` must not match ``canariasconectada.es``.
    """
    domain = normalize_shared_domain(shared_domain)
    hostname = normalize_host(host)
    if domain and (hostname == domain or hostname.endswith("." + domain)):
        return domain
    return ""


class Website(models.Model):
    _inherit = "website"

    @api.model
    def _cookies_bar_shared_domain(self):
        """Validated shared consent domain of this database (``""`` = off)."""
        value = self.env["ir.config_parameter"].sudo().get_param(SHARED_DOMAIN_PARAM)
        return normalize_shared_domain(value)

    @api.model
    def _cookies_bar_shared_domain_for_host(self, host):
        """Shared consent domain that applies to ``host`` (``""`` = none)."""
        return shared_domain_for_host(host, self._cookies_bar_shared_domain())

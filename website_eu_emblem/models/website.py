# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import models
from odoo.http import request

# The statement is empty by default, and that is deliberate. The EU's own
# visual identity rules require the emblem to appear WITH the name of the fund
# that paid for the work ("Financiado por la Unión Europea – NextGenerationEU",
# "FEDER – Una manera de hacer Europa", …), and which one applies is a fact
# about the grant, not something this module may guess. Leaving it blank shows
# the emblem alone and lets whoever administers the grant fill in the exact
# wording from Settings, without a deploy.
PARAM_ENABLED = "website_eu_emblem.enabled"
PARAM_STATEMENT = "website_eu_emblem.statement"
PARAM_URL = "website_eu_emblem.url"

FALSEY = ("False", "false", "0", "")

# Paths whose page already carries the funding strip inside the auth card
# (module ``website_login_branding``); a second copy in the footer would be a
# duplicate on the one page a visitor scrutinises the most. Matched after an
# optional language prefix (``/es/web/login``) since these routes are
# multilang on a website.
NO_FUNDING_FOOTER_RE = re.compile(
    r"^(?:/[a-z]{2,3}(?:[_-][A-Za-z]{2,4})?)?/web/(?:login|signup|reset_password)(?:/|$)"
)

# Substrings that, found in a page's arch, prove the page already shows the
# strip on its own: the legacy filestore attachment (952) the migrated
# homepages point at, the file name used by every copy shipped so far, and the
# dynamic microsite template that renders the strip on each microsite home.
FUNDING_STRIP_MARKERS = (
    "logos_subvenciones.png",
    "/web/image/952/subvenciones.png",
    "subvenciones.png",
    "partner_microsite_manager.microsite_homepage_content",
)


class Website(models.Model):
    _inherit = "website"

    def _eu_emblem_values(self):
        """Everything the header template needs, in one read.

        A method rather than three lookups inside the template: the header
        renders on every page of 218 websites, and a template that reaches
        into ``ir.config_parameter`` itself is both slower to read and harder
        to test than one that receives a dict.
        """
        params = self.env["ir.config_parameter"].sudo()
        return {
            "enabled": params.get_param(PARAM_ENABLED, "True") not in FALSEY,
            "statement": params.get_param(PARAM_STATEMENT, "") or "",
            "url": params.get_param(PARAM_URL, "") or "",
        }

    def _cc_show_funding_footer(self, main_object=None):
        """Whether the platform-wide funding strip belongs at the foot of
        the page being rendered.

        Asked for on 2026-09-15: the combined FEDER / NextGenerationEU strip
        at the foot of EVERY page of the platform, discreet, and never twice
        on the same page. Two families of pages already show it:

        * the login / signup / password-reset card (``website_login_branding``),
        * pages whose own content carries it: the migrated microsite
          homepages (``/web/image/952/subvenciones.png``), the dynamic
          microsite homepage template, and any page an editor pasted the
          strip into.

        Cheap on purpose: the layout calls this once per page. The path test
        is a regex on the request, and the arch test reads ``arch_db`` of the
        page's own view, a single row the ORM has usually fetched already to
        render the page. Read with ``lang=None`` (the ``en_US`` base value):
        every marker lives in a ``src`` or ``t-call`` attribute, which
        ``xml_translate`` never translates, so the base arch contains the
        marker whenever any translation does.
        """
        if request and NO_FUNDING_FOOTER_RE.match(request.httprequest.path or ""):
            return False
        view = None
        name = getattr(main_object, "_name", None)
        if name == "website.page":
            view = main_object.sudo().view_id
        elif name == "ir.ui.view":
            view = main_object.sudo()
        if view:
            arch = view.with_context(lang=None).arch_db or ""
            if any(marker in arch for marker in FUNDING_STRIP_MARKERS):
                return False
        return True

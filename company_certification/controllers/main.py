# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

# Strongest first: this is the sort order of the public holder list and the
# order the level filter is drawn in, not merely a set of valid values.
LEVEL_ORDER = ["gold", "silver", "bronze"]

# A day, not Odoo's year-long static cache: the badge URL is keyed by the
# vertical's code, so replacing the image does not change it and a longer
# max-age would leave the old seal on visitors' screens for months.
BADGE_CACHE_SECONDS = 60 * 60 * 24


class CompanyCertificationController(http.Controller):
    """Website entry points to start a certification evaluation.

    The heavy lifting (cooldown, answer creation) lives in
    ``survey.user_input._start_certification_evaluation``; this controller
    only translates the outcome into friendly website pages.
    """

    def _get_certification_type(self, code):
        return (
            request.env["certification.type"]
            .sudo()
            .search([("code", "=", code)], limit=1)
        )

    @http.route(
        "/certification/<string:code>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def certification_landing(self, code, **kwargs):
        """Public page of one vertical: what it is, and its training material.

        Read as sudo on purpose — visitors have no access to
        ``certification.type``, and only the handful of presentation fields
        below ever reach the template. An unpublished or unknown vertical is
        a plain 404: answering 200 with an empty page would get it indexed.
        """
        cert_type = self._get_certification_type(code)
        if not cert_type or not cert_type.landing_published:
            return request.not_found()
        level = kwargs.get("level") if kwargs.get("level") in LEVEL_ORDER else None
        holders = self._get_certified_companies(cert_type)
        return request.render(
            "company_certification.certification_landing",
            {
                "cert_type": cert_type,
                "materials": cert_type.material_ids.filtered("attachment_id"),
                "holders": [h for h in holders if not level or h["level"] == level],
                "level_counts": self._count_by_level(holders),
                "level": level,
                "base_url": "/certification/%s" % cert_type.code,
            },
        )

    def _get_certified_companies(self, cert_type):
        """The companies currently holding this seal, ready for the template.

        Flattened to plain dicts on purpose: the template runs in a public
        request whose user cannot read ``res.company``, and handing it a sudo
        recordset would put every field of every company one dotted attribute
        away from being rendered. Only what the card shows crosses over.

        Ordered by level then score so the strongest seals lead, which is what
        makes the page worth landing on.
        """
        statuses = (
            request.env["res.company.certification"]
            .sudo()
            .search([("type_id", "=", cert_type.id)])
            .filtered(lambda status: status._is_valid())
        )
        website = request.env["website"].sudo()
        holders = []
        for status in statuses:
            company = status.company_id
            # A company with no microsite has nowhere to send the visitor;
            # a card that links to the shop it is about is the whole point.
            #
            # Filtered on the domain inside the search rather than after it:
            # ``auto_microsite_generator`` creates a website the moment a
            # company is created and only fills the domain in later, so a
            # company can own both a blank placeholder and its real site. A
            # plain limit=1 returns whichever was created first and silently
            # dropped the shop from this list.
            site = website.search(
                [("company_id", "=", company.id), ("domain", "!=", False)],
                limit=1,
            )
            if not site:
                continue
            holders.append(
                {
                    "name": company.name,
                    "url": site.domain,
                    "level": status.level,
                    "level_label": status._get_level_label(),
                    "score": int(status.score),
                    "logo": company.logo,
                    "company_id": company.id,
                }
            )
        holders.sort(key=lambda h: (LEVEL_ORDER.index(h["level"]), -h["score"]))
        return holders

    @staticmethod
    def _count_by_level(holders):
        counts = {level: 0 for level in LEVEL_ORDER}
        for holder in holders:
            counts[holder["level"]] = counts.get(holder["level"], 0) + 1
        return counts

    @http.route(
        "/certification/<string:code>/badge",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def certification_badge(self, code, **kwargs):
        """Serve the seal image of a published vertical.

        A route rather than ``/web/image/certification.type/...`` because the
        latter checks read access on the record, and visitors have none: the
        model also carries the scoring thresholds and the vertical's security
        groups, which is not something to open up for the sake of a picture.
        This exposes exactly one field of the published verticals.

        The alternative was inlining it with ``image_data_uri``, which put a
        258 KB base64 blob in the HTML of every microsite homepage — repeated
        on each page view, never cached and never shared between shops.
        """
        cert_type = self._get_certification_type(code)
        if (
            not cert_type
            or not cert_type.landing_published
            or not cert_type.badge_image
        ):
            return request.not_found()
        stream = request.env["ir.binary"]._get_image_stream_from(
            cert_type, "badge_image"
        )
        # Public + a day of cache: the seal changes about never, and it is the
        # same bytes for every shop holding it.
        stream.public = True
        return stream.get_response(max_age=BADGE_CACHE_SECONDS)

    @http.route(
        "/certification/<string:code>/start",
        type="http",
        auth="user",
        website=True,
    )
    def certification_start(self, code, **kwargs):
        """Start (or refuse with an explanation) a real evaluation."""
        cert_type = self._get_certification_type(code)
        if not cert_type:
            return request.render(
                "company_certification.certification_error",
                {"error": _("Unknown certification type.")},
            )
        user = request.env.user
        if not user.company_id:
            return request.render(
                "company_certification.certification_no_company",
                {"cert_type": cert_type},
            )
        last = request.env["survey.user_input"]._get_last_done_attempt(
            cert_type, user.company_id
        )
        if (
            last
            and last.next_attempt_date
            and last.next_attempt_date > fields.Date.today()
        ):
            return request.render(
                "company_certification.certification_cooldown",
                {"next_date": last.next_attempt_date, "cert_type": cert_type},
            )
        try:
            url = request.env["survey.user_input"]._start_certification_evaluation(
                cert_type
            )
        except UserError as error:
            return request.render(
                "company_certification.certification_error", {"error": str(error)}
            )
        return request.redirect(url)

    @http.route("/certification/<string:code>/close", type="http", auth="user")
    def certification_close(self, code, **kwargs):
        """Send the user back to the vertical's backend evaluation list."""
        cert_type = self._get_certification_type(code)
        if cert_type and cert_type.action_id:
            return request.redirect("/odoo/action-%d" % cert_type.action_id.id)
        return request.redirect("/odoo")

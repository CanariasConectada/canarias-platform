# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from urllib.parse import quote_plus

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools.opening_hours import MAX_RANGES_PER_DAY, parse_opening_hours

# Weekday names shown on the public microsite, indexed like date.weekday().
# They are template terms in views/microsite_templates.xml as well, but the
# model needs them to build the schedule lines for QWeb.
WEEKDAY_LABELS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class ResCompany(models.Model):
    _inherit = "res.company"

    # ------------------------------------------------------------------
    # Microsite content, edited on the company form ("Microsite" tab).
    # The public homepage template reads these fields at render time, so
    # saving the form is enough to update the live microsite.
    # ------------------------------------------------------------------
    has_microsite = fields.Boolean(
        compute="_compute_has_microsite",
        help="True when the company has its own website, i.e. a microsite.",
    )
    microsite_name = fields.Char(
        string="Trade Name",
        help="Public name shown on the microsite. " "Falls back to the company name.",
    )
    microsite_button_text = fields.Char(
        string="Hero Button Label",
        help="Label of the call-to-action button of the hero section. "
        "Falls back to 'Shop'.",
    )
    microsite_hero_image = fields.Image(string="Hero Image")
    microsite_intro_title = fields.Char(string="Intro Banner Title")
    microsite_intro_image = fields.Image(string="Intro Banner Image")
    microsite_banner_title = fields.Char(string="Closing Banner Title")
    microsite_banner_image = fields.Image(string="Closing Banner Image")
    microsite_opening_hours = fields.Char(
        string="Opening Hours",
        help="Compact notation, e.g. "
        "L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00 "
        "(L M X J V S D = Monday..Sunday, at most two ranges per day).",
    )
    microsite_delivery_info = fields.Char(string="Delivery / Shipping")
    microsite_parking_info = fields.Char(string="Parking / Directions")
    microsite_about_title = fields.Char(string="About Title")
    microsite_about_text = fields.Text(string="About Text")
    microsite_services_title = fields.Char(string="Services Title")
    microsite_services_text = fields.Text(string="Services Text")
    microsite_map_url = fields.Char(
        string="Custom Map URL",
        help="Embeddable map URL. When empty, a Google Maps embed is built "
        "from the company address.",
    )
    microsite_homepage_page_id = fields.Many2one(
        "website.page",
        string="Microsite Homepage",
        readonly=True,
        copy=False,
        help="Homepage published by the 'Publish Homepage' action.",
    )

    @api.depends("website_id")
    def _compute_has_microsite(self):
        for company in self:
            company.has_microsite = bool(company.website_id)

    @api.constrains("microsite_opening_hours")
    def _check_microsite_opening_hours(self):
        for company in self:
            value = company.microsite_opening_hours
            if not value:
                continue
            parsed = parse_opening_hours(value)
            if parsed is None:
                raise ValidationError(
                    _(
                        "Invalid opening hours format. Expected e.g. "
                        "'L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00'."
                    )
                )
            for day, ranges in parsed.items():
                if len(ranges) > MAX_RANGES_PER_DAY:
                    raise ValidationError(
                        _(
                            "Too many time ranges for %(day)s: at most "
                            "%(limit)s per day (morning and afternoon).",
                            day=WEEKDAY_LABELS[day],
                            limit=MAX_RANGES_PER_DAY,
                        )
                    )

    # ------------------------------------------------------------------
    # Template helpers (called from QWeb at render time)
    # ------------------------------------------------------------------
    def _get_microsite_opening_hours_lines(self):
        """Weekly schedule as ``[(day_label, 'HH:MM - HH:MM / ...'), ...]``.

        Only the days with opening hours are returned, in week order.
        Returns an empty list when the field is empty or unparsable, so the
        template simply hides the section.
        """
        self.ensure_one()
        parsed = parse_opening_hours(self.microsite_opening_hours)
        if not parsed:
            return []
        return [
            (
                WEEKDAY_LABELS[day],
                " / ".join(f"{start} - {end}" for start, end in parsed[day]),
            )
            for day in sorted(parsed)
        ]

    def _get_microsite_map_url(self):
        """Embeddable map URL: the custom one, or one built from the address.

        Returns an empty string when there is nothing to show, so the
        template hides the map block entirely.
        """
        self.ensure_one()
        if self.microsite_map_url:
            return self.microsite_map_url
        partner = self.partner_id
        address = " ".join(
            part for part in (partner.street, partner.city, partner.zip) if part
        )
        if not address.strip():
            return ""
        return (
            "https://maps.google.com/maps?q="
            f"{quote_plus(address)}&z=13&ie=UTF8&output=embed"
        )

    # ------------------------------------------------------------------
    # Homepage publication (explicit action, one-time per website)
    # ------------------------------------------------------------------
    def _get_microsite_homepage_arch(self):
        """Arch of the homepage view: a thin wrapper around the dynamic
        content template. All the actual content is rendered at request
        time from the company fields, so this arch never needs a re-sync.
        """
        self.ensure_one()
        return (
            '<t t-name="partner_microsite_manager.'
            f'microsite_homepage_{self.id}">\n'
            '    <t t-call="website.layout">\n'
            '        <div id="wrap" class="oe_structure">\n'
            '            <t t-call="'
            'partner_microsite_manager.microsite_homepage_content"/>\n'
            "        </div>\n"
            "    </t>\n"
            "</t>\n"
        )

    def action_publish_microsite_homepage(self):
        """Create or replace the homepage of the company website with the
        dynamic microsite template.

        Explicit by design: nothing is ever written to a website unless a
        backoffice user pushes the button, and only the company's own
        website can be touched (``website_id`` is the website whose
        ``company_id`` is this company).
        """
        for company in self:
            website = company.website_id
            if not website:
                raise UserError(
                    _(
                        "Company %(name)s has no website yet. Create its "
                        "website first (Settings > Websites).",
                        name=company.display_name,
                    )
                )
            company._publish_microsite_homepage(website)
        return True

    def _publish_microsite_homepage(self, website):
        self.ensure_one()
        # sudo: microsite editors are not necessarily website designers,
        # and the target website is guaranteed to be the company's own.
        view_model = self.env["ir.ui.view"].sudo()
        page_model = self.env["website.page"].sudo()
        arch = self._get_microsite_homepage_arch()
        view_key = f"partner_microsite_manager.microsite_homepage_{self.id}"
        page = page_model.search(
            [("website_id", "=", website.id), ("url", "=", "/")], limit=1
        )
        if page:
            page.view_id.write({"arch_db": arch, "key": view_key})
        else:
            view = view_model.create(
                {
                    "name": f"Microsite Homepage - {self.name}",
                    "type": "qweb",
                    "key": view_key,
                    "arch_db": arch,
                    "website_id": website.id,
                }
            )
            page = page_model.create(
                {
                    "name": f"Microsite Homepage - {self.name}",
                    "url": "/",
                    "view_id": view.id,
                    "website_id": website.id,
                    "is_published": True,
                }
            )
        page.is_published = True
        self.microsite_homepage_page_id = page

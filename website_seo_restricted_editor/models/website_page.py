# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import AccessError

# What the "Optimize SEO" dialog writes on a page. Anything else on the
# record (url, name, publication, indexing rules of the view...) stays with
# the designers.
SEO_FIELDS = frozenset(
    {
        "website_meta_title",
        "website_meta_description",
        "website_meta_keywords",
        "website_meta_og_img",
        "website_indexed",
    }
)


class WebsitePage(models.Model):
    _inherit = "website.page"

    def write(self, vals):
        """A restricted editor may only touch the SEO fields.

        The ACL this module adds gives the group write access to the model
        because the SEO dialog saves through a plain ``write``; the record
        rule scopes it to the pages of their own site; this narrows it to
        the fields that dialog owns.
        """
        if (
            not self.env.su
            and not self.env.user.has_group("website.group_website_designer")
            and set(vals) - SEO_FIELDS
        ):
            raise AccessError(
                _(
                    "You may only optimise the SEO of this page. "
                    "Changing %(fields)s needs the website designer group.",
                    fields=", ".join(sorted(set(vals) - SEO_FIELDS)),
                )
            )
        return super().write(vals)

    def unlink(self):
        """Deleting a page is not optimising it.

        Core's ``unlink`` removes the page's view first and then unlinks an
        empty recordset, so the page ACL never gets a say: whoever may delete
        views of the site could delete its pages. Designers only.
        """
        if not self.env.su and not self.env.user.has_group(
            "website.group_website_designer"
        ):
            raise AccessError(_("Deleting a page needs the website designer group."))
        return super().unlink()

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMicrositeSettings(TransactionCase):
    """The corporate microsite look is now editable from website settings."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Settings Test Company"})
        cls.website = cls.env["website"].create(
            {
                "name": "Settings Test Website",
                "company_id": cls.company.id,
            }
        )

    def test_is_microsite_themed_off_by_default(self):
        self.assertFalse(self.website.is_microsite_themed)

    def test_settings_toggle_writes_website(self):
        settings = self.env["res.config.settings"].create(
            {"website_id": self.website.id}
        )
        settings.is_microsite_themed = True
        settings.set_values()
        self.website.invalidate_recordset(["is_microsite_themed"])
        self.assertTrue(self.website.is_microsite_themed)

    def test_settings_reads_website_value(self):
        self.website.is_microsite_themed = True
        settings = self.env["res.config.settings"].create(
            {"website_id": self.website.id}
        )
        self.assertTrue(settings.is_microsite_themed)

    def test_field_present_in_website_settings_view(self):
        # Rendering the website settings form applies our inherited view;
        # a broken xpath would raise here, and the field must be present.
        arch = self.env["res.config.settings"].get_view(
            view_id=self.env.ref("website.res_config_settings_view_form").id,
            view_type="form",
        )["arch"]
        self.assertIn("is_microsite_themed", arch)

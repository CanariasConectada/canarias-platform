# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import tagged
from odoo.tests.common import HttpCase

NO_MAIL_CTX = {"no_reset_password": True, "mail_create_nolog": True, "mail_notrack": True}


@tagged("post_install", "-at_install")
class TestNoValidationBanner(HttpCase):
    """The courses page asks portal accounts to verify, never internal ones."""

    def _user(self, login, groups):
        return self.env["res.users"].with_context(**NO_MAIL_CTX).create(
            {"name": login, "login": login, "password": login + "_pw12345", "email": login + "@example.com", "group_ids": [(6, 0, [self.env.ref(g).id for g in groups])]}
        )

    def _courses_page(self, user):
        self.authenticate(user.login, user.login + "_pw12345")
        response = self.url_open("/slides", allow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_a_merchant_with_zero_karma_is_not_asked_to_verify(self):
        merchant = self._user("banner_merchant", ["base.group_user"])
        self.assertEqual(merchant.karma, 0)
        self.assertNotIn("o_wprofile_email_validation_container", self._courses_page(merchant))

    def test_a_portal_account_still_is(self):
        portal = self._user("banner_portal", ["base.group_portal"])
        self.assertIn("o_wprofile_email_validation_container", self._courses_page(portal))

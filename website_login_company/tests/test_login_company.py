# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re
from unittest.mock import MagicMock, patch

from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.website_login_company.controllers.home import WebsiteLoginCompanyHome

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


class TestLoginCompanyGuards(TransactionCase):
    """The cookie helper must be a strict no-op without a website."""

    def setUp(self):
        super().setUp()
        self.controller = WebsiteLoginCompanyHome()

    def test_no_request_is_noop(self):
        """No bound HTTP request (XML-RPC, cron): nothing happens."""
        with patch(
            "odoo.addons.website_login_company.controllers.home.request",
            None,
        ):
            self.controller._set_website_company_cookie(self.env.user.id)

    def test_no_website_no_host_is_noop(self):
        """Websiteless request without host: no cookie, no crash."""
        fake_request = MagicMock(spec=["httprequest", "env", "future_response"])
        fake_request.httprequest.host = ""
        with patch(
            "odoo.addons.website_login_company.controllers.home.request",
            fake_request,
        ):
            self.controller._set_website_company_cookie(self.env.user.id)
        fake_request.future_response.set_cookie.assert_not_called()

    def test_website_without_company_is_noop(self):
        """A matching website without company must not set the cookie."""
        fake_website = MagicMock()
        fake_website.company_id = self.env["res.company"].browse()
        fake_request = MagicMock(spec=["httprequest", "env", "future_response"])
        fake_request.httprequest.host = "example.test:8069"
        fake_request.env["website"].sudo().search.return_value = fake_website
        with patch(
            "odoo.addons.website_login_company.controllers.home.request",
            fake_request,
        ):
            self.controller._set_website_company_cookie(self.env.user.id)
        fake_request.future_response.set_cookie.assert_not_called()

    def test_login_redirect_survives_helper_crash(self):
        """Any error in the helper must not break the login redirect."""
        with patch.object(
            WebsiteLoginCompanyHome,
            "_set_website_company_cookie",
            side_effect=RuntimeError("boom"),
        ), patch(
            "odoo.addons.web.controllers.home._get_login_redirect_url",
            return_value="/odoo",
        ):
            result = self.controller._login_redirect(self.env.user.id)
        self.assertEqual(result, "/odoo")


@tagged("post_install", "-at_install")
class TestLoginCompanyCookie(HttpCase):
    """End-to-end login through /web/login with a real website."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_main = cls.env.ref("base.main_company")
        cls.company_shop = cls.env["res.company"].create({"name": "Shop Co"})
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.company_id = cls.company_shop
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Merchant",
                    "login": "merchant@example.test",
                    "password": "merchant-password",
                    "company_id": cls.company_main.id,
                    "company_ids": [(6, 0, [cls.company_main.id, cls.company_shop.id])],
                }
            )
        )

    def _post_login(self, login, password):
        page = self.url_open("/web/login")
        self.assertEqual(page.status_code, 200)
        csrf_token = CSRF_RE.search(page.text).group(1)
        return self.url_open(
            "/web/login",
            data={
                "login": login,
                "password": password,
                "csrf_token": csrf_token,
            },
        )

    def _set_website_domain_to_test_host(self):
        self.website.domain = self.base_url()

    def test_login_sets_website_company_cookie(self):
        """User with access: cids is forced to the website company."""
        self._set_website_domain_to_test_host()
        response = self._post_login("merchant@example.test", "merchant-password")
        self.assertEqual(response.status_code, 200)
        cids = self.opener.cookies.get("cids")
        self.assertEqual(cids, str(self.company_shop.id))

    def test_login_without_access_keeps_default(self):
        """User without access to the website company: cookie not forced."""
        self._set_website_domain_to_test_host()
        self.user.company_ids = [(6, 0, [self.company_main.id])]
        self.user.company_id = self.company_main
        response = self._post_login("merchant@example.test", "merchant-password")
        self.assertEqual(response.status_code, 200)
        cids = self.opener.cookies.get("cids")
        self.assertNotEqual(cids, str(self.company_shop.id))

    def test_login_without_matching_website(self):
        """No website matches the host: login still works (historic 500)."""
        self.env["website"].search([]).write({"domain": "unrelated.example"})
        response = self._post_login("merchant@example.test", "merchant-password")
        self.assertEqual(response.status_code, 200)

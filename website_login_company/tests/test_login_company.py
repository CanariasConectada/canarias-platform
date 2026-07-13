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
        website_model = fake_request.env["website"].sudo()
        website_model._get_current_website_id.return_value = 42
        website_model.browse.return_value = fake_website
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
        # auto_microsite_generator (co-installed in the full image) auto-creates
        # a website per company; the extra websites collide on the unique domain
        # constraint these tests exercise, so disable it here.
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
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


@tagged("post_install", "-at_install")
class TestFindLoginWebsiteExactDomain(TransactionCase):
    """Host resolution must pick the EXACT website domain, never a substring.

    Regression guard for a login security incident: the previous hand-rolled
    ``ilike`` match on the client-controlled Host header was non-deterministic
    (``limit=1``) and matched any configured domain that merely *contained*
    the host. A host that is a substring of another site's domain could
    therefore force the wrong company at login. The fix delegates to the
    canonical core resolver, which matches the netloc exactly.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = WebsiteLoginCompanyHome()
        cls.company_root = cls.env["res.company"].create({"name": "Root Co"})
        cls.company_shop = cls.env["res.company"].create({"name": "Shop Co"})
        # Clear pre-existing domains so only our two websites can ever match.
        cls.env["website"].search([]).write({"domain": False})
        # ``shop.example.com`` fully contains ``example.com`` as a substring,
        # and both contain ``ample.com`` -- exactly what tricked the old
        # ``ilike`` matcher into false positives.
        cls.website_root = cls.env["website"].create(
            {
                "name": "Root Site",
                "domain": "example.com",
                "company_id": cls.company_root.id,
            }
        )
        cls.website_shop = cls.env["website"].create(
            {
                "name": "Shop Site",
                "domain": "shop.example.com",
                "company_id": cls.company_shop.id,
            }
        )

    def _find_for_host(self, host):
        """Run the real resolver against a mocked, client-controlled Host."""
        fake_request = MagicMock(spec=["httprequest", "env"])
        fake_request.httprequest.host = host
        # Use the real environment so the canonical resolver runs against the
        # websites created above (no ``request.website`` on ``/web/login``).
        fake_request.env = self.env
        with patch(
            "odoo.addons.website_login_company.controllers.home.request",
            fake_request,
        ):
            return self.controller._find_login_website()

    def test_exact_domain_wins_over_substring_sibling(self):
        """Host equal to the shorter domain must not match the longer one."""
        website = self._find_for_host("example.com")
        self.assertEqual(website, self.website_root)
        self.assertEqual(website.company_id, self.company_root)

    def test_longer_domain_matches_itself(self):
        """Host equal to the longer domain resolves to that exact website."""
        website = self._find_for_host("shop.example.com")
        self.assertEqual(website, self.website_shop)
        self.assertEqual(website.company_id, self.company_shop)

    def test_host_with_port_is_normalized(self):
        """The core strips the port: ``example.com:8069`` still matches root."""
        website = self._find_for_host("example.com:8069")
        self.assertEqual(website, self.website_root)

    def test_foreign_substring_host_does_not_match(self):
        """A host that is only a substring of real domains matches nothing.

        ``ample.com`` is contained in both ``example.com`` and
        ``shop.example.com`` but is not itself a configured domain: the old
        ``ilike`` returned a bogus match, the canonical resolver returns
        none, so the helper is a strict no-op.
        """
        website = self._find_for_host("ample.com")
        self.assertFalse(website)

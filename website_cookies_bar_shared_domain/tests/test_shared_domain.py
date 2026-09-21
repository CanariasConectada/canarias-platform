# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.http_routing.tests.common import MockRequest

from ..models.website import (
    CONSENT_COOKIE,
    SHARED_DOMAIN_PARAM,
    normalize_shared_domain,
    shared_domain_for_host,
)

DOMAIN = "canariasconectada.es"
SHOP_HOST = "tienda.canariasconectada.es"

# (raw value, expected normalized value). Shared with the JS suite, which runs
# the same table through `normalizeSharedDomain` and demands the same answers.
NORMALIZE_TABLE = [
    ("canariasconectada.es", DOMAIN),
    ("  CanariasConectada.ES  ", DOMAIN),
    (".canariasconectada.es", DOMAIN),
    ("canariasconectada.es.", DOMAIN),
    ("zona.canariasconectada.es", "zona.canariasconectada.es"),
    ("xn--caas-5qa.es", "xn--caas-5qa.es"),
    ("", ""),
    ("es", ""),
    ("localhost", ""),
    ("co.uk", ""),
    ("com.es", ""),
    ("gob.es", ""),
    ("github.io", ""),
    ("Blogspot.com", ""),
    (".vercel.app", ""),
    ("odoo.com", ""),
    ("mishop.github.io", "mishop.github.io"),
    ("127.0.0.1", ""),
    ("[::1]", ""),
    ("https://canariasconectada.es", ""),
    ("canariasconectada.es/shop", ""),
    ("canariasconectada.es:8069", ""),
    ("user@canariasconectada.es", ""),
    ("canarias conectada.es", ""),
    ("canariasconectada..es", ""),
    ("-canariasconectada.es", ""),
    ("cañas.es", ""),
    ("*.canariasconectada.es", ""),
    ("a" * 64 + ".es", ""),
    (".".join(["a" * 60] * 5), ""),
]

# (hostname, expected shared domain) with DOMAIN configured. Shared with the
# JS suite: these are all values `window.location.hostname` can take.
HOST_GUARD_TABLE = [
    (DOMAIN, DOMAIN),
    (SHOP_HOST, DOMAIN),
    ("a.b.canariasconectada.es", DOMAIN),
    ("Tienda.CanariasConectada.es", DOMAIN),
    ("tienda.canariasconectada.es.", DOMAIN),
    ("localhost", ""),
    ("127.0.0.1", ""),
    ("[::1]", ""),
    ("notcanariasconectada.es", ""),
    ("canariasconectada.es.evil.com", ""),
    ("mitienda.com", ""),
    ("es", ""),
    ("", ""),
]

# The server reads a `Host` header instead, which may carry a port.
HOST_HEADER_TABLE = [
    ("tienda.canariasconectada.es:443", DOMAIN),
    ("canariasconectada.es:8069", DOMAIN),
    ("localhost:8069", ""),
    ("[::1]:8069", ""),
    ("notcanariasconectada.es:443", ""),
]


@tagged("post_install", "-at_install")
class TestSharedDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.website = cls.env.ref("website.default_website")
        cls.website.cookies_bar = True
        cls.params.set_param(SHARED_DOMAIN_PARAM, DOMAIN)

    # -- validation -------------------------------------------------------

    def test_normalize(self):
        for raw, expected in NORMALIZE_TABLE:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_shared_domain(raw), expected)

    def test_normalize_tolerates_a_missing_value(self):
        self.assertEqual(normalize_shared_domain(None), "")
        self.assertEqual(normalize_shared_domain(False), "")

    def test_host_guard(self):
        for host, expected in HOST_GUARD_TABLE + HOST_HEADER_TABLE:
            with self.subTest(host=host):
                self.assertEqual(shared_domain_for_host(host, DOMAIN), expected)

    def test_host_guard_is_off_without_a_valid_domain(self):
        for configured in ("", False, "es", "co.uk", "https://canariasconectada.es"):
            with self.subTest(configured=configured):
                self.assertEqual(shared_domain_for_host(SHOP_HOST, configured), "")

    def test_parameter_constraint_refuses_an_invalid_domain(self):
        for value in (
            "es",
            "co.uk",
            "https://canariasconectada.es",
            "10.0.0.1",
            "herokuapp.com",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.params.set_param(SHARED_DOMAIN_PARAM, value)

    def test_parameter_constraint_accepts_valid_empty_and_foreign_keys(self):
        self.params.set_param(SHARED_DOMAIN_PARAM, ".Example.com")
        self.assertEqual(
            self.env["website"]._cookies_bar_shared_domain(), "example.com"
        )
        # Emptying the parameter is how the feature is switched off.
        self.params.set_param(SHARED_DOMAIN_PARAM, "")
        self.assertEqual(self.env["website"]._cookies_bar_shared_domain(), "")
        # The constraint is about one key only.
        self.params.set_param("website_cookies_bar_shared_domain.other", "es")

    def test_runtime_ignores_an_invalid_value_written_behind_the_orm(self):
        self.env.cr.execute(
            "UPDATE ir_config_parameter SET value = 'es' WHERE key = %s",
            [SHARED_DOMAIN_PARAM],
        )
        self.env.registry.clear_cache()
        self.assertEqual(self.env["website"]._cookies_bar_shared_domain(), "")
        self.assertEqual(
            self.env["website"]._cookies_bar_shared_domain_for_host(SHOP_HOST), ""
        )

    def test_model_helper_applies_the_guard(self):
        Website = self.env["website"]
        self.assertEqual(Website._cookies_bar_shared_domain_for_host(SHOP_HOST), DOMAIN)
        self.assertEqual(Website._cookies_bar_shared_domain_for_host("localhost"), "")

    # -- exposure to the frontend -------------------------------------------

    def test_session_info_carries_the_domain(self):
        with MockRequest(self.env, website=self.website):
            info = self.env["ir.http"].get_frontend_session_info()
        self.assertEqual(info.get("cookies_bar_shared_domain"), DOMAIN)

    def test_session_info_does_not_depend_on_the_host(self):
        # Pages are cached per website, not per host: the hostname guard is the
        # browser's job, so the server must answer the same on every host.
        with MockRequest(self.env, website=self.website) as request:
            request.httprequest.host = "localhost:8069"
            info = self.env["ir.http"].get_frontend_session_info()
        self.assertEqual(info.get("cookies_bar_shared_domain"), DOMAIN)

    def test_session_info_is_untouched_when_the_feature_is_off(self):
        self.params.set_param(SHARED_DOMAIN_PARAM, "")
        with MockRequest(self.env, website=self.website):
            info = self.env["ir.http"].get_frontend_session_info()
        self.assertNotIn("cookies_bar_shared_domain", info)

    def test_frontend_bundle_ships_the_scripts(self):
        paths = [
            asset[0]
            for asset in self.env["ir.asset"]._get_asset_paths(
                "web.assets_frontend", {}
            )
        ]
        module = "website_cookies_bar_shared_domain/static/src/js/"
        for script in ("shared_consent_cookie.js", "consent_cookie_patches.js"):
            self.assertTrue(
                any(path.endswith(module + script) for path in paths), script
            )

    # -- server side expiry of the legacy consent ---------------------------

    def _consent_set_cookies(self, host, consent):
        with MockRequest(
            self.env, website=self.website, cookies={CONSENT_COOKIE: consent}
        ) as request:
            request.httprequest.host = host
            allowed = self.env["ir.http"]._is_allowed_cookie("optional")
            headers = request.future_response.headers.getlist("Set-Cookie")
        return allowed, [h for h in headers if h.startswith(CONSENT_COOKIE + "=")]

    def test_legacy_consent_is_expired_on_the_shared_domain_too(self):
        allowed, set_cookies = self._consent_set_cookies(SHOP_HOST, "true")
        self.assertFalse(allowed)
        self.assertEqual(len(set_cookies), 2, set_cookies)
        shared = [h for h in set_cookies if "Domain=%s" % DOMAIN in h]
        self.assertEqual(len(shared), 1, set_cookies)
        self.assertIn("Max-Age=0", shared[0])
        self.assertIn("Path=/", shared[0])

    def test_legacy_consent_outside_the_domain_is_left_to_core(self):
        allowed, set_cookies = self._consent_set_cookies("localhost:8069", "true")
        self.assertFalse(allowed)
        self.assertEqual(len(set_cookies), 1, set_cookies)
        self.assertNotIn("Domain=", set_cookies[0])

    def test_current_consent_sets_no_cookie(self):
        refused = '{"required": true, "optional": false, "ts": 1700000000000}'
        accepted = '{"required": true, "optional": true, "ts": 1700000000000}'
        self.assertEqual(self._consent_set_cookies(SHOP_HOST, refused), (False, []))
        self.assertEqual(self._consent_set_cookies(SHOP_HOST, accepted), (True, []))

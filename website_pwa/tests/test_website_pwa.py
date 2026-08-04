# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.website_pwa.controllers.main import WebsitePWA

# 1x1 red PNG. Small enough to inline, real enough for image_process.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
    "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestWebsitePWA(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.write(
            {
                "pwa_enabled": True,
                "pwa_name": "Tienda de Prueba PWA",
                "pwa_short_name": "PruebaPWA",
                "pwa_theme_color": "#123456",
                "pwa_icon": base64.b64encode(TINY_PNG),
            }
        )

    def _disable(self):
        self.website.pwa_enabled = False

    def test_manifest_is_scoped_to_the_public_site(self):
        """The whole point: the app must open the shop, not the backend.

        Odoo's own manifest is scoped to /odoo, so installing it gave the
        visitor the ERP with Odoo's purple icon.
        """
        res = self.url_open("/website_pwa/manifest.webmanifest")
        self.assertEqual(res.status_code, 200)
        manifest = json.loads(res.text)
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["name"], "Tienda de Prueba PWA")
        self.assertEqual(manifest["short_name"], "PruebaPWA")
        self.assertEqual(manifest["theme_color"], "#123456")

    def test_manifest_declares_both_required_icon_sizes(self):
        """Chrome refuses to offer the install prompt without a 192px icon,
        and uses the 512px one for the splash screen."""
        res = self.url_open("/website_pwa/manifest.webmanifest")
        sizes = {icon["sizes"] for icon in json.loads(res.text)["icons"]}
        self.assertEqual(sizes, {"192x192", "512x512"})

    def test_icon_is_a_png_of_the_requested_size(self):
        """Merchant logos are a mix of JPEG, transparent PNG and odd aspect
        ratios; the manifest icon has to be a real PNG of the declared size
        or the browser rejects the app."""
        res = self.url_open("/website_pwa/icon/192.png")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "image/png")
        self.assertTrue(res.content.startswith(b"\x89PNG"))

    def test_unknown_icon_size_is_not_found(self):
        res = self.url_open("/website_pwa/icon/64.png")
        self.assertEqual(res.status_code, 404)

    def test_service_worker_is_served_from_the_root(self):
        """A service worker can only control pages under its own path, so it
        must live at / for the whole microsite to be covered."""
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.status_code, 200)
        self.assertIn("javascript", res.headers["Content-Type"])
        self.assertEqual(res.headers.get("Service-Worker-Allowed"), "/")

    def test_service_worker_serves_the_hook_verbatim(self):
        """The route must serve exactly what ``_pwa_service_worker_content``
        returns, byte for byte.

        Two things break if it does not: an override added by another module
        never reaches the browser, and the worker's bytes drift, which forces
        every phone that already installed the app to update for nothing.
        """
        expected = WebsitePWA()._pwa_service_worker_content(self.website)
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, expected.encode())

    def test_service_worker_keeps_the_root_scope_header(self):
        """Without ``Service-Worker-Allowed: /`` some proxies narrow the scope
        to the directory the file is served from, and the worker then controls
        nothing."""
        res = self.url_open("/service-worker.js")
        self.assertEqual(res.headers.get("Service-Worker-Allowed"), "/")

    def test_extension_modules_can_append_to_the_worker(self):
        """An override of ``_pwa_service_worker_content`` must reach the
        response; that hook is how later modules add their own handlers."""
        marker = "\n// appended by a downstream module\n"
        original = WebsitePWA._pwa_service_worker_content

        def _extended(controller, website):
            return original(controller, website) + marker

        before = self.url_open("/service-worker.js").content
        with patch.object(WebsitePWA, "_pwa_service_worker_content", _extended):
            after = self.url_open("/service-worker.js").content
        self.assertNotIn(marker.encode(), before)
        self.assertEqual(after, before + marker.encode())

    def test_layout_links_the_manifest(self):
        res = self.url_open("/")
        self.assertIn('rel="manifest"', res.text)
        self.assertIn("/website_pwa/manifest.webmanifest", res.text)
        # iOS ignores the manifest, so the apple-* tags carry it there.
        self.assertIn("apple-mobile-web-app-capable", res.text)

    def test_disabled_website_serves_no_app_at_all(self):
        """Switching the app off for one merchant must really remove it: the
        browser has to stop finding a manifest, or it keeps offering to
        install a site that no longer wants to be installed."""
        self._disable()
        self.assertEqual(
            self.url_open("/website_pwa/manifest.webmanifest").status_code, 404
        )
        self.assertEqual(self.url_open("/service-worker.js").status_code, 404)
        self.assertEqual(self.url_open("/website_pwa/icon/192.png").status_code, 404)
        self.assertNotIn('rel="manifest"', self.url_open("/").text)

    def test_defaults_when_the_merchant_configured_nothing(self):
        """A merchant who never opens these settings must still get a usable
        app, not a blank name and a blank icon."""
        self.website.write(
            {"pwa_name": False, "pwa_short_name": False, "pwa_icon": False}
        )
        manifest = json.loads(self.url_open("/website_pwa/manifest.webmanifest").text)
        self.assertEqual(manifest["name"], self.website.name)
        self.assertTrue(manifest["short_name"])
        self.assertLessEqual(len(manifest["short_name"]), 12)

    def test_offline_page_is_available(self):
        """The service worker pre-caches this page; if it 404s the fallback
        silently does nothing when the visitor loses signal."""
        res = self.url_open("/website_pwa/offline")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Sin conexión", res.text)

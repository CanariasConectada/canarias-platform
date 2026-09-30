# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from ..tools import map_url as map_url_tools

RESOLVER = "odoo.addons.partner_microsite_manager.tools.map_url.resolve_short_map_url"
REQUESTS_GET = "odoo.addons.partner_microsite_manager.tools.map_url.requests.get"
TOOLS_LOGGER = "odoo.addons.partner_microsite_manager.tools.map_url"

# Company 7 in production, verbatim.
PLACE_URL = (
    "https://www.google.com/maps/place/P.%C2%BA+Tom%C3%A1s+Morales,+72,+35003"
    "+Las+Palmas+de+Gran+Canaria,+Las+Palmas/@28.1130743,-15.4264542,17z/"
    "data=!3m1!4b1!4m6!3m5!1s0xc40959c23967ad5:0xec71c17796eadc2!8m2"
    "!3d28.1130743!4d-15.4238793!16s%2Fg%2F11bw4489zm?authuser=0&entry=ttu"
)
SHORT_URL = "https://maps.app.goo.gl/PUYHynTn95W7LiD2A"
RESOLVED_URL = (
    "https://www.google.com/maps/place/Never%C3%AD+Obrador+Artesanal/"
    "@28.136562,-15.4360489,17z/data=!3m2!4b1!4m6!3m5!1s0xc40950859d21325:"
    "0x37081306e69987cf!8m2!3d28.1365573!4d-15.4334686!16s?entry=tts"
)
EMBED_URL = (
    "https://maps.google.com/maps?q=Calle+Daoiz+34+Las+Palmas+35010"
    "&t=&z=13&ie=UTF8&iwloc=&output=embed"
)


def _embed(query, zoom=17):
    return f"https://maps.google.com/maps?q={query}&z={zoom}&ie=UTF8&output=embed"


@tagged("post_install", "-at_install")
class TestMapUrlConverter(TransactionCase):
    """Any Google Maps link a merchant pastes must end up in a frameable URL.

    Reported 2026-09-30: share links (``/maps/place``, ``maps.app.goo.gl``)
    answer with ``X-Frame-Options: SAMEORIGIN`` and Firefox showed its
    "can't open this page" fox instead of the map.
    """

    def _convert(self, url, resolver=None):
        return map_url_tools.to_embeddable_map_url(url, resolver=resolver)

    def test_place_url_with_at_coordinates(self):
        url = "https://www.google.es/maps/place/Panaderia/@28.1,-15.4,15z"
        self.assertEqual(self._convert(url), _embed("28.1,-15.4", 15))

    def test_precise_pin_coordinates_are_preferred(self):
        # @ is the viewport centre (-15.4264542); !4d is the pin (-15.4238793).
        self.assertEqual(self._convert(PLACE_URL), _embed("28.1130743,-15.4238793", 17))

    def test_place_name_without_coordinates(self):
        url = "https://www.google.com/maps/place/Calle+Mayor+1,+Telde"
        self.assertEqual(self._convert(url), _embed("Calle+Mayor+1,+Telde"))

    def test_search_query_and_dir_links(self):
        self.assertEqual(
            self._convert("https://www.google.com/maps/search/panaderia+telde/"),
            _embed("panaderia+telde"),
        )
        self.assertEqual(
            self._convert("https://www.google.com/maps?q=Telde&z=12"),
            _embed("Telde", 12),
        )
        self.assertEqual(
            self._convert("https://www.google.com/maps/dir/Casa/Calle+B,+Telde/"),
            _embed("Calle+B,+Telde"),
        )

    def test_short_link_is_resolved_then_converted(self):
        resolver = MagicMock(return_value=RESOLVED_URL)
        self.assertEqual(
            self._convert(SHORT_URL, resolver), _embed("28.1365573,-15.4334686")
        )
        resolver.assert_called_once_with(SHORT_URL)

    def test_short_link_resolution_failure_keeps_the_original(self):
        failing = MagicMock(return_value=None)
        self.assertEqual(self._convert(SHORT_URL, failing), SHORT_URL)
        self.assertEqual(self._convert(SHORT_URL), SHORT_URL)

    def test_embed_url_is_unchanged(self):
        self.assertEqual(self._convert(EMBED_URL), EMBED_URL)
        pb = "https://www.google.com/maps/embed?pb=!1m18!1m12"
        self.assertEqual(self._convert(pb), pb)

    def test_html_escaped_embed_url_is_decoded(self):
        """64 prod companies carry ``&amp;`` copied from an iframe source."""
        escaped = EMBED_URL.replace("&", "&amp;")
        self.assertEqual(self._convert(escaped), EMBED_URL)

    def test_non_google_and_foreign_schemes_are_untouched(self):
        for url in ("https://example.com/embed", "javascript:alert(1)"):
            self.assertEqual(self._convert(url), url)

    def test_resolver_follows_google_hops_only(self):
        def response(location):
            return MagicMock(status_code=302, headers={"Location": location})

        with patch(REQUESTS_GET, return_value=response(RESOLVED_URL)) as get:
            self.assertEqual(
                map_url_tools.resolve_short_map_url(SHORT_URL), RESOLVED_URL
            )
            self.assertLessEqual(get.call_args.kwargs["timeout"], 6)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        with (
            self.assertLogs(TOOLS_LOGGER, "WARNING"),
            patch(REQUESTS_GET, return_value=response("https://evil.example/x")),
        ):
            self.assertIsNone(map_url_tools.resolve_short_map_url(SHORT_URL))
        with patch(REQUESTS_GET, return_value=response(SHORT_URL)) as get:
            self.assertIsNone(map_url_tools.resolve_short_map_url(SHORT_URL))
            self.assertEqual(get.call_count, 5)

    def test_resolver_budget_covers_all_hops(self):
        """6 s for the whole chain, not per hop: a slow first hop leaves the
        next one only the remainder, and none once the budget is spent."""
        clock = iter([100.0, 100.0, 104.5, 107.0])
        response = MagicMock(status_code=302, headers={"Location": SHORT_URL})
        with (
            patch(
                "odoo.addons.partner_microsite_manager.tools.map_url.time.monotonic",
                side_effect=lambda: next(clock),
            ),
            patch(REQUESTS_GET, return_value=response) as get,
            self.assertLogs(TOOLS_LOGGER, "WARNING"),
        ):
            self.assertIsNone(map_url_tools.resolve_short_map_url(SHORT_URL))
        timeouts = [call.kwargs["timeout"] for call in get.call_args_list]
        self.assertEqual(timeouts, [6.0, 1.5])
        with (
            self.assertLogs(TOOLS_LOGGER, "WARNING"),
            patch(REQUESTS_GET, side_effect=requests.Timeout("slow")),
        ):
            self.assertIsNone(map_url_tools.resolve_short_map_url(SHORT_URL))


@tagged("post_install", "-at_install")
class TestCompanyMapUrl(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.company = cls.env["res.company"].create(
            {
                "name": "Map Test Company",
                "street": "Calle Mayor 1",
                "city": "Telde",
                "zip": "35200",
            }
        )
        cls.address_embed = cls.company.partner_id._canarias_map_embed_url()

    def test_saving_a_share_link_stores_the_embed_and_keeps_the_original(self):
        with patch(RESOLVER, return_value=RESOLVED_URL):
            self.company.microsite_map_url = SHORT_URL
        self.assertEqual(
            self.company.microsite_map_url, _embed("28.1365573,-15.4334686")
        )
        self.assertEqual(self.company.microsite_map_share_url, SHORT_URL)
        self.assertEqual(
            self.company._get_microsite_map_url(), self.company.microsite_map_url
        )
        self.assertEqual(self.company._get_microsite_map_link_url(), SHORT_URL)

    def test_new_company_is_normalized_on_create(self):
        company = self.env["res.company"].create(
            {"name": "Map Create Co", "microsite_map_url": PLACE_URL}
        )
        self.assertEqual(company.microsite_map_url, _embed("28.1130743,-15.4238793"))
        self.assertEqual(company.microsite_map_share_url, PLACE_URL)

    def test_resolution_failure_falls_back_to_the_address_map(self):
        with patch(RESOLVER, return_value=None):
            self.company.microsite_map_url = SHORT_URL
        self.assertEqual(self.company.microsite_map_url, SHORT_URL)
        with self.assertLogs(
            "odoo.addons.partner_microsite_manager.models.res_company", "DEBUG"
        ):
            self.assertEqual(self.company._get_microsite_map_url(), self.address_embed)

    def test_resaving_a_failed_short_link_retries(self):
        with patch(RESOLVER, return_value=None):
            self.company.microsite_map_url = SHORT_URL
        self.assertEqual(self.company.microsite_map_url, SHORT_URL)
        with patch(RESOLVER, return_value=RESOLVED_URL) as resolver:
            self.company.write({"microsite_map_url": SHORT_URL})
        resolver.assert_called_once()
        self.assertEqual(
            self.company.microsite_map_url, _embed("28.1365573,-15.4334686")
        )
        self.assertEqual(self.company.microsite_map_share_url, SHORT_URL)

    def test_daily_cron_heals_a_failed_short_link(self):
        with patch(RESOLVER, return_value=None):
            self.company.microsite_map_url = SHORT_URL
        cron = self.env.ref("partner_microsite_manager.ir_cron_retry_map_short_links")
        self.assertIn("_cron_retry_map_short_links", cron.code)
        with patch(RESOLVER, return_value=RESOLVED_URL):
            healed = self.env["res.company"]._cron_retry_map_short_links()
        self.assertIn(self.company, healed)
        self.assertLessEqual(len(healed), 20)
        self.assertEqual(
            self.company.microsite_map_url, _embed("28.1365573,-15.4334686")
        )
        self.assertEqual(self.company.microsite_map_share_url, SHORT_URL)

    def test_embed_url_is_stored_unchanged(self):
        self.company.microsite_map_url = EMBED_URL
        self.assertEqual(self.company.microsite_map_url, EMBED_URL)
        self.assertFalse(self.company.microsite_map_share_url)
        self.assertEqual(self.company._get_microsite_map_url(), EMBED_URL)
        self.assertIn("query=Calle+Daoiz", self.company._get_microsite_map_link_url())

    def test_non_google_https_is_unchanged(self):
        url = "https://www.openstreetmap.org/export/embed.html"
        self.company.microsite_map_url = url
        self.assertEqual(self.company._get_microsite_map_url(), url)
        self.assertFalse(self.company._get_microsite_map_link_url())

    def test_javascript_is_still_rejected(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = "javascript://www.google.com/maps%0a"
        with self.assertRaises(ValidationError):
            self.company.microsite_map_share_url = "javascript://www.google.com/maps"
        with self.assertRaises(ValidationError):
            self.company.write(
                {
                    "microsite_map_url": EMBED_URL,
                    "microsite_map_share_url": "javascript:alert(1)",
                }
            )

    def test_resaving_the_same_link_does_not_resolve_again(self):
        with patch(RESOLVER, return_value=RESOLVED_URL):
            self.company.microsite_map_url = SHORT_URL
        stored = self.company.microsite_map_url
        with patch(RESOLVER) as resolver:
            self.company.write({"microsite_map_url": stored})
            self.company.write({"microsite_map_url": SHORT_URL})
        resolver.assert_not_called()
        self.assertEqual(self.company.microsite_map_url, stored)
        self.assertEqual(self.company.microsite_map_share_url, SHORT_URL)

    def test_clearing_the_map_clears_the_original(self):
        self.company.microsite_map_url = PLACE_URL
        self.company.microsite_map_url = False
        self.assertFalse(self.company.microsite_map_share_url)
        self.assertEqual(self.company._get_microsite_map_url(), self.address_embed)

    def test_render_shows_the_embed_and_the_google_maps_link(self):
        website = self.env["website"].create(
            {"name": "Map Test Website", "company_id": self.company.id}
        )
        self.company.invalidate_recordset(["website_id"])
        self.company.microsite_map_url = PLACE_URL
        html = str(
            self.env["ir.qweb"]._render(
                "partner_microsite_manager.microsite_homepage_content",
                {"website": website},
            )
        )
        self.assertIn("28.1130743,-15.4238793", html)
        self.assertIn("output=embed", html)
        self.assertIn("View on Google Maps", html)
        self.assertNotIn('src="https://www.google.com/maps/place', html)

    def test_wizard_save_normalizes(self):
        shop = self.env["res.company"].create({"name": "Map Wizard Shop"})
        shop.website_id = self.env["website"].create(
            {"name": "Map Wizard Shop", "company_id": shop.id}
        )
        merchant = new_test_user(
            self.env,
            login="map_url_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=shop.id,
            company_ids=[(6, 0, shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        editor = (
            self.env["microsite.content.editor"]
            .with_user(merchant)
            .create({"microsite_map_url": SHORT_URL})
        )
        with patch(RESOLVER, return_value=RESOLVED_URL):
            editor.action_save()
        self.assertEqual(shop.microsite_map_url, _embed("28.1365573,-15.4334686"))
        self.assertEqual(shop.microsite_map_share_url, SHORT_URL)

    def test_migration_is_idempotent(self):
        # Stored as the pre-19.0.2.12.0 code left them: raw, unconverted.
        escaped = EMBED_URL.replace("&", "&amp;")
        other = self.env["res.company"].create({"name": "Map Legacy Co"})
        self.company.write(
            {"microsite_map_url": PLACE_URL, "microsite_map_share_url": False}
        )
        other.write({"microsite_map_url": escaped, "microsite_map_share_url": False})
        path = get_module_path("partner_microsite_manager")
        spec = importlib.util.spec_from_file_location(
            "pmm_map_migration", f"{path}/migrations/19.0.2.12.0/post-migration.py"
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        migration.migrate(self.env.cr, "19.0.2.11.1")
        self.env.invalidate_all()
        self.assertEqual(
            self.company.microsite_map_url, _embed("28.1130743,-15.4238793")
        )
        self.assertEqual(self.company.microsite_map_share_url, PLACE_URL)
        self.assertEqual(other.microsite_map_url, EMBED_URL)
        self.assertFalse(other.microsite_map_share_url)

        companies = self.company | other
        self.assertFalse(companies._normalize_existing_map_urls())
        migration.migrate(self.env.cr, "19.0.2.11.1")
        self.assertEqual(
            self.company.microsite_map_url, _embed("28.1130743,-15.4238793")
        )
        self.assertEqual(self.company.microsite_map_share_url, PLACE_URL)

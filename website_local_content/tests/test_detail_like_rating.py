# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
from unittest.mock import patch

import psycopg2

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger, sql

from odoo.addons.website_local_content.models.local_content_item import (
    RATING_PARTNER_UNIQUE_INDEX,
)

from .common import create_taxonomy, make_test_image

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


@tagged("post_install", "-at_install")
class TestDetailLikeRating(HttpCase):
    """Interactive like button and rating form of the public detail page."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content_type, cls.category, _sub = create_taxonomy(cls.env, "LR")
        cls.item = cls.env["website.local.content.item"].create(
            {
                "name": "WLC Rated Viewpoint",
                "type_id": cls.content_type.id,
                "category_id": cls.category.id,
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        cls.index_url = f"/explora/{cls.content_type.url_slug}"
        cls.detail_url = cls.item.website_url
        cls.rate_url = f"{cls.index_url}/rate/{cls.item.id}"
        cls.like_url = f"{cls.index_url}/like/{cls.item.id}"
        cls.rater = new_test_user(
            cls.env, login="wlc_rater_a", groups="base.group_portal"
        )
        cls.other_rater = new_test_user(
            cls.env, login="wlc_rater_b", groups="base.group_portal"
        )

    def setUp(self):
        super().setUp()
        # Same pin as the controller suite: avoid the language 303 hop.
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code

    # --- Helpers -----------------------------------------------------------
    def _get_page(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        return response.text

    def _csrf(self, url=None):
        return CSRF_PATTERN.search(self._get_page(url or self.detail_url)).group(1)

    def _ratings(self, partner=None):
        domain = [
            ("res_model", "=", self.item._name),
            ("res_id", "=", self.item.id),
        ]
        if partner:
            domain.append(("partner_id", "=", partner.id))
        self.env.invalidate_all()
        return self.env["rating.rating"].sudo().search(domain)

    def _rate(self, **data):
        return self.url_open(self.rate_url, data=dict(data, csrf_token=self._csrf()))

    # --- Likes ---------------------------------------------------------------
    def test_detail_like_button_increments_once_per_session(self):
        html = self._get_page(self.detail_url)
        self.assertIn("wlc-like-btn-inline", html)
        self.assertIn(f'data-like-url="{self.like_url}"', html)
        self.assertIn(f'data-like-counter-for="{self.item.id}"', html)
        self.assertIn('data-liked="0"', html)
        csrf = CSRF_PATTERN.search(html).group(1)
        response = self.url_open(
            self.like_url, data={"csrf_token": csrf, "redirect": self.detail_url}
        )
        self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        self.assertEqual(self.item.like_count, 1)
        # Same visitor again: idempotent, and the page shows the liked state.
        self.url_open(self.like_url, data={"csrf_token": csrf})
        self.env.invalidate_all()
        self.assertEqual(self.item.like_count, 1)
        html = self._get_page(self.detail_url)
        self.assertIn('data-liked="1"', html)
        self.assertIn('aria-pressed="true" disabled="disabled"', html)

    def test_card_like_still_works(self):
        html = self._get_page(self.index_url)
        self.assertIn(f'data-like-url="{self.like_url}"', html)
        self.assertIn(f'data-like-counter-for="{self.item.id}"', html)
        csrf = CSRF_PATTERN.search(html).group(1)
        response = self.url_open(
            self.like_url, data={"csrf_token": csrf, "redirect": self.index_url}
        )
        self.assertEqual(response.status_code, 200)
        self.env.invalidate_all()
        self.assertEqual(self.item.like_count, 1)

    # --- Ratings -------------------------------------------------------------
    def test_anonymous_sees_login_link_and_cannot_rate(self):
        html = self._get_page(self.detail_url)
        self.assertNotIn("wlc-star-picker", html)
        self.assertIn('href="/web/login?redirect=', html)
        response = self.url_open(
            self.rate_url,
            data={"csrf_token": CSRF_PATTERN.search(html).group(1), "rating": "5"},
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers["Location"])
        self.assertFalse(self._ratings())

    def test_rating_create_update_delete(self):
        self.authenticate("wlc_rater_a", "wlc_rater_a")
        html = self._get_page(self.detail_url)
        self.assertIn("wlc-star-picker", html)
        self.assertNotIn("wlc-my-rating", html)

        response = self._rate(rating="4", feedback="  Great views  ")
        self.assertEqual(response.status_code, 200)
        rating = self._ratings()
        self.assertEqual(len(rating), 1)
        self.assertEqual(rating.partner_id, self.rater.partner_id)
        self.assertFalse(rating.rated_partner_id)
        self.assertTrue(rating.consumed)
        self.assertEqual(rating.rating, 4)
        self.assertEqual(rating.feedback, "Great views")
        self.assertEqual(self.item.rating_count, 1)
        self.assertAlmostEqual(self.item.rating_avg, 4.0, places=2)
        html = self._get_page(self.detail_url)
        self.assertIn("wlc-my-rating", html)
        self.assertIn('id="wlc_star_4" value="4" checked="checked"', html)
        self.assertIn("Great views", html)

        # Update: still one row per partner, comment capped at 1000 chars.
        self._rate(rating="2", feedback="x" * 1500)
        rating = self._ratings()
        self.assertEqual(len(rating), 1)
        self.assertEqual(rating.rating, 2)
        self.assertEqual(len(rating.feedback), 1000)
        self.assertAlmostEqual(self.item.rating_avg, 2.0, places=2)

        response = self.url_open(
            f"{self.rate_url}/delete", data={"csrf_token": self._csrf()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._ratings())
        self.assertEqual(self.item.rating_count, 0)

    def test_invalid_rating_value_is_ignored(self):
        self.authenticate("wlc_rater_a", "wlc_rater_a")
        for value in ("0", "6", "abc", ""):
            response = self._rate(rating=value)
            self.assertIn("rating_error=1", response.url)
            self.assertIn("wlc-rating-error", response.text)
        self.assertFalse(self._ratings())
        self.assertNotIn("wlc-rating-error", self._get_page(self.detail_url))

    def test_user_only_acts_on_own_rating(self):
        self.authenticate("wlc_rater_a", "wlc_rater_a")
        self._rate(rating="5", feedback="Mine")
        own = self._ratings(self.rater.partner_id)
        self.assertEqual(len(own), 1)

        self.authenticate("wlc_rater_b", "wlc_rater_b")
        # Deleting with nothing of their own leaves A's rating untouched.
        self.url_open(f"{self.rate_url}/delete", data={"csrf_token": self._csrf()})
        self.assertEqual(self._ratings(self.rater.partner_id), own)
        # Rating creates B's own row; A's row keeps its value.
        self._rate(rating="1")
        self.assertEqual(len(self._ratings()), 2)
        own = self._ratings(self.rater.partner_id)
        self.assertEqual((own.rating, own.feedback), (5, "Mine"))
        self.assertEqual(self._ratings(self.other_rater.partner_id).rating, 1)
        # B's page never shows A's rating as theirs.
        self.url_open(f"{self.rate_url}/delete", data={"csrf_token": self._csrf()})
        self.assertNotIn("wlc-my-rating", self._get_page(self.detail_url))
        self.assertEqual(len(self._ratings(self.rater.partner_id)), 1)

    def test_unpublished_item_refused(self):
        self.authenticate("wlc_rater_a", "wlc_rater_a")
        csrf = self._csrf()
        self.item.is_published = False
        response = self.url_open(
            self.rate_url, data={"csrf_token": csrf, "rating": "5"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self._ratings())

    # --- Database guarantee ----------------------------------------------------
    def test_unique_index_exists(self):
        self.assertTrue(sql.index_exists(self.env.cr, RATING_PARTNER_UNIQUE_INDEX))

    def test_duplicate_create_leaves_one_row(self):
        """A second raw create for the same partner hits the index; the
        controller helper falls back to updating the existing row."""
        vals = {
            "res_model_id": self.env["ir.model"]._get_id(self.item._name),
            "res_id": self.item.id,
            "partner_id": self.rater.partner_id.id,
            "rating": 3,
            "consumed": True,
        }
        Rating = self.env["rating.rating"].sudo()
        Rating.create(vals)
        with self.assertRaises(psycopg2.IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                Rating.create(dict(vals, rating=5))
        self.assertEqual(len(self._ratings(self.rater.partner_id)), 1)
        # Ratings without partner stay unconstrained.
        Rating.create(dict(vals, partner_id=False))
        Rating.create(dict(vals, partner_id=False))
        self.assertEqual(len(self._ratings()), 3)

    def test_controller_create_race_falls_back_to_update(self):
        """Simulate the race: another request already inserted the row, but
        this one looked before that. The insert hits the unique index and
        the request still ends with one updated row."""
        from odoo.addons.website_local_content.controllers.main import (
            WebsiteLocalContent,
        )

        self.authenticate("wlc_rater_a", "wlc_rater_a")
        # Token first: rendering the page also looks up the own rating.
        csrf = self._csrf()
        self.env["rating.rating"].sudo().create(
            {
                "res_model_id": self.env["ir.model"]._get_id(self.item._name),
                "res_id": self.item.id,
                "partner_id": self.rater.partner_id.id,
                "rating": 1,
                "consumed": True,
            }
        )
        self.env.flush_all()
        original = WebsiteLocalContent._get_own_rating
        calls = []

        def stale_first_lookup(controller, item):
            calls.append(1)
            if len(calls) == 1:
                return item.env["rating.rating"].browse()
            return original(controller, item)

        with (
            patch.object(WebsiteLocalContent, "_get_own_rating", stale_first_lookup),
            mute_logger("odoo.sql_db"),
        ):
            response = self.url_open(
                self.rate_url, data={"csrf_token": csrf, "rating": "4"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(calls), 2)
        rating = self._ratings(self.rater.partner_id)
        self.assertEqual(len(rating), 1)
        self.assertEqual(rating.rating, 4)

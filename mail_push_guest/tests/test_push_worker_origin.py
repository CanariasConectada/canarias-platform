# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from .common import BROWSER_KEYS, FCM_ENDPOINT, MOZILLA_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushWorkerOrigin(MailPushGuestMixin, HttpCase):
    """Devices remember which service worker owns them.

    An origin running the installed app has two workers, the website's and
    core's backend one, and a persona subscribed on both gets every message
    twice. Internal users belong on the backend worker, so registering one of
    theirs there removes their website-worker leftovers.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.user_author.password = "mpg_author_pwd"
        cls.other_internal = cls.env["res.users"].create(
            {
                "name": "Other Internal",
                "login": "mpg_other",
                "email": "mpg_other@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _device(self, endpoint):
        return self.Device.sudo().search([("endpoint", "=", endpoint)])

    def _tagged_device(self, endpoint, partner, worker):
        device = self._create_device(endpoint, partner=partner)
        device.cc_worker = worker
        return device

    def _subscribe(self, endpoint, **params):
        payload = {
            "endpoint": endpoint,
            "keys": dict(BROWSER_KEYS),
            "vapid_public_key": self.vapid_public_key,
        }
        payload.update(params)
        return self.make_jsonrpc_request("/mail/push/subscribe", payload)

    # ------------------------------------------------------------------
    # Tagging
    # ------------------------------------------------------------------

    def test_route_records_the_backend_worker(self):
        self.authenticate("mpg_author", "mpg_author_pwd")
        self._subscribe(FCM_ENDPOINT % "tag-backend", worker="backend")
        self.assertEqual(
            self._device(FCM_ENDPOINT % "tag-backend").cc_worker, "backend"
        )

    def test_route_defaults_to_the_website_worker(self):
        """What the route served before the value existed, and what the
        website worker's own renewal handler still sends."""
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._subscribe(FCM_ENDPOINT % "tag-default")
        self._subscribe(FCM_ENDPOINT % "tag-garbage", worker="<script>")
        self.assertEqual(
            self._device(FCM_ENDPOINT % "tag-default").cc_worker, "website"
        )
        self.assertEqual(
            self._device(FCM_ENDPOINT % "tag-garbage").cc_worker, "website"
        )

    def test_core_registration_is_the_backend_worker(self):
        endpoint = FCM_ENDPOINT % "tag-core"
        self.Device.with_user(self.user_author).register_devices(
            endpoint=endpoint,
            keys=BROWSER_KEYS,
            vapid_public_key=self.vapid_public_key,
            expirationTime=None,
        )
        self.assertEqual(self._device(endpoint).cc_worker, "backend")

    # ------------------------------------------------------------------
    # Safety net
    # ------------------------------------------------------------------

    def test_backend_registration_drops_the_internal_user_s_website_devices(self):
        leftover = self._tagged_device(
            MOZILLA_ENDPOINT % "leftover", self.partner_author, "website"
        )
        legacy = self._create_device(
            MOZILLA_ENDPOINT % "legacy", partner=self.partner_author
        )
        stranger = self._tagged_device(
            MOZILLA_ENDPOINT % "stranger", self.other_internal.partner_id, "website"
        )

        self.authenticate("mpg_author", "mpg_author_pwd")
        self._subscribe(FCM_ENDPOINT % "net-backend", worker="backend")

        self.assertFalse(leftover.exists(), "the duplicate-maker must go")
        self.assertTrue(legacy.exists(), "rows with no recorded worker are left alone")
        self.assertTrue(stranger.exists(), "only the registering user's rows")
        self.assertEqual(
            self._device(FCM_ENDPOINT % "net-backend").cc_worker, "backend"
        )

    def test_core_registration_drops_them_too(self):
        leftover = self._tagged_device(
            MOZILLA_ENDPOINT % "leftover-core", self.partner_author, "website"
        )
        self.Device.with_user(self.user_author).register_devices(
            endpoint=FCM_ENDPOINT % "net-core",
            keys=BROWSER_KEYS,
            vapid_public_key=self.vapid_public_key,
            expirationTime=None,
        )
        self.assertFalse(leftover.exists())

    def test_website_registration_drops_nothing(self):
        kept = self._tagged_device(
            MOZILLA_ENDPOINT % "kept-website", self.partner_author, "website"
        )
        self.authenticate("mpg_author", "mpg_author_pwd")
        self._subscribe(FCM_ENDPOINT % "net-website", worker="website")
        self.assertTrue(kept.exists())

    def test_portal_users_keep_their_website_devices(self):
        """The website worker IS where portal users belong."""
        kept = self._tagged_device(
            MOZILLA_ENDPOINT % "portal-website", self.portal_user.partner_id, "website"
        )
        self.authenticate("mpg_portal", "mpg_portal_pwd")
        self._subscribe(FCM_ENDPOINT % "portal-backend", worker="backend")
        self.assertTrue(kept.exists())

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityGuestModel(CommunityMixin, TransactionCase):
    """The lifecycle of an internal community guest: birth, worth, purge."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()

    def _backdate(self, user, days=30):
        """Push the account's creation past the staleness window.

        Raw SQL because ``create_date`` is a magic column the ORM refuses to
        write; same technique as the ``website_login_branding`` GC tests.
        """
        old = fields.Datetime.now() - timedelta(days=days)
        self.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id = %s", (old, user.id)
        )
        user.invalidate_recordset(["create_date"])

    def test_create_community_guest_shape(self):
        """An INTERNAL guest with every guard of the portal blueprint.

        The differences from ``_create_platform_guest`` are exactly the ones
        the product decided (internal + community instead of portal) and no
        other: non-routable login domain, email notifications, platform
        company only, the flag that makes it findable and disposable. The
        Discuss landing action and the zone seat come with the shape.
        """
        guest = self.env["res.users"]._create_community_guest(zone="guanarteme")
        self.assertTrue(guest.is_community_guest)
        self.assertTrue(guest._is_internal(), "community guests are internal")
        self.assertFalse(guest.share)
        self.assertIn(self.community_group, guest.all_group_ids)
        self.assertTrue(guest.login.startswith("cguest_"))
        self.assertTrue(guest.login.endswith("@guests.canariasconectada.es"))
        self.assertEqual(guest.notification_type, "email")
        self.assertEqual(
            guest.company_ids,
            self.main_company,
            "the arrival website's company must never land on the user",
        )
        self.assertEqual(guest.chat_zone, "guanarteme")
        # By id: `action_id`'s comodel is the base `ir.actions.actions`, the
        # ref is the concrete `ir.actions.client` -- same row, two models.
        self.assertEqual(guest.action_id.id, self.discuss_action.id)
        self.assertEqual(
            self._zone_channels_of(guest),
            self.channel_general | self.channel_guanarteme,
        )

    def test_guest_zone_is_normalised_from_legacy_spellings(self):
        """A legacy zone spelling from an old website row still seats right.

        The migrated database holds ``lomo_los_frailes`` and friends, and the
        website's company is data, not code -- the door must speak both.
        """
        guest = self.env["res.users"]._create_community_guest(zone="lomo_los_frailes")
        self.assertEqual(guest.chat_zone, "lomolosfrailes")
        self.assertEqual(
            self._zone_channels_of(guest),
            self.channel_general | self.channel_lomo,
        )

    def test_gc_removes_idle_silent_guest(self):
        """Idle past the window and never spoke: the account evaporates."""
        guest = self.env["res.users"]._create_community_guest()
        self._backdate(guest)
        removed = self.env["res.users"]._gc_community_guests()
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(guest.exists(), "the idle silent guest must be purged")

    def test_gc_keeps_a_guest_who_posted(self):
        """A guest with a message in a conversation is not disposable.

        Deleting the author of messages other residents can still read would
        amputate the conversation; "posted a comment" is this module's
        definition of "worth keeping", the mirror of the branding module's
        "placed an order".
        """
        guest = self.env["res.users"]._create_community_guest()
        self.channel_general.sudo().message_post(
            body="still here",
            author_id=guest.partner_id.id,
            message_type="comment",
        )
        self._backdate(guest)
        self.env["res.users"]._gc_community_guests()
        self.assertTrue(guest.exists(), "a guest who posted must survive the GC")

    def test_gc_never_touches_a_young_guest(self):
        """An account younger than the window is kept even with no logins.

        A guest created moments ago has no login log yet and would look
        "idle" to a naive query; age is the guard.
        """
        guest = self.env["res.users"]._create_community_guest()
        self.env["res.users"]._gc_community_guests()
        self.assertTrue(guest.exists())

    def test_gc_ignores_the_portal_guest_population(self):
        """Each GC sweeps its own flock.

        ``website_login_branding``'s portal guests carry a different flag and
        a different "worth keeping" rule (orders, not messages); this cron
        deleting them -- or vice versa -- would apply the wrong rule to the
        wrong account.
        """
        portal_guest = self.env["res.users"]._create_platform_guest()
        self._backdate(portal_guest)
        self.env["res.users"]._gc_community_guests()
        self.assertTrue(
            portal_guest.exists(),
            "the community GC must never touch portal guests",
        )

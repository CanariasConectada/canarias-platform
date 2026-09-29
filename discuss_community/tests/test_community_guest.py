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

    def _gc(self):
        return self.env["res.users"]._gc_community_guests()

    def test_gc_removes_an_inactive_guest(self):
        """Inactive past the window: user, partner, seats and devices go."""
        guest = self.env["res.users"]._create_community_guest(zone="guanarteme")
        partner = guest.partner_id
        self.env["mail.push.device"].sudo().create(
            {
                "partner_id": partner.id,
                "endpoint": "https://push.example.com/dcm",
                "keys": '{"p256dh": "x", "auth": "y"}',
            }
        )
        self._backdate(guest)
        counters = self._gc()
        self.assertGreaterEqual(counters["users_removed"], 1)
        self.assertFalse(guest.exists(), "the inactive guest must be removed")
        self.assertFalse(partner.exists(), "its partner has nothing to keep")
        self.assertFalse(
            self.env["discuss.channel.member"]
            .sudo()
            .search([("partner_id", "=", partner.id)])
        )
        self.assertFalse(
            self.env["mail.push.device"]
            .sudo()
            .search([("partner_id", "=", partner.id)])
        )

    def test_gc_keeps_an_active_guest(self):
        """An old account with recent activity (a login) is kept."""
        guest = self.env["res.users"]._create_community_guest()
        self._backdate(guest)
        self.env["res.users.log"].with_user(guest).sudo().create({})
        self._gc()
        self.assertTrue(guest.exists())
        self.assertTrue(guest.active)

    def test_gc_keeps_a_guest_with_recent_presence(self):
        guest = self.env["res.users"]._create_community_guest()
        self._backdate(guest)
        self.env["mail.presence"].sudo().create(
            {"user_id": guest.id, "last_poll": fields.Datetime.now()}
        )
        self._gc()
        self.assertTrue(guest.active)

    def test_gc_keeps_messages_readable(self):
        """A guest who posted: the account goes, the author partner is only
        archived, and the message stays readable with its author."""
        guest = self.env["res.users"]._create_community_guest()
        message = self.channel_general.sudo().message_post(
            body="still here",
            author_id=guest.partner_id.id,
            message_type="comment",
        )
        self.env.cr.execute(
            "UPDATE mail_message SET date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=30), message.id),
        )
        message.invalidate_recordset(["date"])
        partner = guest.partner_id
        self._backdate(guest)
        self._gc()
        self.assertFalse(guest.exists().filtered("active"), "the account goes")
        self.assertTrue(partner.exists(), "the author partner must stay")
        self.assertFalse(partner.active, "the author partner is archived")
        read = message.with_user(self.employee).read(["body", "author_id"])[0]
        self.assertEqual(read["author_id"][0], partner.id)
        self.assertIn("still here", str(read["body"]))

    def test_gc_never_touches_a_merchant(self):
        """Only community guests are swept, however idle anybody else is."""
        company = self.env["res.company"].create(
            {"name": "DCM Shop", "commercial_zone": "guanarteme"}
        )
        merchant = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "DCM Merchant",
                    "login": "dcm_merchant",
                    "company_id": company.id,
                    "company_ids": [(6, 0, company.ids)],
                    "group_ids": [(6, 0, self.portal_group.ids)],
                }
            )
        )
        for user in (merchant, self.member, self.employee):
            self._backdate(user)
        self._gc()
        for user in (merchant, self.member, self.employee):
            self.assertTrue(user.exists() and user.active)
            self.assertTrue(user.partner_id.active)

    def test_gc_never_touches_a_young_guest(self):
        """An account younger than the window is kept even with no logins."""
        guest = self.env["res.users"]._create_community_guest()
        self._gc()
        self.assertTrue(guest.exists())

    def test_gc_is_idempotent(self):
        guest = self.env["res.users"]._create_community_guest()
        self._backdate(guest)
        self._gc()
        second = self._gc()
        self.assertEqual(second["users_removed"], 0)
        self.assertEqual(second["users_archived"], 0)
        self.assertEqual(second["partners_archived"], 0)

    def test_gc_window_comes_from_the_parameter(self):
        icp = self.env["ir.config_parameter"].sudo()
        guest = self.env["res.users"]._create_community_guest()
        self._backdate(guest, days=10)
        icp.set_param("discuss_community.guest_inactivity_days", "30")
        self._gc()
        self.assertTrue(guest.exists(), "10 days idle is inside a 30-day window")
        icp.set_param("discuss_community.guest_inactivity_days", "nonsense")
        self.assertEqual(self.env["res.users"]._community_guest_inactivity_days(), 7)
        icp.set_param("discuss_community.guest_inactivity_days", "7")
        self._gc()
        self.assertFalse(guest.exists())

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

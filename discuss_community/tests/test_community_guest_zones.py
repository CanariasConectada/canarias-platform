# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged

from odoo.addons.discuss_community.controllers.main import _company_zone

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityGuestZones(CommunityMixin, TransactionCase):
    """Guests are seated in their zone, then join and leave at will."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()
        cls.guest = cls.env["res.users"]._create_community_guest(zone="guanarteme")
        cls.Member = cls.env["discuss.channel.member"]

    def _seat(self, user, channel):
        return self.Member.sudo().search(
            [
                ("channel_id", "=", channel.id),
                ("partner_id", "=", user.partner_id.id),
            ]
        )

    # ------------------------------------------------------------------
    # Arrival zone
    # ------------------------------------------------------------------

    def test_zone_company_gives_its_zone_key(self):
        """A commercial-zone company is 'canarias' by commercial_zone; its
        zone is its zone key. This is what the zone sites were missing."""
        company = self.env["res.company"].create({"name": "DCM Zone Company"})
        if "zone_company_key" not in company._fields:
            self.skipTest("zone_company_ownership is not installed")
        company.write(
            {"commercial_zone": "canarias", "zone_company_key": "tamaraceite"}
        )
        self.assertEqual(_company_zone(company), "tamaraceite")

    def test_merchant_company_gives_its_commercial_zone(self):
        company = self.env["res.company"].create(
            {"name": "DCM Merchant Company", "commercial_zone": "lomolosfrailes"}
        )
        self.assertEqual(_company_zone(company), "lomolosfrailes")

    def test_guest_is_seated_in_general_and_its_zone(self):
        self.assertTrue(self._seat(self.guest, self.channel_general))
        self.assertTrue(self._seat(self.guest, self.channel_guanarteme))
        self.assertFalse(self._seat(self.guest, self.channel_tamaraceite))

    def test_returning_guest_without_zone_adopts_the_arrival_zone(self):
        guest = self.env["res.users"]._create_community_guest(zone="canarias")
        guest._community_guest_adopt_zone("tamaraceite")
        self.assertEqual(guest.chat_zone, "tamaraceite")
        self.assertTrue(self._seat(guest, self.channel_tamaraceite))
        # A guest that already has a neighbourhood keeps it.
        guest._community_guest_adopt_zone("guanarteme")
        self.assertEqual(guest.chat_zone, "tamaraceite")
        self.assertFalse(self._seat(guest, self.channel_guanarteme))

    # ------------------------------------------------------------------
    # Join and leave
    # ------------------------------------------------------------------

    def test_guest_joins_and_leaves_another_zone_channel(self):
        channel = self.channel_tamaraceite.with_user(self.guest)
        channel.channel_join()
        self.assertTrue(self._seat(self.guest, self.channel_tamaraceite))
        channel.action_unfollow()
        self.assertFalse(self._seat(self.guest, self.channel_tamaraceite))

    def test_guest_leaves_its_own_zone_and_general(self):
        for channel in (self.channel_guanarteme, self.channel_general):
            channel.with_user(self.guest).action_unfollow()
            self.assertFalse(self._seat(self.guest, channel))
        # And comes back.
        self.channel_guanarteme.with_user(self.guest).channel_join()
        self.assertTrue(self._seat(self.guest, self.channel_guanarteme))

    def test_guest_still_reads_only_its_own_row_after_joining(self):
        self.channel_tamaraceite.sudo()._add_members(
            partners=self.employee.partner_id, post_joined_message=False
        )
        self.channel_tamaraceite.with_user(self.guest).channel_join()
        rows = (
            self.Member.with_user(self.guest)
            .search([("channel_id", "=", self.channel_tamaraceite.id)])
            .partner_id
        )
        self.assertEqual(rows, self.guest.partner_id)

    def test_nightly_sync_respects_the_guest_choice(self):
        """A left channel does not come back, a joined one is not removed."""
        self.channel_guanarteme.with_user(self.guest).action_unfollow()
        self.channel_lomo.with_user(self.guest).channel_join()
        self.env["res.users"]._cron_sync_zone_channels()
        self.assertFalse(self._seat(self.guest, self.channel_guanarteme))
        self.assertTrue(self._seat(self.guest, self.channel_lomo))

    def test_every_community_member_is_self_managed(self):
        """Guests and registered residents choose; employees keep the sync."""
        self.assertEqual(self.member._zone_self_managed_users(), self.member)
        self.assertEqual(self.guest._zone_self_managed_users(), self.guest)
        self.assertFalse(self.employee._zone_self_managed_users())

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def test_seat_existing_guests_is_idempotent(self):
        self._seat(self.guest, self.channel_guanarteme).unlink()
        first = self.env["res.users"]._seat_community_guests()
        self.assertGreaterEqual(first["added"], 1)
        self.assertEqual(first["removed"], 0)
        self.assertTrue(self._seat(self.guest, self.channel_guanarteme))
        second = self.env["res.users"]._seat_community_guests()
        self.assertEqual(second, {"added": 0, "removed": 0})

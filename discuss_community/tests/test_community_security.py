# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityMemberAccess(CommunityMixin, TransactionCase):
    """What being ``base.group_user`` does NOT give a community member.

    The product decision makes residents internal, and internal is a wide
    door: this suite pins down the edges that matter for Phase 1. The audit
    behind it (what base.group_user ACLs expose and what already narrows it)
    is written up in the module's DESCRIPTION.md; these tests are the subset
    that must never regress silently.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.orm.models")
    def test_member_cannot_read_any_sale_order(self):
        """No sale ACL at all: not "the wrong company's orders", NONE.

        Core grants ``sale.order`` read to portal (own documents, by rule)
        and to the sales/accounting groups -- plain employees hold no ACL on
        the model whatsoever, so a community member reading ANY order, own
        company or other, must be an ``AccessError``. Asserted against an
        order in a foreign company because that is the leak that would hurt:
        a resident reading a merchant's sales.
        """
        if "sale.order" not in self.env:
            self.skipTest("sale is not installed in this database")
        company = (
            self.env["res.company"]
            .sudo()
            .create({"name": "DCM Foreign Shop", "commercial_zone": "tamaraceite"})
        )
        partner = self.env["res.partner"].sudo().create({"name": "DCM Buyer"})
        order = (
            self.env["sale.order"]
            .sudo()
            .with_company(company)
            .create({"partner_id": partner.id, "company_id": company.id})
        )
        with self.assertRaises(AccessError):
            self.env["sale.order"].with_user(self.member).browse(order.id).read(
                ["name"]
            )
        with self.assertRaises(AccessError):
            self.env["sale.order"].with_user(self.member).search([])

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.orm.models")
    def test_member_cannot_create_or_write_companies(self):
        """``res.company`` is read-only for employees, and must stay so.

        The employee ACL on companies is (1,0,0,0); a community member
        minting or renaming companies would corrupt the multi-company spine
        the whole platform hangs on (one company per merchant NIF, zones as
        properties). Read is expected -- record rules scope WHICH companies
        -- so only create and write are asserted.
        """
        Company = self.env["res.company"].with_user(self.member)
        with self.assertRaises(AccessError):
            Company.create({"name": "DCM Rogue Company"})
        with self.assertRaises(AccessError):
            Company.browse(self.main_company.id).write({"name": "DCM Renamed"})

    @mute_logger("odoo.addons.base.models.ir_model", "odoo.orm.models")
    def test_member_cannot_grant_themselves_groups(self):
        """The community shape is not self-service.

        ``group_ids`` is not in ``SELF_WRITEABLE_FIELDS`` and a plain
        employee has no write ACL on ``res.users``: the member must not be
        able to escalate out of the stripped backend by editing their own
        groups. (What they MAY edit -- ``chat_zone`` -- is a product
        feature, covered by ``discuss_channel_zone``.)
        """
        with self.assertRaises(AccessError):
            self.member.with_user(self.member).write(
                {"group_ids": [(4, self.env.ref("base.group_system").id)]}
            )

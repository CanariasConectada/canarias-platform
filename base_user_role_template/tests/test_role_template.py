# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestRoleTemplate(TransactionCase):
    """The role seeds the groups; it no longer cages them.

    Upstream ``base_user_role`` re-derives ``group_ids`` on every
    ``res.users.write``, so anything granted by hand evaporated on the next
    write -- without an error, which is exactly why it kept being reported
    as "why did the permission disappear".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_in_role = cls.env["res.groups"].create(
            {"name": "Role Template: carried by the role"}
        )
        cls.group_extra = cls.env["res.groups"].create(
            {"name": "Role Template: granted by hand"}
        )
        cls.role = cls.env["res.users.role"].create(
            {
                "name": "Role Template: the role",
                "implied_ids": [Command.link(cls.group_in_role.id)],
            }
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "Role Template User",
                "login": "role-template-user@example.invalid",
                "role_line_ids": [Command.create({"role_id": cls.role.id})],
            }
        )

    def test_assigning_a_role_applies_its_groups(self):
        self.assertIn(self.group_in_role, self.user.group_ids)

    def test_a_hand_granted_group_survives_the_next_write(self):
        """The whole request: the template must not block the exception."""
        self.user.write({"group_ids": [Command.link(self.group_extra.id)]})
        # Any later write used to be the moment the grant evaporated.
        self.user.write({"signature": "still me"})
        self.user.set_groups_from_roles()
        self.assertIn(
            self.group_extra,
            self.user.group_ids,
            "a group granted by hand must survive the role sync",
        )
        self.assertIn(self.group_in_role, self.user.group_ids)

    def test_a_role_group_removed_by_hand_is_healed_back(self):
        """The role stays the guaranteed minimum."""
        self.user.write({"group_ids": [Command.unlink(self.group_in_role.id)]})
        self.assertIn(
            self.group_in_role,
            self.user.group_ids,
            "the sync at the end of the write must restore the template",
        )

    def test_removing_the_role_resets_to_the_template(self):
        """force=True keeps the upstream full replacement on purpose."""
        self.user.write({"group_ids": [Command.link(self.group_extra.id)]})
        self.user.role_line_ids.unlink()
        self.assertNotIn(self.group_in_role, self.user.group_ids)
        self.assertNotIn(
            self.group_extra,
            self.user.group_ids,
            "a role change is a reset: the account starts from a clean template",
        )

    def test_the_stale_banner_is_retired(self):
        self.assertFalse(
            self.user.show_alert,
            "the banner warns about a reversion that no longer happens",
        )

    def test_a_user_without_roles_is_left_alone(self):
        loner = self.env["res.users"].create(
            {
                "name": "Role Template Loner",
                "login": "role-template-loner@example.invalid",
                "group_ids": [Command.link(self.group_extra.id)],
            }
        )
        loner.set_groups_from_roles()
        self.assertIn(self.group_extra, loner.group_ids)

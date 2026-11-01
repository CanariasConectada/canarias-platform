# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


class CommunityMixin:
    """Minimal cast for the community-member suite.

    A mixin (not a ``TransactionCase``) because the HTTP suite needs
    ``HttpCase`` and the same scenario has to serve both bases without
    duplicating the setup -- same shape as ``discuss_channel_zone``'s
    ``ZoneChannelMixin``.

    The cast is one community member and one ordinary employee: the smallest
    pair with which every claim of this module ("the member's backend is only
    Discuss", "the employee's backend is untouched") can be both affirmed and
    refuted.
    """

    @classmethod
    def _setup_community_fixtures(cls):
        cls.main_company = cls.env.ref("base.main_company")
        cls.internal_group = cls.env.ref("base.group_user")
        cls.portal_group = cls.env.ref("base.group_portal")
        cls.community_group = cls.env.ref("discuss_community.group_community_member")
        cls.zone_gate_group = cls.env.ref(
            "discuss_channel_zone.group_zone_channel_member"
        )
        cls.discuss_action = cls.env.ref("mail.action_discuss")
        cls.discuss_root = cls.env.ref("mail.menu_root_discuss")
        cls.employees_channel = cls.env.ref("mail.channel_all_employees")

        cls.channel_general = cls.env.ref("discuss_channel_zone.channel_canarias")
        cls.channel_guanarteme = cls.env.ref("discuss_channel_zone.channel_guanarteme")
        cls.channel_tamaraceite = cls.env.ref(
            "discuss_channel_zone.channel_tamaraceite"
        )
        cls.channel_lomo = cls.env.ref("discuss_channel_zone.channel_lomolosfrailes")
        cls.zone_channels = (
            cls.channel_general
            | cls.channel_guanarteme
            | cls.channel_tamaraceite
            | cls.channel_lomo
        )

        # Uninvited signup must be open for the signup-promotion tests: the
        # platform runs b2c (218 public sites people register on). BOTH knobs
        # on purpose -- the `website` module overrides
        # `_get_signup_invitation_scope` to read the CURRENT WEBSITE's
        # `auth_signup_uninvited` first and only falls back to the config
        # parameter (website/models/res_users.py:65-68).
        cls.env["ir.config_parameter"].sudo().set_param(
            "auth_signup.invitation_scope", "b2c"
        )
        cls.env["website"].sudo().search([]).write({"auth_signup_uninvited": "b2c"})

        User = cls.env["res.users"].with_context(no_reset_password=True)
        # The member is created with the exact shape the two production doors
        # produce (same helper), so every assertion below is about the shape
        # itself, not about which door happened to mint it.
        cls.member = User.create(
            {
                "name": "DCM Member",
                "login": "dcm_member",
                "password": "dcm_member",
                "email": "dcm_member@example.com",
                "company_id": cls.main_company.id,
                "company_ids": [(6, 0, cls.main_company.ids)],
                "group_ids": [(6, 0, User._community_group_ids())],
                "chat_zone": "guanarteme",
            }
        )
        cls.employee = User.create(
            {
                "name": "DCM Employee",
                "login": "dcm_employee",
                "password": "dcm_employee",
                "email": "dcm_employee@example.com",
                "company_id": cls.main_company.id,
                "company_ids": [(6, 0, cls.main_company.ids)],
                "group_ids": [(6, 0, cls.internal_group.ids)],
            }
        )

    def _zone_channels_of(self, user):
        """The managed zone channels this user is seated in.

        Scoped to ``discuss_channel_zone``'s four channels on purpose: what
        other channels a user belongs to (the employees channel above all) is
        the subject of its OWN tests, not noise in these.
        """
        members = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id", "in", self.zone_channels.ids),
                    ("partner_id", "=", user.partner_id.id),
                ]
            )
        )
        return members.channel_id

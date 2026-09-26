# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, common as test_common, tagged


@tagged("post_install", "-at_install")
class TestDiscussLayout(HttpCase):
    """The notifications banner must not squeeze Discuss.

    Regression of 19.0.1.4.0 seen in production: the banner wrapper put
    core's Discuss root in a flex row, where it shrank to its content and left
    about 40% of the screen empty next to a short thread.
    """

    def setUp(self):
        super().setUp()
        # Same reason as the guest tours: no screencast (BrokenPipeError on
        # a frame acknowledged while Chrome closes).
        self.startPatcher(
            patch.object(
                test_common, "Screencaster", lambda *args: test_common.NoScreencast()
            )
        )

    def test_discuss_takes_the_whole_width(self):
        admin = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "DCM Layout Admin",
                    "login": "dcm_layout_admin",
                    "password": "dcm_layout_admin",
                    "email": "dcm_layout_admin@example.com",
                    "group_ids": [(6, 0, [self.env.ref("base.group_system").id])],
                }
            )
        )
        channel = self.env["discuss.channel"].create(
            {"name": "DCM Short Thread", "channel_type": "channel"}
        )
        channel._add_members(users=admin, post_joined_message=False)
        channel.with_user(admin).message_post(
            body="Short thread", message_type="comment", subtype_xmlid="mail.mt_comment"
        )
        self.start_tour(
            "/odoo/action-mail.action_discuss?active_id=discuss.channel_%s"
            % channel.id,
            "discuss_community_layout",
            login="dcm_layout_admin",
        )

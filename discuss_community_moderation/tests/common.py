# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json


class CommunityModerationMixin:
    """Shared fixtures for the bridge suites.

    A mixin (not a ``TransactionCase``) for the same reason as the engine's
    ``DiscussModerationMixin``: the abuse suite needs ``HttpCase`` and the
    same cast has to serve both bases without duplicating the setup.

    The cast, and what each member is there to prove or refute:

    * two moderated channels (A and B) -- per-channel trust needs a second
      moderated channel to be falsifiable -- plus an unmoderated control;
    * a community MEMBER (registered resident: internal +
      ``group_community_member``), the persona the probation applies to;
    * a community GUEST (walk-in: same groups plus ``is_community_guest``),
      the persona that must never ride the probation out of moderation;
    * a plain internal employee, who must never be held no matter what;
    * a moderator, who decides the queue and is exempt on their own channel.
    """

    @classmethod
    def _setup_community_moderation_fixtures(cls):
        cls.public_user = cls.env.ref("base.public_user")
        cls.main_company = cls.env.ref("base.main_company")
        cls.Pending = cls.env["discuss.channel.pending.message"]
        cls.Moderation = cls.env["discuss.channel.moderation"]

        # `group_public_id = False` EXPLICITLY, for the same reason the
        # engine's fixtures spell it out: omitting it makes the compute fill
        # in `base.group_user` and the record rule then hides the channel
        # from non-internal readers, so visibility tests would pass by
        # seeing nothing because there is nothing to see.
        cls.channel_a, cls.channel_b, cls.channel_free = cls.env[
            "discuss.channel"
        ].create(
            [
                {
                    "name": "Community Moderated A",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
                {
                    "name": "Community Moderated B",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
                {
                    "name": "Community Free",
                    "channel_type": "channel",
                    "group_public_id": False,
                },
            ]
        )

        cls.moderator = cls.env["res.users"].create(
            {
                "name": "DCCM Moderator",
                "login": "dccm_moderator",
                "email": "dccm_moderator@example.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "discuss_channel_moderation.group_moderation_user"
                            ).id
                        ],
                    )
                ],
            }
        )

        cls.moderation_a, cls.moderation_b = cls.Moderation.create(
            [
                {
                    "channel_id": cls.channel_a.id,
                    "moderator_user_ids": [(6, 0, cls.moderator.ids)],
                },
                {
                    "channel_id": cls.channel_b.id,
                    "moderator_user_ids": [(6, 0, cls.moderator.ids)],
                },
            ]
        )

        User = cls.env["res.users"].with_context(no_reset_password=True)
        # Built with the exact shape the production doors produce (the same
        # `_community_group_ids` helper), so the assertions are about the
        # shape, not about which door minted it.
        cls.member = User.create(
            {
                "name": "DCCM Member",
                "login": "dccm_member",
                "password": "dccm_member_pwd",
                "email": "dccm_member@example.com",
                "company_id": cls.main_company.id,
                "company_ids": [(6, 0, cls.main_company.ids)],
                "group_ids": [(6, 0, User._community_group_ids())],
            }
        )
        cls.member_b = User.create(
            {
                "name": "DCCM Member B",
                "login": "dccm_member_b",
                "email": "dccm_member_b@example.com",
                "company_id": cls.main_company.id,
                "company_ids": [(6, 0, cls.main_company.ids)],
                "group_ids": [(6, 0, User._community_group_ids())],
            }
        )
        # A real walk-in guest, minted by the production helper: the suite
        # must moderate what the button actually creates, not a hand-rolled
        # imitation of it.
        cls.community_guest = cls.env["res.users"]._create_community_guest()
        cls.community_guest.write({"password": "dccm_cguest_pwd"})
        cls.employee = User.create(
            {
                "name": "DCCM Employee",
                "login": "dccm_employee",
                "email": "dccm_employee@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    # ------------------------------------------------------------------
    # Posting helpers (same shape as the engine's: the route posts sudo,
    # and sudo() not changing env.user is what the hold relies on)
    # ------------------------------------------------------------------

    def _post_as_user(self, channel, user, body="hello", message_type="comment"):
        return (
            channel.with_user(user)
            .sudo()
            .message_post(
                body=body,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )
        )

    def _channel_comments(self, channel):
        return self.env["mail.message"].search(
            [
                ("model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
                ("message_type", "=", "comment"),
            ]
        )

    def _pending_of(self, channel, user=None):
        domain = [("channel_id", "=", channel.id)]
        if user is not None:
            domain.append(("partner_id", "=", user.partner_id.id))
        return self.Pending.search(domain)

    def _message_type_values(self):
        """Every ``mail.message.message_type`` value, READ from the field.

        Never a hand-written list -- same reasoning, verbatim, as the
        engine's helper: modules extend the selection, and a sweep that
        reads it covers new values the day they are installed.
        """
        return [
            value
            for value, _label in self.env["mail.message"].fields_get(["message_type"])[
                "message_type"
            ]["selection"]
        ]

    def _approve(self, pending):
        return pending.with_user(self.moderator).action_approve()

    def _reject(self, pending, reason=None):
        return pending.with_user(self.moderator).action_reject(reason=reason)

    def _earn_trust(self, channel, user, count):
        """Post and approve ``count`` messages for ``user`` on ``channel``."""
        for index in range(count):
            self._post_as_user(channel, user, body="earning trust %s" % index)
            pending = self._pending_of(channel, user).filtered(
                lambda row: row.state == "pending"
            )
            self._approve(pending)

    # ------------------------------------------------------------------
    # Bus assertions
    #
    # `bus.bus` rows are only created at PRECOMMIT (`_sendone` queues the
    # values in `env.cr.precommit.data`), so inside a TransactionCase the
    # queue itself is the only observable truth about what was sent.
    # ------------------------------------------------------------------

    def _bus_payloads(self, listener_record, notification_type):
        """Payloads of ``notification_type`` queued for this exact listener."""
        values = self.env.cr.precommit.data.get("bus.bus.values", [])
        payloads = []
        for value in values:
            message = json.loads(value["message"])
            if message.get("type") != notification_type:
                continue
            channel = json.loads(value["channel"])
            if channel[1:3] == [listener_record._name, listener_record.id]:
                payloads.append(message["payload"])
        return payloads

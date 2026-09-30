# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class DiscussChannelModeration(models.Model):
    """Two more switches and a probation counter on the per-channel row.

    The engine's row already answers "are anonymous guests held?" and "are
    portal users held?". `discuss_community` introduced two populations the
    engine deliberately knows nothing about -- community guests and community
    members are INTERNAL users, and the engine's contract is "internal users
    are never held". These fields let a channel say, per channel and only per
    channel, that those two populations are held too.

    ON EXISTING ROWS (the four rows `discuss_channel_zone` seeds, and any row
    an administrator created by hand): installing this module adds the columns
    through the ORM's normal field initialisation, which applies each field's
    default to every pre-existing row. No XML override of the seeded records
    and no post_init hook is needed -- the seeded rows come out of the install
    with `moderate_community_guests = True`, `moderate_new_users = True` and
    `trust_threshold = 3`, and the `noupdate="1"` on the seed data stays
    untouched. `tests/test_community_hold.py` pins that behaviour so a future
    refactor cannot silently un-moderate the zone channels.
    """

    _inherit = "discuss.channel.moderation"

    moderate_community_guests = fields.Boolean(
        string="Moderate Community Guests",
        default=True,
        help="Hold every comment posted by a walk-in community guest (the "
        "'Enter as guest' button) until a moderator approves it. Community "
        "guests are anonymous throwaway accounts: they never build up trust "
        "and stay moderated for as long as this switch is on.",
    )
    moderate_new_users = fields.Boolean(
        string="Moderate New Community Members",
        default=True,
        help="Hold the comments of registered community members until they "
        "have had 'Trust Threshold' messages approved on this channel. Once "
        "past the threshold they post freely here; the counter is per "
        "channel, so a newcomer to another moderated channel starts over "
        "there.",
    )
    trust_threshold = fields.Integer(
        string="Trust Threshold",
        default=3,
        help="Approved messages a community member needs on this channel "
        "before their posts stop being held. Zero (or a negative value) "
        "means members are never held even with 'Moderate New Community "
        "Members' on.",
    )

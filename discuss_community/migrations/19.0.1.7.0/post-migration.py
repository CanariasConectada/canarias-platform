# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Seat the existing guests in the general channel and their zone channel.

    Only missing seats are added, nothing is removed, so running it again is a
    no-op. The logic lives on the model (``_seat_community_guests``).
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.users"]._seat_community_guests()

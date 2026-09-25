# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bring the guests that already exist to the Discuss guest profile.

    Removes their seats in the staff channels ("general", "Administrators"),
    takes them out of their OdooBot DM and disables OdooBot for them. The
    logic lives on the model (``_cleanup_community_guests``) so it is tested
    like any other code path; this script only runs it once.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.users"]._cleanup_community_guests()

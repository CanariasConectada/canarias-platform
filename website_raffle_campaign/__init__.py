# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from . import controllers, models, wizard


def uninstall_hook(env):
    """Leave nothing behind: alias redirects and private receipt files."""
    env["website.rewrite"].sudo().with_context(active_test=False).search(
        [("name", "=like", "raffle.campaign:%")]
    ).unlink()
    env["ir.attachment"].sudo().search([("res_model", "=", "raffle.entry")]).unlink()

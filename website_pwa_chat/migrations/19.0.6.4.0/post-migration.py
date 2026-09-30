# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Name the support conversations that already exist after who asked.

    Until 19.0.6.4.0 the name was set once, when the conversation opened, and
    a visitor who identified themselves afterwards stayed "Soporte ·
    Visitante" in every agent's sidebar. The rename is the same method the
    identify form now calls, so an old conversation ends up exactly as a new
    one would: the typed name, else the account, else the guest.

    Run with no language in the context, so the prefix is the source
    "Soporte · ", which is what the agents -- who work in Spanish -- read.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    channels = env["discuss.channel"].search([("support_key", "!=", False)])
    before = {channel.id: channel.name for channel in channels}
    channels._support_refresh_name()
    renamed = [channel for channel in channels if channel.name != before[channel.id]]
    _logger.info(
        "Renamed %s of %s support conversations after their requester",
        len(renamed),
        len(channels),
    )

# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Take the support conversations out of the agents' Discuss sidebar.

    They were seated pinned, so every conversation ever opened sat in Mensajes
    directos -- one row each, most of them empty, because a visitor who lands
    on the page opens a conversation whether or not they type anything. An
    administrator opening Discuss met a wall of "Soporte · Visitante".

    Unpinning does not unseat anybody: the agents keep the seat that lets them
    answer and be notified, and Odoo re-pins a member as soon as the channel
    has fresh interest, so a conversation somebody actually writes in comes
    back on its own. The queue under Discusión > Soporte is where the rest is
    read.

    The visitor's own row is deliberately left alone -- it is their
    conversation -- which is why this asks who the agents are rather than
    unpinning everyone.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Channel = env["discuss.channel"].sudo()

    channels = Channel.search([("support_key", "!=", False)])
    if not channels:
        return

    agents = Channel._support_agents()
    if not agents:
        _logger.info("Sin agentes de soporte: nada que desanclar")
        return

    members = channels.channel_member_ids.filtered(
        lambda member: member.partner_id in agents.partner_id
    )
    if not members:
        return

    members.unpin_dt = fields.Datetime.now()
    _logger.info(
        "Desancladas %s membresías de agente en %s conversaciones de soporte",
        len(members),
        len(channels),
    )

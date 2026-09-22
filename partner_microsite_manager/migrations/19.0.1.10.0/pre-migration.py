# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)

MODULE = "partner_microsite_manager"
XMLID = "action_own_microsite_content"


def migrate(cr, version):
    """Let the "Page content" action change from a window action to a server one.

    The menu used to open an ``ir.actions.act_window`` straight onto the
    transient, which answered every administrator with "your account is not
    linked to a shop". It now opens an ``ir.actions.server`` that decides which
    screen the caller should get.

    An external id cannot change model in place: the loader stops with "found
    record of different model ir.actions.act_window" and takes the whole update
    down with it. So the old row goes first, here, where nothing is looking at
    it yet -- the data file recreates the id under the new model moments later,
    and the menu is rebound in the same pass.

    The window action itself is deleted too, not just its external id: left
    behind it would be an unreferenced action that still shows up in
    Settings > Technical > Actions, and somebody would eventually wonder which
    of the two is the real one.
    """
    cr.execute(
        """
        SELECT id, res_id FROM ir_model_data
         WHERE module = %s AND name = %s AND model = 'ir.actions.act_window'
        """,
        (MODULE, XMLID),
    )
    row = cr.fetchone()
    if not row:
        return  # Already a server action, or a clean install.

    data_id, action_id = row
    # The menu points at "ir.actions.act_window,<id>". Blank it rather than
    # leave it dangling: the data file sets it again on the next line of the
    # same update, and a menu with a broken action is a menu that raises when
    # somebody clicks it in between.
    cr.execute(
        "UPDATE ir_ui_menu SET action = NULL WHERE action = %s",
        ("ir.actions.act_window,%s" % action_id,),
    )
    cr.execute("DELETE FROM ir_model_data WHERE id = %s", (data_id,))
    cr.execute("DELETE FROM ir_act_window WHERE id = %s", (action_id,))
    _logger.info(
        "Retirada la acción de ventana %s.%s (id %s) para recrearla como "
        "acción de servidor",
        MODULE,
        XMLID,
        action_id,
    )

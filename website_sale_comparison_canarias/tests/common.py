# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.addons.website_sale_comparison_canarias.models.website import PARAM_ENABLED


def set_comparison_enabled(env, enabled):
    """Flip the platform switch the way the settings screen does."""
    env["ir.config_parameter"].sudo().set_param(PARAM_ENABLED, repr(bool(enabled)))


class ComparisonEnabledCase:
    """Mixin: the comparator is ON for the whole class.

    The module ships switched off (data/ir_config_parameter.xml), so a test
    of what the comparator DOES has to turn it on first; a test of the
    switch itself (test_comparison_switch.py) sets it explicitly instead.
    Listed before the Odoo test case in the bases, so ``super()`` reaches
    ``setUpClass`` of the real case.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        set_comparison_enabled(cls.env, True)

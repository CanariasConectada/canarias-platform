# -*- coding: utf-8 -*-
from odoo import models


class Website(models.Model):
    _inherit = "website"

    def get_certifications(self):
        """Read the website certifications from ir.config_parameter."""
        self.ensure_one()

        Param = self.env["ir.config_parameter"].sudo()

        has_silver = Param.get_param(f"website.{self.id}.has_silver") == "true"
        has_sostenible = Param.get_param(f"website.{self.id}.has_sostenible") == "true"

        return {
            "has_silver": has_silver,
            "has_sostenible": has_sostenible,
        }

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    social_facebook = fields.Char(string="Facebook")
    social_instagram = fields.Char(string="Instagram")
    social_twitter = fields.Char(string="Twitter/X")
    social_youtube = fields.Char(string="YouTube")
    social_linkedin = fields.Char(string="LinkedIn")

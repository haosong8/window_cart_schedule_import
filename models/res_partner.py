# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    allow_window_schedule_upload = fields.Boolean(
        string="Allow Window Schedule Upload (B2B)",
        help="If enabled, this partner can upload window schedules on the website cart.",
    )



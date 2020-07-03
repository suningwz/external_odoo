# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
_logger = logging.getLogger(__name__)

from odoo import api, models, fields

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    external_sale_order_id = fields.Many2one(
        comodel_name='external.sale.order',
        string='External Sale Order Id'
    )
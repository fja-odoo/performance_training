from odoo import models, fields
from time import sleep


class ResPartner(models.Model):
    _inherit = 'res.partner'

    total_amount_on_so = fields.Float(compute='_compute_total_amount_on_so')

    def _compute_total_amount_on_so(self):
        # for record in self:
        #     sale_orders = self.env['sale.order'].search([('partner_id', '=', record.id)])
        #     total = sum(sale_orders.mapped('amount_total'))
        #     record.total_amount_on_so = total

        # for record in self:
        #     sale_orders = self.env['sale.order'].search_read([('partner_id', '=', record.id)], ['amount_total'])
        #     record.total_amount_on_so = sum([so['amount_total'] for so in sale_orders])

        # for record in self:
        #     record.total_amount_on_so = sum(record.sale_order_ids.mapped('amount_total'))

        # for record in self:
        #     record.total_amount_on_so = sum(record.sale_order_ids.with_context(prefetch_fields=False).mapped('amount_total'))

        amount_per_partner = self.env['sale.order']._read_group(
            [('partner_id', 'in', self.ids)],
            ['partner_id'],
            ['amount_total:sum'],
        )
        amount_per_partner = dict(amount_per_partner)
        for partner in self:
            partner.total_amount_on_so = amount_per_partner.get(partner.id, 0)

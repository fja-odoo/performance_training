from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    total_amount_on_so = fields.Float(compute='_compute_total_amount_on_so')

    def _compute_total_amount_on_so(self):
        # 26 sec
        # for partner in self:
            # sale_orders = self.env['sale.order'].search([('partner_id', '=', partner.id)])
            # partner.total_amount_on_so = sum(sale_orders.mapped('amount_total'))

        # 19 sec
        # for partner in self:
        #     sale_orders = self.env['sale.order'].search_read([('partner_id', '=', partner.id)], ['amount_total'])
        #     partner.total_amount_on_so = sum([so['amount_total'] for so in sale_orders])

        # 2 sec
        # for partner in self:
        #     partner.total_amount_on_so = sum(partner.sale_order_ids.mapped('amount_total'))

        # 1.3 sec
        # for partner in self:
        #     partner.total_amount_on_so = sum(partner.sale_order_ids.with_context(prefetch_fields=False).mapped('amount_total'))

        # .5
        amount_per_partner = self.env['sale.order']._read_group(
            domain=[('partner_id', 'in', self.ids)],
            groupby=['partner_id'],
            aggregates=['amount_total:sum'],
        )
        amount_per_partner = dict(amount_per_partner)
        for partner in self:
            partner.total_amount_on_so = amount_per_partner.get(partner.id, 0)

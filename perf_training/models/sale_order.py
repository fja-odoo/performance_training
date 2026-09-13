from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    # _order = 'partner_id, date_order desc, id desc'

    new_sequence = fields.Char(string='New Sequence', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['new_sequence'] = self.env['ir.sequence'].next_by_code('perf_odoo.sale_order_no_gap_sequence') or _('New')
        return super(SaleOrder, self).create(vals_list)

    def _action_confirm(self):
        # for order in self:
        #     for i in range(1, 365):
        #         new_order = order.copy(default={'date_order': order.date_order + relativedelta(days=i)})
        #         new_order.activity_schedule(
        #             user_id=new_order.user_id.id,
        #             date_deadline=(order.date_order + relativedelta(days=-1)).date(),
        #             activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
        #             summary=_('Follow up on sale order'),
        #         )

        so_to_create = []
        for order in self:
            for i in range(1, 30):
                so_to_create += order.copy_data(default={'date_order': order.date_order + relativedelta(days=i)})
        new_orders = self.create(so_to_create)
        for order in new_orders:
            order.activity_schedule(
                user_id=order.user_id.id,
                date_deadline=(order.date_order + relativedelta(days=-1)).date(),
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                summary=_('Follow up on sale order'),
            )

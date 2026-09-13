from odoo import fields, models


class ResPartner(models.Model):
    """Exercise 4 -- the "who owes us money" list view.

    The credit controller opens a list of customers with an overdue column
    and sorts it. 80 partners per page, one page takes forever.
    """
    _inherit = 'res.partner'

    overdue_amount = fields.Monetary(
        string="Overdue",
        compute='_compute_overdue_amount',
        help="Residual amount of the posted receivable entries already due.",
    )
    overdue_invoice_count = fields.Integer(
        string="Overdue Invoices",
        compute='_compute_overdue_amount',
    )

    def _compute_overdue_amount(self):
        today = fields.Date.context_today(self)
        for partner in self:
            lines = self.env['account.move.line'].search([
                ('partner_id', '=', partner.id),
                ('parent_state', '=', 'posted'),
                ('account_type', '=', 'asset_receivable'),
                ('date_maturity', '<', today),
                ('amount_residual', '!=', 0),
            ])
            partner.overdue_amount = sum(lines.mapped('amount_residual'))
            partner.overdue_invoice_count = len(lines.mapped('move_id'))

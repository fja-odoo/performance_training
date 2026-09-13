from odoo import models


class PosSession(models.Model):
    """Exercise 5 -- closing a point of sale session.

    Before the cashier can close, the closing popup shows the "sold products
    of the day" summary. A quiet shop closes instantly; the airport shop with
    thousands of orders takes minutes -- and the database is barely working
    during that time.
    """
    _inherit = 'pos.session'

    def get_closing_product_summary(self):
        """Return [(product name, qty sold, subtotal)] sorted by product name."""
        self.ensure_one()
        orders = self.order_ids
        products = orders.mapped('lines').mapped('product_id')

        summary = []
        for product in products:
            qty = 0.0
            subtotal = 0.0
            for order in orders:
                for line in order.lines:
                    if line.product_id == product:
                        qty += line.qty
                        subtotal += line.price_subtotal_incl
            summary.append((product.display_name, qty, subtotal))

        return sorted(summary, key=lambda row: row[0])

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        data['product_summary'] = self.get_closing_product_summary()
        return data

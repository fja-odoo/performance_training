from odoo import api, fields, models


class SaleOrder(models.Model):
    """Exercise 1 -- the customer portal "track my order" search box.

    A customer types (part of) the reference printed on their order
    confirmation e-mail; the portal looks the order up and renders a small
    summary. It is fast on a demo database and falls apart on a real one.
    """
    _inherit = 'sale.order'

    customer_reference = fields.Char(
        string="Portal Reference",
        copy=False,
        help="Reference communicated to the customer, searchable from the portal.",
    )

    @api.model
    def portal_find_by_reference(self, reference, limit=10):
        """Find the customer's order from whatever they typed in the box.

        Customers never remember which of the three references they were
        given, and support kept forwarding "I pasted my PO number and it
        found nothing", so the box now searches all of them -- including
        the free-text note, where the delivery instructions and the odd
        hand-written reference end up.

        Called on every keystroke of the portal search box (debounced at
        300ms client side).
        """
        orders = self.search([
            '|', '|',
            ('customer_reference', 'ilike', reference),
            ('client_order_ref', 'ilike', reference),
            ('note', 'ilike', reference),
        ], limit=limit)
        return [{
            'id': order.id,
            'name': order.name,
            'customer_reference': order.customer_reference,
            'amount_total': order.amount_total,
            'state': order.state,
        } for order in orders]

    @api.model
    def portal_recent_orders(self, offset=0, limit=80):
        """Paginated "my orders" list, sorted by customer reference."""
        return self.search_read(
            domain=[('state', 'in', ('sale', 'done'))],
            fields=['name', 'customer_reference', 'date_order', 'amount_total'],
            order='customer_reference asc, id desc',
            offset=offset,
            limit=limit,
        )

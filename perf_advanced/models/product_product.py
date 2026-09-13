from odoo import api, models


class ProductProduct(models.Model):
    """Exercise 2 -- the barcode scanner of the warehouse.

    The mobile client scans a barcode and needs, for a single product:
      * the product identity,
      * where the goods are and how many, shelf by shelf,
      * the last moves of that product.

    The client does one RPC per piece of information, and the server answers
    each of them the naive way.
    """
    _inherit = 'product.product'

    @api.model
    def scanner_identify(self, barcode):
        """Step 1 of the scan: resolve a barcode into a product."""
        product = self.search([('barcode', '=', barcode)], limit=1)
        if not product:
            return False
        return {'id': product.id, 'display_name': product.display_name}

    @api.model
    def scanner_stock_per_location(self, product_id, location_id):
        """Step 2 of the scan: where is it, and how many on each shelf?

        The operator needs the breakdown, not the total: they have to walk to
        the right shelf.
        """
        locations = self.env['stock.location'].search([
            ('id', 'child_of', location_id),
            ('usage', '=', 'internal'),
        ])
        breakdown = []
        for location in locations:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product_id),
                ('location_id', '=', location.id),
            ])
            available = sum(quant.quantity - quant.reserved_quantity for quant in quants)
            if available:
                breakdown.append({
                    'location_id': location.id,
                    'location': location.complete_name,
                    'available_qty': available,
                })
        return breakdown

    @api.model
    def scanner_last_moves(self, product_id, limit=5):
        """Step 3 of the scan: the last moves, for the operator to double check."""
        moves = self.env['stock.move'].search(
            [('product_id', '=', product_id)],
            order='date desc, id desc',
            limit=limit,
        )
        return [{
            'id': move.id,
            'date': move.date,
            'quantity': move.product_uom_qty,
            'reference': move.reference,
            'location': move.location_id.complete_name,
            'location_dest': move.location_dest_id.complete_name,
        } for move in moves]

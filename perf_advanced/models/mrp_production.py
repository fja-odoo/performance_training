from odoo import models


class MrpProduction(models.Model):
    """Exercise 3 -- confirming a manufacturing order.

    On confirmation the shop floor wants a component availability report
    posted on the MO chatter, so that the operator knows what is missing
    before walking to the picking area.
    """
    _inherit = 'mrp.production'

    def action_confirm(self):
        res = super().action_confirm()
        for production in self:
            production._post_component_availability()
        return res

    def _post_component_availability(self):
        self.ensure_one()
        lines = []
        for move in self.move_raw_ids:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', move.product_id.id),
                ('location_id', 'child_of', self.location_src_id.id),
            ])
            on_hand = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
            reference_uom = self.env.ref('uom.product_uom_unit')
            needed = move.uom_id._compute_quantity(move.product_uom_qty, reference_uom)
            status = "OK" if on_hand >= needed else "MISSING"
            lines.append(
                f"<li>{move.product_id.display_name}: "
                f"needed {needed:.2f}, on hand {on_hand:.2f} [{status}]</li>"
            )
            self.message_post(
                body=f"Component check: {move.product_id.display_name} -> {status}",
            )
        self.message_post(body=f"<p>Component availability</p><ul>{''.join(lines)}</ul>")

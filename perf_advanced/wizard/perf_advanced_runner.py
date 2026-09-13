import logging
import time

from odoo import fields, models

_logger = logging.getLogger(__name__)


class PerfAdvancedRunner(models.TransientModel):
    """Single entry point to replay the three "single flow" exercises.

    Open it from Performance Advanced > Run a flow, start the profiler
    (developer tools > Enable profiling), then press a button. The whole
    flow ends up in one ir.profile record you can open in speedscope.

    For the headless variant, wrap the same flows in a Profiler in
    `odoo-bin shell` -- see the speedscope section of EXERCISES.md.
    """
    _name = 'perf.advanced.runner'
    _description = "Performance Advanced - Flow Runner"

    mo_count = fields.Integer("Manufacturing orders to confirm", default=1)
    partner_count = fields.Integer("Partners to read", default=80)
    result = fields.Text("Result", readonly=True)

    def _reopen(self, label, duration, detail=''):
        self.result = f"{label}: {duration:.2f}s {detail}"
        _logger.info("[perf_advanced] %s", self.result)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_run_exercise_3(self):
        """Confirm draft manufacturing orders (component availability report)."""
        self.ensure_one()
        productions = self.env['mrp.production'].search(
            [('state', '=', 'draft')], limit=max(self.mo_count, 1))
        if not productions:
            return self._reopen("Exercise 3", 0, "-- no draft MO found, run the populate first")
        start = time.time()
        productions.action_confirm()
        return self._reopen(
            "Exercise 3", time.time() - start,
            f"({len(productions)} MO, {len(productions.move_raw_ids)} components)")

    def action_run_exercise_4(self):
        """Read the overdue column for one page of customers."""
        self.ensure_one()
        partners = self.env['res.partner'].search(
            [('customer_rank', '>', 0)], limit=max(self.partner_count, 1))
        if not partners:
            partners = self.env['res.partner'].search([], limit=max(self.partner_count, 1))
        start = time.time()
        partners.invalidate_recordset(['overdue_amount', 'overdue_invoice_count'])
        values = partners.read(['display_name', 'overdue_amount', 'overdue_invoice_count'])
        return self._reopen(
            "Exercise 4", time.time() - start,
            f"({len(values)} partners, total overdue "
            f"{sum(v['overdue_amount'] for v in values):.2f})")

    def action_run_exercise_5(self):
        """Build the closing summary of the busiest POS session."""
        self.ensure_one()
        session = self.env['pos.session'].search(
            [('order_ids', '!=', False)], order='id desc', limit=1)
        if not session:
            return self._reopen("Exercise 5", 0, "-- no POS session found, run the populate first")
        start = time.time()
        summary = session.get_closing_product_summary()
        return self._reopen(
            "Exercise 5", time.time() - start,
            f"(session {session.name}, {len(session.order_ids)} orders, "
            f"{len(summary)} products)")

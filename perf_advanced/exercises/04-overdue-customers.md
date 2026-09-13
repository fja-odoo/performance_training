[← All exercises](../EXERCISES.md) · [← Manufacturing order](03-manufacturing-order.md) · [POS session closing →](05-pos-closing.md)

# Exercise 4 — the overdue customers list

**Flame graph, then EXPLAIN, then an index.**

> The credit controller opens *Overdue Customers* every morning. 80 customers
> per page, and it has been getting slower every month since the company
> started invoicing seriously. Sorting a column means waiting again. The list
> only shows a name, a count and an amount.

The computed field is in `models/res_partner.py`.

## Data

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex4_overdue -j auto
```

A chart of accounts must be installed on the company first (see README) —
without it there is no sale journal and the blueprint cannot create invoices.

This is the slowest of the five blueprints — around **3 minutes** — and most of
that is Odoo posting 11.000 invoices one at a time. It has to be serial: the
invoice sequence locks, and parallel posting deadlocks. The counts are the
smallest that still reproduce the plan this exercise is about (~10.000 overdue
receivable lines); raise them with `--scale` if you want it worse.

*(Reference measurements below come from the default run: 11.026 posted
invoices, 41.026 journal items, 10.866 of them overdue receivables.)*

## Your job

1. **Record the flow** — *Performance Advanced > Overdue Customers* in the UI
   with profiling on, or the `Profiler` recipe from
   [EXERCISES.md](../EXERCISES.md) around one page of the list:

   ```python
   partners = env['res.partner'].search([('customer_rank', '>', 0)], limit=80)
   partners.invalidate_recordset(['overdue_amount', 'overdue_invoice_count'])
   partners.read(['display_name', 'overdue_amount', 'overdue_invoice_count'])
   ```

   The `invalidate_recordset` matters: without it a second run reads the
   compute straight out of the ORM cache and measures nothing.

2. **In the flame graph**: how many times is the `search` inside
   `_compute_overdue_amount` entered, and how many queries does one page cost?

3. **Take one of those queries and EXPLAIN it.** Pick the partner with the most
   journal items to make the numbers visible:

   ```sql
   SELECT partner_id FROM account_move_line
    WHERE partner_id IS NOT NULL GROUP BY partner_id ORDER BY count(*) DESC LIMIT 1;
   ```

   * There is a `JOIN` on `account_account` that you did not write. Where does
     it come from? (look at how `account_type` is defined on
     `account.move.line`)
   * Which part of the `WHERE` ends up as an `Index Cond`, and which part is
     only applied afterwards? Count the rows read against the rows returned,
     then multiply by the 80 partners of the page.

4. **Rewrite the compute**, then EXPLAIN the *one* query it now produces.
   Is it fast enough? If not, what index would you add, and why a **partial**
   one?

5. Bonus: the controller wants to *sort* on the overdue column. What does that
   imply for a non-stored computed field, and what are the options?

<details>
<summary><b>Answer — exercise 4</b></summary>

### The flame graph

`_compute_overdue_amount` is entered once, but the `search` inside it runs 80
times — one per partner of the page. **173 queries for one page**, almost all of
the time in SQL. This is the canonical "compute that queries per record": the
ORM hands you a *recordset* in `self` precisely so you can batch, and the code
iterates instead.

### The join you did not write

```python
('account_type', '=', 'asset_receivable')
```

`account_type` on `account.move.line` is
`fields.Selection(related='account_id.account_type')`, **not stored**. Searching
on it makes the ORM join `account_account`. The plan for one partner:

```
Sort (actual time=0.414..0.414 rows=9 loops=1)
  ->  Nested Loop
        ->  Bitmap Heap Scan on account_move_line l (actual rows=9 loops=1)
              ->  Bitmap Index Scan on account_move_line_partner_id_ref_idx
                    Index Cond: (partner_id = 1202)       -- 50 rows
        ->  Materialize
              ->  Seq Scan on account_account a
                    Filter: (account_type = 'asset_receivable')
  Buffers: shared hit=59
  Execution Time: 0.480 ms
```

Only `partner_id` is usable as an index condition. `parent_state`,
`date_maturity` and `amount_residual` are all applied *after* the index, and the
account type costs a join on top. 50 rows read to return 9 — and PostgreSQL does
that 80 times per page.

> **Your plan will not be identical to this one.** Plans depend on the volume
> and on the statistics: with more overdue lines PostgreSQL starts combining
> the `partner_id` and `date_maturity` indexes in a `BitmapAnd`, reading
> thousands of index entries to return a handful of rows. Read *your* plan and
> reason about it — the shape (one usable index condition, everything else
> filtered afterwards, times 80) is what stays true.

### The fix, step 1 — batch

```python
def _compute_overdue_amount(self):
    today = fields.Date.context_today(self)
    self.overdue_amount = 0.0
    self.overdue_invoice_count = 0

    groups = self.env['account.move.line']._read_group(
        [
            ('partner_id', 'in', self.ids),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('date_maturity', '<', today),
            ('amount_residual', '!=', 0),
        ],
        ['partner_id'],
        ['amount_residual:sum', 'move_id:count_distinct'],
    )
    for partner, amount, invoice_count in groups:
        partner.overdue_amount = amount
        partner.overdue_invoice_count = invoice_count
```

Three things:

* **one** query for the 80 partners instead of 80;
* the sum and the distinct count are done by PostgreSQL, not by
  `sum(lines.mapped(...))` and `len(lines.mapped('move_id'))` — the original
  fetched every line *and* every `move_id` just to count them;
* `self.overdue_amount = 0.0` on the whole recordset first: a compute **must**
  assign every record of `self`, and partners without overdue lines are absent
  from the groups.

Writing `('account_id.account_type', '=', …)` instead of `('account_type', …)`
produces the same join, written explicitly. Keep it explicit so the next reader
sees the cost.

Verified: identical totals to the shipped version, and the page drops from
0.14 s / 173 queries to a single query below measurement resolution on this
dataset. For most instances, stop here.

### The fix, step 2 — the index, if the volume justifies it

The selective part of the domain is *"posted, still open, already due"*, a small
fraction of a very large table:

```sql
SELECT count(*) AS lines,
       count(*) FILTER (WHERE parent_state = 'posted' AND amount_residual <> 0) AS open_lines
  FROM account_move_line;
```

If `open_lines` is a few percent of `lines`, a **partial** index pays for
itself: it indexes only the rows that can ever match, so it is small, stays in
cache, and does not slow down writes on the rows it excludes.

```python
from odoo import models, tools

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def init(self):
        super().init()
        tools.create_index(
            self.env.cr,
            'account_move_line_overdue_idx',
            self._table,
            ['partner_id', 'date_maturity'],
            where="parent_state = 'posted' AND amount_residual != 0 AND partner_id IS NOT NULL",
        )
```

Same query, same data, with the index:

```
  ->  Bitmap Heap Scan on account_move_line l (actual rows=9 loops=1)
        ->  Bitmap Index Scan on account_move_line_overdue_idx (actual rows=9 loops=1)
              Index Cond: ((partner_id = 1202) AND (date_maturity < CURRENT_DATE))
  Buffers: shared hit=12 read=2
  Execution Time: 0.131 ms
```

**59 blocks → 14, 0.48 ms → 0.13 ms**, and the index now returns exactly the 9
rows that matter instead of 50 candidates to be filtered.

Careful with partial indexes: PostgreSQL only uses one when it can *prove* the
query implies the `WHERE` of the index. The domain must contain
`('parent_state', '=', 'posted')` and `('amount_residual', '!=', 0)` literally.
Drop one of them in a later refactor and the index silently stops being used —
exactly the kind of regression to check with `EXPLAIN`.

### Bonus — sorting on the column

A non-stored computed field cannot be sorted by the database: the ORM would have
to compute it for *every* partner, not just the page, and then sort in Python.
Three options, in order of preference:

1. **Do not sort on it.** Filter instead (`overdue_amount > 0` through a
   `search=` method), and sort on something stored.
2. **`search='_search_overdue_amount'`** — lets the domain be pushed down to SQL
   for filtering, still not for ordering.
3. **Store it** (`store=True` + `@api.depends`) — then it is indexable and
   sortable, at the price of a recompute on every payment and every invoice
   posting. And the "already due" part *depends on today's date*, which cannot
   be expressed with `@api.depends` at all: you would need a nightly cron, and a
   stale stored field is worse than a slow one. That last point is usually what
   kills the idea.

</details>


---

[← All exercises](../EXERCISES.md) · [← Manufacturing order](03-manufacturing-order.md) · [POS session closing →](05-pos-closing.md)

The toolbox (pgBadger, speedscope, EXPLAIN) and the setup instructions are in [EXERCISES.md](../EXERCISES.md) and [README.md](../README.md).

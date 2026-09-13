[← All exercises](../EXERCISES.md) · [← Overdue customers](04-overdue-customers.md)

# Exercise 5 — closing the point of sale

**A flame graph with almost no SQL in it.**

> The airport shop closes at midnight. The cashier hits *Close Session*, the
> closing popup spins for over a minute, and the shop cannot close its till.
> The DBA swears the database is idle — and this time the graphs agree:
> PostgreSQL is at 2 % CPU during the whole thing, one Odoo worker is pinned
> at 100 %.

The code is in `models/pos_session.py`: `get_closing_product_summary`.

## Data

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex5_pos_closing
```

One session, 8.000 orders, 60.000 lines, 800 distinct products.

## Your job

1. **Record the flow** — *Performance Advanced > Run a flow* in the UI with
   profiling on, or the `Profiler` recipe from
   [EXERCISES.md](../EXERCISES.md) around:

   ```python
   session = env['pos.session'].search([('order_ids', '!=', False)], order='id desc', limit=1)
   session.get_closing_product_summary()
   ```

2. **Left Heavy.** The SQL band is tiny and the Python band fills the graph.
   * How many queries does the flow make? Is the database the problem?
   * Which frames are at the top of the flame graph? What are they doing?
   * Write down the complexity of the method as a function of *P* (products),
     *O* (orders) and *L* (lines per order). Plug in the real numbers.
   * `line.product_id == product` looks innocent. What does it cost, and why
     does it show up in the profile?

3. **Rewrite it.** Two versions, and measure both:
   * one that keeps the data in Python but makes a single pass;
   * one that lets PostgreSQL do the grouping.

   Which one wins, and is the difference worth the reduced readability?

<details>
<summary><b>Answer — exercise 5</b></summary>

### What the flame graph shows

**67 seconds of wall time. 28 queries.** A few hundred milliseconds of SQL,
everything else Python, and the top frames are `BaseModel.__eq__`,
`BaseModel.__iter__` and `__getitem__`: the ORM machinery that turns
`order.lines` into records, over and over.

### The complexity

```python
for product in products:            # P  = 800
    for order in orders:            # O  = 8.000
        for line in order.lines:    # L  = 7.5 on average
            if line.product_id == product:
```

`P × O × L` = 800 × 8.000 × 7.5 = **48 million** iterations, each doing a
recordset comparison. And `line.product_id` *materialises a recordset* every
time: an object allocation, a prefetch-set lookup, then `__eq__` comparing ids.
That is why ORM frames are at the top of the graph — the algorithm is not doing
arithmetic, it is doing object churn.

The database is idle because the data was already fetched, correctly, in a
handful of queries. **Not every performance problem is a query problem**, and
this is the exercise that proves it.

### Version 1 — single pass, still in Python

```python
from collections import defaultdict

def get_closing_product_summary(self):
    self.ensure_one()
    totals = defaultdict(lambda: [0.0, 0.0])
    for line in self.order_ids.lines:
        total = totals[line.product_id.id]
        total[0] += line.qty
        total[1] += line.price_subtotal_incl

    products = self.env['product.product'].browse(totals)
    return sorted(
        ((product.display_name, *totals[product.id]) for product in products),
        key=lambda row: row[0],
    )
```

`P × O × L` becomes `O × L` — 60.000 iterations instead of 48 million, a single
pass over the lines. `self.order_ids.lines` reads all the lines of all the
orders in one query, and `browse(totals)` builds one recordset out of the
collected ids so `display_name` is computed for the 800 products in one
prefetched batch.

### Version 2 — let PostgreSQL group

```python
def get_closing_product_summary(self):
    self.ensure_one()
    groups = self.env['pos.order.line']._read_group(
        [('order_id.session_id', '=', self.id)],
        ['product_id'],
        ['qty:sum', 'price_subtotal_incl:sum'],
    )
    return sorted(
        ((product.display_name, qty, subtotal) for product, qty, subtotal in groups),
        key=lambda row: row[0],
    )
```

One `GROUP BY` query returning 800 rows. The 60.000 lines never leave
PostgreSQL, so there is no ORM cache to fill and no Python loop at all.

### Measured

| | wall time |
|---|---|
| shipped | **67.2 s** |
| version 1, single pass in Python | **0.67 s** |
| version 2, `_read_group` | **0.045 s** |

Both versions return exactly the same rows as the shipped one (same products,
same quantities, same subtotals — check it, do not assume it).

Version 2 wins by a factor 15 over version 1, and it is also the shorter code.
The rule of thumb: **if you are looping to aggregate, the database can do it for
you**. Keep a Python pass only when the aggregation cannot be expressed in SQL —
a rule depending on something that is not in the table, a currency conversion
per line, a `filtered` on a non-stored field.

One detail worth knowing: `_read_group` returns the `product_id` groups as a
recordset with a correct prefetch set, so `product.display_name` in the
comprehension costs **one** query for all 800 products, not 800.

### The lesson

Three profiles, three different shapes:

| Exercise | SQL band | Python band | Diagnosis |
|----------|----------|-------------|-----------|
| 3 | wide, repeated | thin | N+1 queries → batch them |
| 4 | wide, repeated | thin | compute per record → `_read_group` |
| 5 | thin | wide | wrong algorithm → fix the loop |

Look at the *ratio* first. It tells you which of the three books to open.

</details>


---

[← All exercises](../EXERCISES.md) · [← Overdue customers](04-overdue-customers.md)

The toolbox (pgBadger, speedscope, EXPLAIN) and the setup instructions are in [EXERCISES.md](../EXERCISES.md) and [README.md](../README.md).

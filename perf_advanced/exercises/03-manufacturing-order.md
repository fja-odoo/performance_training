[← All exercises](../EXERCISES.md) · [← Barcode scanner](02-barcode-scanner.md) · [Overdue customers →](04-overdue-customers.md)

# Exercise 3 — confirming the manufacturing orders of the week

**One flow, one flame graph.**

> Production planning confirms the manufacturing orders of the week every
> Monday morning: twenty MOs, selected in the list, *Confirm*. Since the
> "component availability" report was added to the chatter, that click takes
> a quarter of a minute and the planner has learned to go get a coffee. And
> the chatter of every MO is now unreadable: a hundred notifications nobody
> asked for.

The code is in `models/mrp_production.py`: `action_confirm` →
`_post_component_availability`.

## Data

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex3_manufacturing
```

200 draft manufacturing orders, ~75 components each, 400 products, a few
thousand quants under `WH/Stock`.

## Your job

1. **Record the flow.** Either from the UI (*Performance Advanced > Run a
   flow*, with profiling enabled) or headlessly — take the `Profiler` recipe
   from [EXERCISES.md](../EXERCISES.md) and give it this flow:

   ```python
   env['mrp.production'].search([('state', '=', 'draft')], limit=20).action_confirm()
   ```

   Record `limit=1` as well, and compare: the per-MO cost is the number you
   will quote to the planner, the twenty-MO cost is the one they feel.

2. **Open it in speedscope, switch to Left Heavy.**

3. **Answer:**
   * How much of the wall time is SQL, and how much is Python?
   * Which single function is responsible for most of the queries? How many
     times is it called, and what does that number correspond to in the data?
   * There are **two** independent N+1 in this method. Find both. (One of them
     is not a `search`.)
   * `self.env.ref(...)` sits inside the loop. Is it a problem? Justify with
     the profile, not with intuition.
   * Rewrite `_post_component_availability`. Target: a number of queries that
     does not depend on the number of components.

<details>
<summary><b>Answer — exercise 3</b></summary>

### What the flame graph shows

| | wall time | queries |
|---|---|---|
| 1 MO (48 components), whole `action_confirm` | 0.46 s | ~700 |
| 20 MOs (1.521 components), whole `action_confirm` | 15.4 s | **22.087** |
| the report alone, 20 MOs | 5.8 s | — |

Left Heavy: two wide blocks, `stock.quant.search` and `message_post`, both with
a call count equal to the number of raw moves. Almost everything is SQL.

### N+1 number one — one `search` per component

```python
for move in self.move_raw_ids:
    quants = self.env['stock.quant'].search([
        ('product_id', '=', move.product_id.id),
        ('location_id', 'child_of', self.location_src_id.id),
    ])
    on_hand = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
```

75 components = 75 searches, and each one re-resolves `child_of` — a subquery on
`stock_location.parent_path` computed 75 times for the *same* location. Then
`mapped()` fetches every quant row to sum it in Python, exactly like exercise 2.

### N+1 number two — one `message_post` per component

```python
    self.message_post(body=f"Component check: …")
```

This is the expensive one, and it is not a `search`. Each `message_post`
creates a `mail.message`, resolves the author, computes the recipients, inserts
the notifications and invalidates the chatter cache: a dozen queries **plus** a
noticeable Python cost. Measured on one MO: **49 chatter messages for 48
components**. Business-wise it is also wrong — the operator wants one report,
not 48 lines of noise.

### `env.ref` in the loop

`self.env.ref('uom.product_uom_unit')` resolves an XML id, which is cached in
the registry after the first call. In the profile it is a thin, repeated, cheap
frame. **It is not the problem here** — and that is the point of the question: a
flame graph tells you where the time *is*, which is rarely where intuition
points. Hoist it out of the loop because it is cleaner, not because it buys you
time.

### The fixed version

```python
def _post_component_availability(self):
    self.ensure_one()
    moves = self.move_raw_ids
    reference_uom = self.env.ref('uom.product_uom_unit')

    # ONE query for every component, whatever their number
    quantities = {
        product.id: (quantity or 0.0) - (reserved or 0.0)
        for product, quantity, reserved in self.env['stock.quant']._read_group(
            [
                ('product_id', 'in', moves.product_id.ids),
                ('location_id', 'child_of', self.location_src_id.id),
            ],
            ['product_id'],
            ['quantity:sum', 'reserved_quantity:sum'],
        )
    }

    lines = []
    for move in moves:
        on_hand = quantities.get(move.product_id.id, 0.0)
        needed = move.uom_id._compute_quantity(move.product_uom_qty, reference_uom)
        status = "OK" if on_hand >= needed else "MISSING"
        lines.append(
            f"<li>{move.product_id.display_name}: "
            f"needed {needed:.2f}, on hand {on_hand:.2f} [{status}]</li>"
        )

    # ONE message instead of one per component
    self.message_post(body=f"<p>Component availability</p><ul>{''.join(lines)}</ul>")
```

Note `moves.product_id.ids`: reading a many2one on a whole recordset resolves it
in one query, and it warms the prefetch cache used by
`move.product_id.display_name` in the loop below.

Measured, report only:

| | shipped | fixed |
|---|---|---|
| 1 MO, 48 components | 0.23 s, 49 messages | **0.02 s, 1 message** |
| 20 MOs, 1.521 components | 5.84 s | **0.17 s** |

### And the loop over `self`

```python
def action_confirm(self):
    res = super().action_confirm()
    for production in self:
        production._post_component_availability()
    return res
```

Correct for one MO, but confirming 20 still does 20 × (one `_read_group` + one
`message_post`). If the planner confirms the whole week in one go, push the
batching one level up: a single `_read_group` over `self.move_raw_ids.product_id`
grouped by `raw_material_production_id` and `product_id`, then one
`message_post` per MO. Measure before you write it — at 0.17 s for twenty MOs
you are already done, and `message_post` cannot be batched below one call per
record anyway.

</details>


---

[← All exercises](../EXERCISES.md) · [← Barcode scanner](02-barcode-scanner.md) · [Overdue customers →](04-overdue-customers.md)

The toolbox (pgBadger, speedscope, EXPLAIN) and the setup instructions are in [EXERCISES.md](../EXERCISES.md) and [README.md](../README.md).

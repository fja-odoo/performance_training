[← All exercises](../EXERCISES.md) · [← Customer portal](01-customer-portal.md) · [Manufacturing order →](03-manufacturing-order.md)

# Exercise 2 — the barcode scanner that melts the server

**Load test + pgBadger, without a single slow query.**

> Twelve pickers, one scan every two seconds. That is six scans per second —
> nothing. Yet a scan takes a second and a half, the app throughput tops out at
> three scans per second, and the pickers are queuing at the shelf.
>
> The DBA looked at the slow query log (threshold: 1 second) and says the
> database is fine, nothing is slow. **He is right.** Not one query in the whole
> run takes a millisecond. Both of you are looking at true facts and reaching
> opposite conclusions.

Server side, one scan is three RPCs, in `models/product_product.py`:

```python
product.product.scanner_identify(barcode)
product.product.scanner_stock_per_location(product_id, location_id)
product.product.scanner_last_moves(product_id, limit=5)
```

The middle one gives the operator the breakdown per shelf — they need to know
*where* to walk, not just how many exist somewhere in the building.

## Data

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex2_barcode -j auto
```

One warehouse — the default one — with **2.000 bin locations** directly under
`WH/Stock`, 120 products, 30.000 quants holding real stock and 100.000 moves.
Both `WH` and `WH/Stock` work as the scanner's `location_id`, so there is
nothing to get wrong there.

2.000 bins is an ordinary mid-size distribution centre. It is also the number
that drives this whole exercise — keep it in mind when you find the cause.

The bins do not scale with `--scale`: the warehouse keeps them whatever you
pass, so the exercise bites even on a small dataset.

## Your job

1. **Write the load test.** `tools/locust_ex2_scanner.py`: one task = one
   complete scan, the three calls chained (the second and third need the
   `product_id` returned by the first).

   ```shell
   locust -f tools/locust_ex2_scanner.py --headless -u 12 -r 2 -t 3m
   ```

2. **pgBadger, but look at the other section.** *Most frequent queries*, and
   the *Overall statistics* → total number of queries.

3. **Do not start from the query durations.** They will all be under a
   millisecond and they will tell you nothing. Start from these three numbers,
   in this order:

   | Where | What to read |
   |---|---|
   | locust | median and p95 response time, and **scans/s actually achieved** vs the 6/s you asked for |
   | pgBadger → *Overall statistics* | **total number of queries**, and queries per second |
   | pgBadger → *Most frequent queries* | the one query at the top, and its **count** |

   Divide: total queries ÷ scans performed. That single number is the exercise.

4. **Then answer:**
   * How many SQL queries does **one** scan cost?
   * Which of the three RPCs is responsible for practically all of them?
   * What does that count depend on? It is not the catalog size and it is not
     the amount of stock. Find it, then predict what happens the day the
     warehouse manager racks another aisle.
   * The query at the top of *Most frequent queries* takes 0.007 ms. The method
     that runs it takes 700 ms. Where did the other 699 ms go?
   * Rewrite that method so the query count stops depending on the shape of the
     warehouse. Then **check that it returns exactly the same bins as
     before** — this one has a trap in it.

<details>
<summary><b>Answer — exercise 2</b></summary>

### The shape of the problem

Nothing is slow. Everything is *frequent*. Measured on the reference dataset,
scanning a product held on 123 shelves of a 296-shelf warehouse:

| RPC | queries |
|---|---|
| `scanner_identify` | 4 |
| **`scanner_stock_per_location`** | **2.177** |
| `scanner_last_moves` | 4 |
| **one scan** | **~2.185** |

And what that costs, measured over RPC against a 4-worker server, twelve
scanners with two seconds of think time:

| | 1 picker | 12 pickers, median | 12 pickers, p95 | achieved |
|---|---|---|---|---|
| **shipped** | 700 ms | 1.464 ms | 3.360 ms | **3.0 scans/s** |
| **fixed** | 130 ms | 130 ms | 1.112 ms | 4.5 scans/s |

Six scans per second against the shipped code is **~13.000 queries per second**,
and the server cannot keep up: it delivers three. Not one of those queries
appears in a slow query log, because not one of them is slow.

### The N+1

```python
locations = self.env['stock.location'].search([
    ('id', 'child_of', location_id),
    ('usage', '=', 'internal'),
])
breakdown = []
for location in locations:
    quants = self.env['stock.quant'].search([         # <-- one query per shelf
        ('product_id', '=', product_id),
        ('location_id', '=', location.id),
    ])
    available = sum(quant.quantity - quant.reserved_quantity for quant in quants)
```

1.909 active bins, 1.909 searches, plus the fetches behind `quant.quantity`.
The query count is a function of *the shape of the warehouse*, not of the
answer: a product sitting in one bin costs exactly as much as a product in all
of them. Rack another aisle and every scan in the building gets slower — that
is the answer to "what does the count depend on", and it is neither the catalog
size nor the amount of stock.

The cost is brutally linear, ~0.3 ms per bin. Measured on the same product:

| bins | one call |
|---|---|
| 300 | 111 ms |
| 1.000 | 312 ms |
| 2.000 | 639 ms |
| 4.000 | 955 ms |

### Where the 92.9 ms go

Here is the plan of the query that runs 296 times:

```
Bitmap Heap Scan on stock_quant (actual time=0.003..0.003 rows=0 loops=1)
  ->  BitmapAnd
        ->  Bitmap Index Scan on stock_quant__location_id_index
        ->  Bitmap Index Scan on stock_quant__product_id_index (never executed)
  Execution Time: 0.007 ms
```

1.909 × 0.007 ms ≈ **13 ms of SQL**. The database is doing essentially nothing;
`pg_stat` will look bored and the DBA will keep telling you the database is
fine. The other ~690 ms is Odoo: building a domain, going through `ir.rule`,
allocating a recordset, a round trip on the socket — ~0.35 ms of framework per
query, repeated 1.909 times.

This is why "the queries are fast" and "the app is slow" are both true at once,
and why a slow query log can never close this case.

That is the lesson of this exercise, and it is why `EXPLAIN` alone would never
have found it. **A query that is free is not free to call.** When you count
queries, the count *is* the metric; the duration of each one is a detail.

### The fix

```python
@api.model
def scanner_stock_per_location(self, product_id, location_id):
    groups = self.env['stock.quant']._read_group(
        [
            ('product_id', '=', product_id),
            ('location_id', 'child_of', location_id),
            ('location_id.usage', '=', 'internal'),
            ('location_id.active', '=', True),
        ],
        ['location_id'],
        ['quantity:sum', 'reserved_quantity:sum'],
    )
    return [{
        'location_id': location.id,
        'location': location.complete_name,
        'available_qty': (quantity or 0.0) - (reserved or 0.0),
    } for location, quantity, reserved in groups if (quantity or 0.0) - (reserved or 0.0)]
```

| | queries | one call (cold) |
|---|---|---|
| shipped | 2.177 | 3.247 ms |
| `_read_group` | **3** | **14 ms** |

**230× faster, 725× fewer queries**, and the cost now depends on how many bins
actually hold the product, not on how big the warehouse is. Rack all the aisles
you like.

### The trap

Write that `_read_group` the obvious way — without `('location_id.active', '=',
True)` — and it returns **274** bins where the original returned **264**. It is
faster *and* wrong, and nothing tells you.

The reason: `search()` applies `active_test` and silently skips archived
records, so the original loop never visited the 98 decommissioned bins (5 % of
the warehouse, and 10 of them still hold this product). Traversing
`location_id.usage` inside a domain is a plain SQL join, with no `active_test`
on the joined table. The archived shelves come back.

So: **when you replace a loop by an aggregate, diff the two results before you
delete the old code.** On this dataset the difference is 10 rows out of 264 — in
production it is a stock report that quietly disagrees with the one people
trusted last month.

### And the third RPC, for later

`scanner_last_moves` is only 4 queries, but look at its plan:

```
Limit (actual time=0.366..0.367 rows=5 loops=1)
  ->  Incremental Sort
        Sort Key: date DESC, id DESC
        ->  Index Scan Backward using stock_move__date_index on stock_move
              Filter: (product_id = 36)
              Rows Removed by Filter: 322
        Buffers: shared hit=88
```

`product_id` and `date` each have their own index, but PostgreSQL can only use
*one* of them for both the filter and the ordering. It walks the table backwards
by date, discarding 5.954 moves belonging to other products, to find 5. A
composite index turns it into a scan that stops after 5 rows:

```python
from odoo import models, tools

class StockMove(models.Model):
    _inherit = 'stock.move'

    def init(self):
        super().init()
        tools.create_index(
            self.env.cr,
            'stock_move_product_date_idx',
            self._table,
            ['product_id', 'date DESC', 'id DESC'],
        )
```

```
Limit (actual time=0.015..0.016 rows=5 loops=1)
  ->  Index Only Scan using stock_move_product_date_idx on stock_move
        Index Cond: (product_id = 36)
        Heap Fetches: 0
        Buffers: shared hit=1 read=3
```

**88 blocks → 4, 0.376 ms → 0.025 ms.** Note how modest that is in absolute
terms: at 100.000 moves this index is invisible end to end. It also depends
entirely on *which* product you scan — `Rows Removed by Filter` is roughly "how
far back you must walk before this product's five most recent moves appear", so
a product nobody has touched in a year costs far more than the 322 rows above.
Try a few and watch the number move.

That is the point: at ten million moves, and for the unlucky products, this is
the whole scan. You find it with `EXPLAIN`, never with a stopwatch — the exact
opposite of the N+1 above, and why you need both tools.

### Bonus — the three round trips

Even fixed, one scan is three HTTP requests. Measured over
`/web/dataset/call_kw`, a request that calls only `scanner_identify` costs **54
queries** — session, user, `ir.rule`, access rights, transaction. That fixed
toll is paid three times per scan. Merging the three RPCs into one
`scanner_scan(barcode, location_id)` removes two of them. It is worth doing, but
notice the order of magnitude: the N+1 above was worth 400 queries per scan and
this is worth about 100. **Fix the loop first.**

</details>


---

[← All exercises](../EXERCISES.md) · [← Customer portal](01-customer-portal.md) · [Manufacturing order →](03-manufacturing-order.md)

The toolbox (pgBadger, speedscope, EXPLAIN) and the setup instructions are in [EXERCISES.md](../EXERCISES.md) and [README.md](../README.md).

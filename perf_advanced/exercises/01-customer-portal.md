[← All exercises](../EXERCISES.md) · [Barcode scanner →](02-barcode-scanner.md)

# Exercise 1 — the customer portal at 9 a.m.

**Load test + pgBadger + EXPLAIN.**

> A marketing e-mail went out this morning with a *track my order* link.
> Since then the whole instance is slow — not only the portal, *everything*.
> The customer service cannot open a quotation any more. Nothing was deployed
> yesterday.
>
> The portal search itself takes **one and a half seconds**, and when a customer
> mistypes their reference it takes **three**.

The portal calls two methods, both in `models/sale_order.py`:

* `portal_find_by_reference(reference)` — the search box, one call per ~300 ms
  of typing. Customers never remember which of their three references they were
  given, so the box searches the customer reference, the PO number **and the
  free-text note**;
* `portal_recent_orders(offset, limit)` — the paginated list of the customer's
  orders, sorted by the customer reference.

## Data

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex1_portal -j auto
```

150.000 sale orders with a unique `customer_reference` and a realistic ~3.9 kB
delivery note. Around 3 minutes; the table lands at ~300 MB.

## Your job

1. **Write the load test.** `tools/locust_ex1_portal.py` has the scenario and
   the weights; the tasks are `NotImplementedError`. Fill them in.

   ```shell
   locust -f tools/locust_ex1_portal.py --headless -u 20 -r 2 -t 3m
   ```

2. **Collect the evidence.** Turn the PostgreSQL logging on *before* the run,
   build the pgBadger report after it.

3. **Answer with numbers:**
   * Which query spends the most time in total? How many calls, what mean
     duration?
   * `EXPLAIN (ANALYZE, BUFFERS)` it. Take the statement from the pgBadger
     report, or wrap `portal_find_by_reference` in the `Profiler` recipe from
     [EXERCISES.md](../EXERCISES.md) — `json.loads(profile.sql)` gives you the
     exact SQL Odoo sent, parameters and all.
   * Run that `EXPLAIN` twice: once with the `note` in the `OR`, once without
     it. Do not guess which half the time is in.
   * Time the search for 2, 4, 5 and 10 characters typed. The numbers are not
     monotonic. Explain the shape before reading on.
   * The table is 300 MB. Pad every row to four times its size *without*
     touching the note and the scan time barely moves; make the note four times
     longer and it triples. What does that tell you about what a sequential
     scan actually costs?
   * The instance was slow *for everybody*, not only for the portal users. Why
     does one sequential scan on one table do that?
   * Fix it. Then re-measure at 2, 4, 5 and 10 characters — the fix does not
     work everywhere, and finding where it fails is the point of the exercise.

<details>
<summary><b>Answer — exercise 1</b></summary>

### What the report shows

`portal_find_by_reference` produces, per keystroke, one query:

```sql
SELECT "sale_order"."id" FROM "sale_order"
 WHERE ("sale_order"."client_order_ref" ILIKE '%CR-1234%'
     OR "sale_order"."customer_reference" ILIKE '%CR-1234%'
     OR "sale_order"."note" ILIKE '%CR-1234%')
 ORDER BY "sale_order"."date_order" DESC, "sale_order"."id" DESC
 LIMIT 10;
```

Measured on the reference dataset, through the ORM:

| the customer has typed | search |
|---|---|
| 2 characters | 31 ms |
| 4 characters | **3.135 ms** |
| 5 characters | **3.138 ms** |
| 8 characters of a real reference | **1.419 ms** |
| a full reference | **1.459 ms** |

### Why a sequential scan is expensive

Not because the table is big in megabytes. This is worth proving to yourself:

| table | scan |
|---|---|
| 20.000 orders, 11 MB | 10.7 ms |
| the same 20.000 orders padded to 43 MB | 12.0 ms |
| 20.000 orders with a 1.5 kB note in the search | **150 ms** |

Four times the pages costs 12 % more. Four times the *text to match* costs nine
times more. A sequential scan costs **rows × per-row work**, and here the
per-row work is an `ILIKE` over a 3.9 kB note.

The cleanest proof is to run the same filter twice on the same 150.000 rows,
once with the note and once without:

| filter | scan |
|---|---|
| `client_order_ref OR customer_reference OR note` | 1.344 ms |
| `client_order_ref OR customer_reference` | **72 ms** |

**The note is 95 % of the cost.** Adding it to the search box was the single
decision that turned a 70 ms search into a 1.5 second one.

### Why the *whole instance* got slow

That is the important half. Every keystroke of every customer pushes the entire
`sale_order` table — 300 MB — through `shared_buffers`. It evicts everything
else: the `res_partner` pages the customer service needs, the `ir_ui_view` rows,
the indexes of unrelated tables. Every other query on the instance starts
reading from disk. One missing index on one hot path degrades the cache for
every user of that PostgreSQL cluster.

### The fix, and where it stops working

`ILIKE '%…%'` cannot use a btree index — a btree is ordered by the *beginning*
of the value. You need trigram GIN indexes, on **every** column the box
searches:

```python
customer_reference = fields.Char(string="Portal Reference", copy=False, index='trigram')
client_order_ref = fields.Char(index='trigram')
note = fields.Html(index='trigram')
```

with `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in the database, then
`odoo-bin -d perf_advanced -u perf_advanced`.

With five or more characters typed, the plan becomes exactly what you wanted:

```
Limit (actual time=0.053..0.053 rows=0 loops=1)
  ->  Bitmap Heap Scan on sale_order
        ->  BitmapOr
              ->  Bitmap Index Scan on sale_order_client_order_ref_index
              ->  Bitmap Index Scan on sale_order_customer_reference_index
              ->  Bitmap Index Scan on sale_order_note_index
  Execution Time: 0.164 ms
```

**1.459 ms → 0.26 ms.** And then you re-measure at four characters and get
**3.120 ms** — exactly what you had before the index.

### Why, and what to actually do about it

Two things conspire, and both are worth knowing:

1. **Trigrams are three characters.** `%ZZQ90%` yields three usable trigrams,
   `%ZZQ9%` only two. The fewer trigrams, the more rows PostgreSQL estimates
   the index would return, and the less attractive it looks. Odoo itself will
   not even send a trigram prefilter below 3 characters.
2. **`ORDER BY date_order DESC LIMIT 10` offers the planner an escape.** It can
   walk the `date_order` index backwards and stop as soon as it has 10 matching
   rows — which looks cheap, and *is* cheap when many rows match. That is why
   two characters takes 31 ms: it finds its 10 rows almost immediately. When
   nothing matches, the same plan walks all 150.000 rows and filters every one
   of them. The best case and the worst case of that plan differ by a factor of
   a hundred, and the planner cannot tell them apart.

So the complete fix is not only the index:

* **index every searched column** (above);
* **do not search before 5 characters**, client side. Every real search box
  does this, and now you can justify the number instead of guessing it;
* **reconsider searching the note at all.** The GIN index on a 3.9 kB text
  column is **110 MB** and takes **31 seconds** to build, and it has to be
  maintained on every write. If the note is not really where references live,
  dropping it from the domain takes the search to 0.06 ms with two small
  indexes and no maintenance cost.

Splitting the `OR` into one search per column, by the way, does **not** help:
each individual search meets the same planner choice, and four characters still
costs 3 seconds. Measure it before you believe me.

> **Your numbers will differ, and your plans may too.** Plan choices here depend
> on the volume, on the statistics, and on how many parallel workers your
> PostgreSQL will give a 300 MB scan. What is stable is the shape: a flat
> multi-second cost with no index, a sub-millisecond bitmap when the pattern is
> long enough, and a cliff between them.

### The second query

```sql
ORDER BY customer_reference ASC, id DESC LIMIT 80 OFFSET 4000
```

A trigram index does **not** help an `ORDER BY`: GIN indexes are unordered. And
`OFFSET 4000` makes PostgreSQL produce and throw away 4.000 rows — the cost
grows with the page number. Two independent fixes:

* sort the portal list by something cheap — `id desc` is free (primary key),
  `date_order desc` needs its own index (it has none in standard Odoo);
* replace the offset pagination by a keyset ("seek") pagination: remember the
  last reference of the page and search
  `[('customer_reference', '>', last_seen)]` with `limit=80`. Constant cost on
  page 1 and on page 1000.

</details>


---

[← All exercises](../EXERCISES.md) · [Barcode scanner →](02-barcode-scanner.md)

The toolbox (pgBadger, speedscope, EXPLAIN) and the setup instructions are in [EXERCISES.md](../EXERCISES.md) and [README.md](../README.md).

# perf_advanced — exercises

Five exercises, roughly 45 minutes each. The module ships the **slow**
implementation of every flow; your job is to measure first, then fix.

Each exercise is a separate file, listed below. Every one ends with its answer
in a collapsed block — opening it before you have a number on the table is the
only way to get this training wrong.

Setup (database, populate, tooling): see [README.md](README.md).

> **About the numbers in the answers.** Every figure in these exercises was
> measured on the reference dataset described in each one, on one laptop, with a
> warm cache. Yours will differ — what must match is the *shape*: the ratios, the
> query counts, and the plan nodes. A production instance with ten times the
> data and a cold cache turns these milliseconds into seconds.

---

## The toolbox in three minutes

### pgBadger — "the whole system was slow"

Aggregates PostgreSQL logs over a period. Answers *which query cost the cluster
the most time*, not *why one click was slow*.

Set this up once, in `postgresql.conf`:

```ini
logging_collector = on
log_directory = '/var/log/postgresql'
log_file_mode = 0777
log_rotation_age = 0
log_rotation_size = 0
log_min_duration_statement = 0
```

`log_rotation_age` and `log_rotation_size` at `0` disable automatic rotation, so
PostgreSQL keeps writing to one file until you tell it otherwise — which is
exactly what you want when one file should mean one load test. `log_file_mode`
makes the file readable by whoever runs pgBadger. `logging_collector` needs a
restart; the rest only a reload.

Then, for each run:

```shell
psql -U postgres -c "select pg_rotate_logfile();"   # start a fresh log file
# ... run the load test ...
pgbadger --prefix "$(psql -tAc 'SHOW log_line_prefix')" \
         -o report.html "$(ls -1t /var/log/postgresql/*.log | head -1)"
```

The `--prefix` is not optional: pgBadger parses the log with it, and gets
nothing out of the file if it does not match what the server writes. Reading it
from the server rather than typing it is the cheap way not to get that wrong.

`log_min_duration_statement = 0` logs **every** statement. That is what you want
for a three minute load test, and it is never what you want on a production
instance.

Three sections matter, and they answer different questions:

| Section | Question |
|---------|----------|
| **Time consuming queries** | which *single* query is slow? → one query to `EXPLAIN` |
| **Most frequent queries** | which query is *called too often*? → an N+1 somewhere in Python |
| **Overall statistics** | how many queries in total? → divide by user actions |

A query at 0.3 ms that runs 2.000 times per click costs 600 ms. It will never
appear in a slow query log at any threshold you would dare set in production,
and it is usually the real problem.

**The duration column is a trap.** If you open a pgBadger report and start by
sorting on query time, an N+1 is invisible — every row says 0.00. Exercise 2 is
built entirely around that mistake: go there with a stopwatch and you will
conclude, correctly and uselessly, that nothing is slow. The column that matters
is **count**.

### speedscope — "this click was slow"

Odoo's profiler records one execution and exports a flame graph.

* **UI**: developer mode → bug icon → *Enable profiling* → do the thing →
  *Settings > Technical > Profiling* → **Speedscope**. For exercises 3-5 the
  thing to do is *Performance Advanced > Run a flow*.
* **Headless**: wrap the flow in a `Profiler` in `odoo-bin shell`. There is no
  script shipped for this on purpose — write your own, it is four lines:

```python
# odoo-bin shell -d perf_advanced --no-http
from odoo.tools.profiler import Profiler, PeriodicCollector, SQLCollector

with Profiler(db=env.cr.dbname, description='exercise 3',
              collectors=[SQLCollector(), PeriodicCollector(interval=0.001)],
              disable_gc=True) as profiler:
    # ---- the flow you want to measure, see each exercise ----
    env['mrp.production'].search([('state', '=', 'draft')], limit=20).action_confirm()

env.cr.rollback()

profile = env['ir.profile'].browse(profiler.profile_id)
print(f'{profile.duration:.2f}s, {profile.sql_count} queries, ir.profile {profile.id}')
with open('speedscope.json', 'wb') as fd:
    fd.write(profile._generate_speedscope(profile._parse_params({'combined_profile': True})))
```

Two things in there are not obvious and will cost you an afternoon if you guess:

* **the `rollback()` is mandatory**, and not for the reason you think. The
  profiler writes its `ir.profile` row on its *own* database connection. Your
  shell transaction was opened before that row existed, so it cannot see it —
  `browse(profiler.profile_id)` raises `MissingError` until you roll back and
  get a fresh snapshot. It also undoes whatever the flow changed, which is what
  keeps the exercise replayable.
* **`SQLCollector` and `PeriodicCollector` are both needed.** The first records
  the queries, the second samples the Python stack. With only one of them,
  `combined_profile` has nothing to combine and half of the flame graph is
  missing — which is exactly the half that tells you whether you have a query
  problem or an algorithm problem.

Drop the resulting `speedscope.json` on <https://www.speedscope.app>, or use the
**Speedscope** button on the `ir.profile` record — both read the same format.

In speedscope, switch to **Left Heavy**: it merges all the calls of the same
stack, so a function called 4.000 times becomes one wide block instead of 4.000
invisible slivers. The SQL frames are interleaved with the Python ones, so a
wide SQL band means "the database is working", and a wide Python band with no
SQL underneath means "the database is idle and we are burning CPU".

### EXPLAIN — "why is this one query slow"

```sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS, COSTS) <the query>;
```

Read it top-down, and compare `rows=` (the estimate) with `actual rows=` (the
truth). A factor 100 between them means PostgreSQL is planning against numbers
that do not exist — run `VACUUM ANALYZE` before blaming the plan. `Buffers:
shared read=` is the number of 8 kB blocks that were *not* in cache; that is the
number that turns into disk I/O on a production instance. And `Rows Removed by
Filter` is the single most useful line in a plan: it is the work PostgreSQL did
for nothing.

---

---

## The five exercises

Each one is a standalone file: the story, the data to generate, what to measure,
and the answer in a collapsed block at the end.

| # | Exercise | Tools | What you practice |
|---|----------|-------|-------------------|
| 1 | [Customer portal "track my order"](exercises/01-customer-portal.md) | locust, pgBadger, EXPLAIN | what a sequential scan really costs; trigram indexes and where they stop working |
| 2 | [Warehouse barcode scanner](exercises/02-barcode-scanner.md) | locust, pgBadger | reading the *count* column, not the duration; killing an N+1 over a location tree |
| 3 | [Manufacturing order confirmation](exercises/03-manufacturing-order.md) | speedscope | spotting a per-record `search` in a flame graph, batching with `_read_group` |
| 4 | [Overdue customers list](exercises/04-overdue-customers.md) | speedscope, EXPLAIN | a compute that queries per record; non-stored related fields; partial indexes |
| 5 | [POS session closing](exercises/05-pos-closing.md) | speedscope | a flow with almost no SQL: pure Python algorithmics |

Exercises 1-2 are *load tests*: many users, aggregated evidence, PostgreSQL
logs. Exercises 3-5 are *single flows*: one user, one click, a flame graph.

---

## Wrap-up

| Symptom | First tool | Usual cause |
|---------|-----------|-------------|
| "everything is slow since this morning" | pgBadger, *time consuming queries* | one missing index on a hot path, trashing the shared buffers |
| "this screen is slow for everybody, always" | pgBadger, *most frequent queries* | N+1, in Python or in the RPC protocol |
| "this one click is slow" | speedscope, Left Heavy | depends on the SQL/Python ratio |
| wide SQL band, repeated | speedscope + `EXPLAIN` | per-record query → `_read_group`, or a missing index |
| wide Python band, no SQL | speedscope | complexity of the algorithm, ORM object churn |
| numbers that make no sense | `VACUUM ANALYZE`, then measure again | stale statistics |

And the three rules that cover most of it:

1. **Measure before you fix.** Every exercise here has an obvious wrong answer
   that a profile rules out in thirty seconds.
2. **A query count that grows with the data is a bug**, even when every single
   query is fast.
3. **`Rows Removed by Filter` is wasted work.** When a plan reads thousands of
   rows to return sixteen, you have found your index.

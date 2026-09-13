# perf_advanced

Five hands-on performance exercises for Odoo 19.

| # | Exercise | Tools | What you practice |
|---|----------|-------|-------------------|
| 1 | [Customer portal "track my order"](exercises/01-customer-portal.md) | locust, pgBadger, EXPLAIN | what a sequential scan really costs, trigram indexes and where they stop working |
| 2 | [Warehouse barcode scanner](exercises/02-barcode-scanner.md) | locust, pgBadger | reading the *count* column and not the duration, killing an N+1 over a location tree |
| 3 | [Manufacturing order confirmation](exercises/03-manufacturing-order.md) | speedscope | spotting a per-record `search` in a flame graph, batching with `_read_group` |
| 4 | [Overdue customers list](exercises/04-overdue-customers.md) | speedscope, EXPLAIN | a compute that queries per record, related fields that add a join, partial indexes |
| 5 | [POS session closing](exercises/05-pos-closing.md) | speedscope | a flow with almost no SQL: pure Python algorithmics |

Exercises 1-2 are *load tests*: many users, aggregated evidence, PostgreSQL logs.
Exercises 3-5 are *single flows*: one user, one click, a flame graph.

**The module ships the slow code on purpose.** Each exercise is its own file
under [exercises/](exercises/), with the answer in a collapsed block at the end.
[EXERCISES.md](EXERCISES.md) is the index: it carries the toolbox (pgBadger,
speedscope, EXPLAIN) and the wrap-up. Try first.

## Setup

### 1. Prerequisites

```shell
pip install "faker==22.0.0"            # required by odoo-bin populate
pip install locust OdooLocust          # exercises 1-2
sudo apt install pgbadger              # exercises 1-2
```

Exercises 1-2 read the PostgreSQL log, so `postgresql.conf` needs:

```ini
logging_collector = on
log_directory = '/var/log/postgresql'
log_file_mode = 0777
log_rotation_age = 0
log_rotation_size = 0
log_min_duration_statement = 0
```

`logging_collector` needs a restart, the rest only a reload. Rotation is
disabled on purpose: you start a fresh log file per run with
`psql -U postgres -c "select pg_rotate_logfile();"`, so one file is one load
test. Never leave `log_min_duration_statement = 0` on a production instance.

Exercise 4 creates customer invoices, so the company needs a **chart of
accounts** — without one there is no sale journal and the blueprint cannot
create anything. Installing `account` usually brings one in automatically;
check before assuming either way:

```shell
psql -d perf_advanced -c "SELECT count(*) FROM account_journal WHERE type = 'sale'"
```

If that returns 0, load one:

```shell
odoo-bin shell -d perf_advanced --no-http <<'EOF'
env['account.chart.template'].try_loading('generic_coa', company=env.company, install_demo=False)
env.cr.commit()
EOF
```

Nothing else is needed: the exercise 5 blueprint creates its own point of sale.

### 2. Database and module

```shell
createdb perf_advanced
odoo-bin -d perf_advanced -i perf_advanced,populate --stop-after-init
# blueprints shipped by a module are only discovered when `populate` is upgraded
odoo-bin -d perf_advanced -u populate --stop-after-init
```

### 3. PostgreSQL settings for a training instance

```sql
ALTER ROLE odoo IN DATABASE perf_advanced SET maintenance_work_mem = '2GB';
ALTER ROLE odoo IN DATABASE perf_advanced SET work_mem = '256MB';
ALTER ROLE odoo IN DATABASE perf_advanced SET synchronous_commit = off;
```

`synchronous_commit = off` makes the populate much faster. Keep it off for the
whole training: it removes the disk flush noise from the measurements.

### 4. Data

Each exercise has its own blueprint, run only the one you need:

```shell
odoo-bin populate -d perf_advanced -b perf_advanced.ex1_portal                   -j auto
odoo-bin populate -d perf_advanced -b perf_advanced.ex2_barcode                  -j auto
odoo-bin populate -d perf_advanced -b perf_advanced.ex3_manufacturing
odoo-bin populate -d perf_advanced -b perf_advanced.ex4_overdue                  -j auto
odoo-bin populate -d perf_advanced -b perf_advanced.ex5_pos_closing
```

`--scale` multiplies every count of the blueprint, `-j auto` uses all cores.
Start small (`--scale 0.1`) to check that everything runs, then scale up.

Rough cost on a laptop with `-j auto`: exercise 1 is ~3 minutes (150.000 orders
with a 3.9 kB note each, ~300 MB), exercises 2, 3 and 5 are one to two minutes
each, and exercise 4 is by far the slowest at ~3 minutes, because it has to *post*
11.000 invoices one at a time (the invoice sequence locks, so parallel posting
deadlocks). Use `--resume` if you interrupt it.

Exercise 1 needs both the rows and the notes: the note is 95 % of what its
sequential scan costs. `--scale 0.5` still shows the problem, at about half the
duration.

`odoo-bin populate` runs `VACUUM ANALYZE` when it finishes, so the planner
statistics are already correct. If you change the data by hand afterwards, run
it again yourself — an un-analyzed table gives PostgreSQL bogus row estimates
and you will spend the exercise debugging the statistics instead of the query.

### 5. Profiling

Speedscope (exercises 3-5) needs nothing extra: Odoo generates the file, you
drop it on <https://www.speedscope.app>, or use the **Speedscope** button on the
`ir.profile` record.

To record a profile from the UI: developer mode, then the bug icon in the top
right, **Enable profiling**, then *Performance Advanced > Run a flow*.

To record one headlessly, wrap the flow in a `Profiler` in `odoo-bin shell`.
No script is shipped for that on purpose — the recipe, and the two things about
it that are not obvious, are in the speedscope section of
[EXERCISES.md](EXERCISES.md).

## Files

```
models/          the slow implementations -- this is the code you fix
wizard/          "Run a flow" dialog, one button per single-flow exercise
populate/        one populate blueprint per exercise, 01_... to 05_...
tools/
  locust_ex1_portal.py     skeleton to complete  (exercise 1)
  locust_ex2_scanner.py    skeleton to complete  (exercise 2)
                           (the pgBadger and profiler recipes are in
                            EXERCISES.md -- you write those yourself)
EXERCISES.md     index: the toolbox, the five exercises, the wrap-up
exercises/
  01-customer-portal.md      load test, pgBadger, trigram indexes
  02-barcode-scanner.md      load test, pgBadger, an N+1 per shelf
  03-manufacturing-order.md  speedscope, batching with _read_group
  04-overdue-customers.md    speedscope, EXPLAIN, partial index
  05-pos-closing.md          speedscope, algorithmic complexity
```

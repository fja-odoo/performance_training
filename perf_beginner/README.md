[Presentation](https://docs.google.com/presentation/d/1vz6KlLZ1B48SArlIlD7rfUGs2x7YpzzrBCW0lwmTNoQ/edit?usp=sharing)

# Exercice 2

```SQL
ALTER ROLE odoo IN DATABASE perf_training SET maintenance_work_mem = '2GB';
ALTER ROLE odoo IN DATABASE perf_training SET work_mem = '256MB';
ALTER ROLE odoo IN DATABASE perf_training SET synchronous_commit = off;
```

```shell
python3 populate_partner_sales.py --url http://127.0.0.1:8069 --db perf_training --username admin --password admin --partner-name "Perf Test Partner" --partner-count 5 --orders-per-partner 3
```

```shell
odoo-bin populate -d perf_training --models=res.partner,sale.order --factors=300000
```


# -- 1. Enable logging collector globally (one-time, requires restart if changing from off)
ALTER SYSTEM SET logging_collector = on;

-- 2. Scope verbose logging to just this database
ALTER DATABASE perf_training_final_2 SET log_statement = 'all';
ALTER DATABASE perf_training_final_2 SET log_min_duration_statement = 0;
ALTER DATABASE perf_training_final_2 SET log_destination = 'stderr';
ALTER DATABASE perf_training_final_2 SET log_line_prefix = '%m [%p] %q%u@%d ';

-- 3. Reload config (won't apply logging_collector if it was off before — see note below)
SELECT pg_reload_conf();

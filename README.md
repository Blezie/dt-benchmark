# dt-benchmark

Python benchmarking for PostgreSQL, MongoDB, and InfluxDB under simulated Digital Twin (IoT-style) loads with real-time ingestion + concurrent queries and automatic metrics collection.

## Quick start

1. Install Docker Desktop and Python 3.

2. Select one database in config.yaml, then start it using: python scripts/run_db.py up. This launches the selected database based on your configuration. To stop it, run: python scripts/run_db.py down

3. Run the Python workload generator to ingest and query concurrently; export results to CSV; plot with matplotlib/pandas.

> **Note:** Experiments in the thesis ran each DB in Docker with default settings; only one DB active at a time.

## What this tool does

- **Systems under test:** PostgreSQL (relational), MongoDB (NoSQL), InfluxDB (TSDB). Official container images, default configs.
- **Client & drivers:** Custom Python generator; psycopg (PostgreSQL), pymongo (MongoDB), influxdb3-python (InfluxDB 3).
- **Mixed workload:** Continuous real-time inserts + concurrent queries to mirror DT synchronization.
- **Run protocol (per configuration):** preload 1h history → warm-up 60s (discard) → measure 300s → cool-down 60s, repeat ×3 and aggregate.

## Data model (uniform across DBs)

Each record is one measurement:

```json
{ "sensor_id": "sensor_0042", "timestamp": "2025-10-16T13:45:00Z", "value": 23.7 }
```

- **PostgreSQL:** table `(sensor_id TEXT, ts TIMESTAMPTZ, value DOUBLE PRECISION)`, index `(sensor_id, ts)`.

- **MongoDB:** time-series collection `timeField: "ts"`, `metaField: "sensor_id"`, index `{sensor_id:1, ts:1}`.

- **InfluxDB 3:** measurement `measurements` with `sensor_id` as dimension, `value` metric, `time` timestamp.

> **Note:** Timestamps in UTC; JSON timestamp stored as `ts` except `time` in InfluxDB.

## Workload scales

- **Small:** 100 sensors, 1 Hz.
- **Medium:** 1,000 sensors, 1 Hz.
- **Large:** 5,000 sensors, 2 Hz.

Client thread count scales with size; each DB is preloaded with 1h of history before timing.

## Query set (executed during ingestion)

- **W1 – Latest:** most recent value for sensor S.
- **W2 – Range 5 min:** all readings for S in last 5 minutes.
- **W3 – Downsample 1h/1m:** mean per 1-minute bucket over last hour for S.
- **W4 – Top-10:** sensors with highest mean over last 5 minutes.

> **Note:** Implemented as SQL for PostgreSQL and InfluxDB 3; MongoDB aggregation pipeline.

## Metrics & how we compute them

- **Ingestion throughput:** successful inserts / measurement window (r/s).
- **Query latency:** client-side p50/p95/p99 per query type (warm-up excluded).
- **Storage utilization:** on-disk size after ingest-only run + 60s idle settle.
- **Resource usage:** container CPU% and MiB via docker stats @ 1 Hz (mean ± stdev; peaks where relevant).
- **Data analysis:** CSV exports merged in pandas; plots with matplotlib; results aggregated across 3 repeats.

## Test setup (reference)

- **Isolation:** Docker containers; identical host; one DB active per run.
- **Fairness:** only minimal equivalent schema aids (see Data model); no per-container CPU/RAM limits.
- **Example host used in thesis:** Ryzen 7 7800X3D, 32 GB RAM, NVMe SSD; Windows 11 Pro 24H2. (You can reproduce on other hosts; keep other variables fixed.)

## Reproducibility checklist

- [ ] Pull official images and keep them at fixed tags.
- [ ] Preload exactly 1h history before timing.
- [ ] Follow the run protocol and repeat ×3.
- [ ] Fix random seeds in the generator.
- [ ] Export raw CSVs + docker stats; keep raw byte counts for storage.

## Repository pointers

- `workload/` – Python generator (ingest + queries, config for scales & concurrency).
- `db/` – minimal schemas/mappings per engine.
- `scripts/` – helpers to start/stop a single DB container and to collect docker stats.
- `analysis/` – notebooks to aggregate CSVs and plot figures.

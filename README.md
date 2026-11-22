# PharmaLock — Pharmacy Inventory & Transaction Systems Lab

<p align="center">
  <img src="https://raw.githubusercontent.com/Joshua-Sarkar/Joshua-Sarkar/media/repositories/pharmalock/hero.gif" width="100%" alt="PharmaLock animated pharmacy systems banner" />
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Joshua-Sarkar/Joshua-Sarkar/media/repositories/pharmalock/flow.gif" width="100%" alt="PharmaLock transaction, lock, WAL and buffer workflow" />
</p>

PharmaLock is a small Flask application built as an interactive **Operating Systems + Database Management Systems** simulation. It uses a pharmacy stock catalogue to make storage, caching, transactions, locking, deadlocks and crash recovery visible through a browser dashboard.

It is an educational simulator, not an inventory platform for dispensing real medication.

## What is inside

| Subsystem | Implementation | Why it exists |
|---|---|---|
| Disk manager | File-backed medicine records | Simulates persistent storage |
| Buffer pool | Four-page cache with LRU eviction | Demonstrates cache hits, misses and replacement |
| Lock manager | Exclusive per-medicine locks and a wait-for graph | Coordinates concurrent department operations |
| Transaction manager | Strict two-phase locking | Groups inventory changes into atomic transactions |
| Write-ahead log | JSON-lines WAL with `fsync` | Records updates before committing them |
| Recovery | Redo committed work; undo unfinished work | Demonstrates restart consistency |
| Pharmacy engine | Dispense, restock, expiry audit and stress actions | Connects the subsystems to an understandable domain |

## Transaction lifecycle

1. A transaction receives a new ID and writes a `BEGIN` record.
2. It requests an exclusive lock for each medicine record it needs.
3. The lock manager records waits and checks the wait-for graph for cycles.
4. The transaction reads the medicine through the buffer pool.
5. The WAL records the before/after stock values before the buffer/disk write.
6. On success, a `COMMIT` record closes the transaction. On validation failure, the manager rolls back changes and records an abort.
7. A simulated crash can interrupt the transaction before commit. Recovery replays committed updates and reverses unfinished ones.

## Dashboard API

Run the Flask application and open `http://127.0.0.1:5000`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/state` | Inventory, locks, event history, WAL and buffer statistics |
| POST | `/api/dispense` | Reduce stock for a department |
| POST | `/api/restock` | Increase stock |
| POST | `/api/expiry` | Inspect expiry-related inventory |
| POST | `/api/refresh` | Refresh cached medicine records |
| POST | `/api/deadlock` | Run the deadlock demonstration |
| POST | `/api/crash` | Trigger the simulated crash path |
| POST | `/api/recover` | Run recovery |
| POST | `/api/stress` | Exercise concurrent requests |
| POST | `/api/reset` | Reset demonstration data |

The initial catalogue is seeded in `pharmacy.py` when the backing store is empty.

## Run locally

The Flask application is inside the `pharmalock/` directory:

```bash
cd pharmalock
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Run the self-test from the same directory:

```bash
python smoke_test.py
```

## Code map

- `app.py` — Flask routes and JSON responses
- `pharmacy.py` — inventory domain and subsystem composition
- `disk_manager.py` — persistent record storage
- `buffer_pool.py` — LRU page cache
- `lock_manager.py` — exclusive locks, wait-for graph and deadlock victim handling
- `transaction.py` — transaction lifecycle, rollback and simulated crashes
- `log_manager.py` — WAL append and recovery
- `static/index.html` — interactive dashboard

## Scope

The data catalogue and operations are illustrative. The project does not connect to a real pharmacy, validate prescriptions, integrate with a regulated drug database, or provide medication-safety controls. Do not use it to manage real stock or clinical dispensing.

---

<p align="center"><sub>Locks, logs, pages, transactions—and one deliberately inconvenient deadlock.</sub></p>

# PharmaLock - Phase 3
Run: `pip install flask` then `python app.py` then open http://127.0.0.1:5000  (self-test: `python smoke_test.py`)

| Phase 3 task | Where in the code |
|---|---|
| 1. Deadlock detection | lock_manager.py -> `acquire()` and `_find_cycle()` |
| 2. Deadlock demo | app.py -> `deadlock()`; "Deadlock demo" button |
| 3. Crash demo + recovery | app.py -> `crash()`; log_manager.py -> `recover()`; transaction.py -> `crash` flag |
| 4. Expiry rule for memory | buffer_pool.py -> `refresh()` |
| 5. Lock view web page | static/index.html -> "Live lock view" card; app.py -> `state()` |
| 6. Many-requests test | pharmacy.py -> `stress()` |
| 7. Testing + docs | smoke_test.py, this file |

Layers: OS side = disk_manager, buffer_pool, lock_manager. DBMS side = log_manager, transaction, pharmacy.

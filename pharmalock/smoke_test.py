# Quick self-test: python smoke_test.py (uses a temporary folder, your real data is untouched)
import os
import tempfile
import threading

# Use an isolated temporary data folder so tests never touch production files
os.environ["PHARMA_DATA"] = tempfile.mkdtemp()

from pharmacy import Pharmacy
from transaction import SimulatedCrash

P = Pharmacy()

# Test 1: Verify negative stock rule (prevent overdraw)
try:
    P.dispense("T", 0, 9999)
    raise SystemExit("FAIL: overdraw allowed")
except ValueError:
    print("ok  refuses to go below zero")

# Test 2: Deadlock detection and victim abortion
res = []


def run_worker(department, items):
    try:
        P.run(department, items, hold=0.5)
        res.append("ok")
    except Exception as err:
        res.append(str(err))


threads = [
    threading.Thread(target=run_worker, args=("A", [(0, -1), (1, -1)])),
    threading.Thread(target=run_worker, args=("B", [(1, -1), (0, -1)])),
]

for t in threads:
    t.start()
for t in threads:
    t.join()

assert sum("victim" in r for r in res) == 1 and "ok" in res, res
print("ok  deadlock found, one cancelled, other finished")

# Test 3: Simulated crash and WAL recovery
before = P.disk.read(2)["stock"]
try:
    P.run("X", [(2, -5)], hold=0, crash=True)
except SimulatedCrash:
    pass

assert P.disk.read(2)["stock"] == before - 5
P.recover()
assert P.disk.read(2)["stock"] == before
print("ok  crash recovered using the log")

# Test 4: Concurrency stress test with 150 requests
P.reset()
stress_result = P.stress(150)
assert stress_result["correct"] and stress_result["final"] == 0, stress_result
print("ok  150 requests:", stress_result)

# Test 5: Expiry refresh ordering in buffer pool
P.refresh = P.pool.refresh()
print("ok  expiry refresh order", P.refresh)

print("ALL OK")

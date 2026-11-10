# DBMS SIDE - Pharmacy Operations: ties all subsystems (disk, cache, log, locks) together.
# Handles high-level inventory operations: dispensing, restocking, expiry audits, and stress testing.
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import os
import time

from buffer_pool import BufferPool
from disk_manager import DiskManager
from lock_manager import Deadlock, LockManager
from log_manager import LogManager
from transaction import SimulatedCrash, TransactionManager

# Default database and log directory
DATA = os.environ.get(
    "PHARMA_DATA",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
)

# Initial sample catalog: (medicine_name, starting_stock, days_until_expiry)
SEED = [
    ("Paracetamol", 100, 400),
    ("Amoxicillin", 60, 25),
    ("Insulin", 40, 12),
    ("Aspirin", 80, 300),
    ("Ibuprofen", 50, 5),
    ("Morphine", 20, 200),
    ("Saline", 120, 150),
    ("Adrenaline", 30, 60),
]


def ymd(days_from_today):
    """Calculates an integer date YYYYMMDD given an offset in days from today."""
    target_date = date.today() + timedelta(days=days_from_today)
    return target_date.year * 10000 + target_date.month * 100 + target_date.day


def days_left(expiry_integer):
    """Calculates number of days left until expiry from an integer YYYYMMDD date."""
    year = expiry_integer // 10000
    month = (expiry_integer // 100) % 100
    day = expiry_integer % 100
    expiry_date = date(year, month, day)
    return (expiry_date - date.today()).days


class Pharmacy:
    def __init__(self):
        os.makedirs(DATA, exist_ok=True)

        # Initialize OS storage and caching layer
        db_file = os.path.join(DATA, "medicines.db")
        wal_file = os.path.join(DATA, "wal.log")

        self.disk = DiskManager(db_file)
        self.pool = BufferPool(self.disk, cap=4)

        # Initialize DBMS transaction, lock, and logging managers
        self.log = LogManager(wal_file)
        self.locks = LockManager()
        self.tm = TransactionManager(self.pool, self.log, self.locks)

        self.crashed = False

        # If database file is completely fresh, seed initial medicines; otherwise run crash recovery
        if self.disk.count() == 0:
            self.seed()
        else:
            # Automatic crash recovery on system startup
            self.log.recover(self.disk)

    def seed(self):
        # Populate the database file with the initial inventory seed
        for medicine_id, (name, stock, expiry_days) in enumerate(SEED):
            record = {
                "id": medicine_id,
                "name": name,
                "stock": stock,
                "expiry": ymd(expiry_days),
            }
            self.disk.write(record)

    def reset(self):
        # Reset entire system back to starting state for testing and demos
        self.pool.pages.clear()
        self.locks.reset()

        wal_file = os.path.join(DATA, "wal.log")
        with open(wal_file, "w") as f:
            pass
        self.log.n = 0

        self.locks.events.clear()
        self.seed()
        self.crashed = False

    def run(self, dept, items, hold=0, crash=False):
        # Block operations if engine is currently halted due to an unrecovered crash
        if self.crashed:
            raise RuntimeError("Engine is down after the crash. Click Recover.")

        # Validate that all requested medicine IDs exist in the catalog
        total_medicines = self.disk.count()
        for medicine_id, _ in items:
            if not (0 <= medicine_id < total_medicines):
                raise ValueError("Unknown medicine")

        try:
            tx = self.tm.execute(dept, items, hold=hold, crash=crash)
            self.locks.event(f"T{tx} ({dept}) COMMITTED")
            return tx

        except SimulatedCrash:
            # Simulate sudden power loss: RAM buffer and locks are wiped out instantly
            self.crashed = True
            self.pool.pages.clear()
            self.locks.reset()
            self.locks.event("CRASH! Stopped in the middle of a dispense. No COMMIT was written.")
            raise

        except (ValueError, Deadlock) as err:
            self.locks.event(str(err))
            raise

    def dispense(self, dept, pid, qty, hold=0):
        # Dispensing subtracts stock (delta = -qty)
        return self.run(dept, [(pid, -qty)], hold=hold)

    def restock(self, dept, pid, qty, hold=0):
        # Restocking adds stock (delta = +qty)
        return self.run(dept, [(pid, qty)], hold=hold)

    def check_stock(self):
        # Read current stock directly from the binary disk file
        total = self.disk.count()
        return [self.disk.read(i) for i in range(total)]

    def check_expiry(self, days):
        # Find all medicines that will expire within the given number of days
        all_medicines = self.check_stock()
        results = []
        for item in all_medicines:
            item_copy = dict(item)
            item_copy["days_left"] = days_left(item["expiry"])
            if item_copy["days_left"] <= days:
                results.append(item_copy)

        # Sort so the medicines expiring soonest appear first
        results.sort(key=lambda r: r["days_left"])
        return results

    def recover(self):
        # Run Write-Ahead Log crash recovery to restore system consistency
        report = self.log.recover(self.disk)
        self.pool.pages.clear()
        self.locks.reset()
        self.crashed = False

        for message in report:
            self.locks.event("RECOVERY: " + message)
        return report

    # PHASE 3 FEATURE 6: MANY-REQUESTS TEST - n departments hit ONE medicine at the same moment
    def stress(self, n, pid=0):
        # Concurrency test: launch N simultaneous threads trying to dispense from the same medicine
        start_stock = self.disk.read(pid)["stock"]
        self.locks.quiet = True
        start_time = time.time()

        def single_request(request_id):
            try:
                self.tm.execute(f"Req{request_id}", [(pid, -1)])
                return 1
            except ValueError:
                # Refused when stock reached zero (no negative stock allowed)
                return 0

        # Execute all requests concurrently using a thread pool
        with ThreadPoolExecutor(max_workers=n) as executor:
            successful_requests = sum(executor.map(single_request, range(n)))

        elapsed_seconds = time.time() - start_time
        self.locks.quiet = False
        final_stock = self.disk.read(pid)["stock"]

        expected_final = start_stock - successful_requests
        is_correct = (final_stock == expected_final and final_stock >= 0)
        safe_duration = max(elapsed_seconds, 1e-6)
        throughput = round(n / safe_duration)

        return {
            "requests": n,
            "succeeded": successful_requests,
            "refused": n - successful_requests,
            "start": start_stock,
            "final": final_stock,
            "expected": expected_final,
            "correct": is_correct,
            "seconds": round(elapsed_seconds, 2),
            "per_sec": throughput,
        }

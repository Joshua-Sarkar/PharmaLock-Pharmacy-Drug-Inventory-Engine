# DBMS SIDE - Log Manager: implements Write-Ahead Logging (WAL).
# Fundamental database rule: always log changes to disk BEFORE changing actual data.
import json
import os
import threading


class LogManager:
    def __init__(self, path):
        self.path = path
        self.mu = threading.Lock()

        # Ensure the log file exists on disk
        if not os.path.exists(path):
            with open(path, "a"):
                pass

        # Recover transaction counter from previous log entries so IDs never collide
        existing_records = self.read_all()
        tx_ids = [record["tx"] for record in existing_records if "tx" in record]
        self.n = max(tx_ids) if tx_ids else 0

    def new_tx(self):
        # Generate a unique, monotonically increasing transaction ID
        with self.mu:
            self.n += 1
            return self.n

    def append(self, rec, sync=True):
        # Append a JSON record to the end of the log file
        with self.mu:
            with open(self.path, "a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                # fsync forces the operating system to flush kernel cache to physical storage
                if sync:
                    os.fsync(f.fileno())

    def read_all(self):
        # Read all valid JSON log entries in order
        records = []
        if not os.path.exists(self.path):
            return records

        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    # Ignore corrupted or half-written line at the end after a sudden crash
                    pass

        return records

    # PHASE 3 FEATURE 3: CRASH RECOVERY - REDO committed work, UNDO unfinished work
    def recover(self, disk):
        # ARIES-style recovery: ensures database consistency after a system crash
        recs = self.read_all()

        # Step 1: Find transactions that committed, and transactions already finished
        committed = {r["tx"] for r in recs if r.get("type") == "COMMIT"}
        aborted = {r["tx"] for r in recs if r.get("type") == "ABORT"}
        finished = committed | aborted

        def set_medicine_stock(pid, new_stock):
            # Helper to write directly to disk record
            record = disk.read(pid)
            record["stock"] = new_stock
            disk.write(record)
            return record["name"]

        # Step 2 (REDO pass): Replay committed changes forward so successful updates persist
        for r in recs:
            if r.get("type") == "UPDATE" and r["tx"] in committed:
                set_medicine_stock(r["pid"], r["after"])

        # Step 3 (UNDO pass): Scan backwards and rollback uncommitted (in-flight) transactions
        report = []
        uncommitted_txs = set()

        for r in reversed(recs):
            if r.get("type") == "UPDATE" and r["tx"] not in finished:
                tx_id = r["tx"]
                med_name = set_medicine_stock(r["pid"], r["before"])
                uncommitted_txs.add(tx_id)
                report.append(
                    f"UNDO T{tx_id}: {med_name} stock restored to {r['before']} (no COMMIT in log)"
                )

        # Write ABORT records for undone transactions so they won't be undone again on next boot
        for tx_id in uncommitted_txs:
            self.append({"type": "ABORT", "tx": tx_id})

        if report:
            return report
        return ["Nothing to undo - all work in the log was finished."]

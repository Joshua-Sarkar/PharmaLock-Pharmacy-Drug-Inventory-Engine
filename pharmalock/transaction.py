# DBMS SIDE - Transaction Manager: coordinates ACID transactions.
# Either all inventory changes take effect (COMMIT), or none of them do (ABORT/UNDO).
import time
from lock_manager import Deadlock


class SimulatedCrash(Exception):
    """Raised during the crash demo to simulate power failure before commit."""
    pass


class TransactionManager:
    def __init__(self, pool, log, locks):
        self.pool = pool
        self.log = log
        self.locks = locks

    def execute(self, dept, items, hold=0, crash=False):
        """Executes a list of updates atomically: items = [(medicine_id, delta)].

        Delta < 0 represents dispensing stock.
        Delta > 0 represents restocking inventory.
        """
        # Step 1: Assign a unique transaction ID and write BEGIN to log
        tx = self.log.new_tx()
        self.log.append({"type": "BEGIN", "tx": tx, "dept": dept}, sync=False)

        # In-memory undo list to rollback changes if this transaction aborts mid-way
        undo_stack = []

        try:
            for pid, delta in items:
                # 1. Strict 2-Phase Locking: Acquire lock on this medicine before reading or writing
                self.locks.acquire(tx, pid, dept)

                # Optional pause so live lock state can be observed on the web dashboard
                if hold > 0:
                    time.sleep(hold)

                # Read current stock from buffer pool
                rec = self.pool.get(pid)
                new_stock = rec["stock"] + delta

                # Business Rule: Pharmacy inventory must never drop below zero
                if new_stock < 0:
                    med_name = rec["name"]
                    current_stock = rec["stock"]
                    requested_amount = -delta
                    raise ValueError(
                        f"T{tx} ({dept}) REFUSED: only {current_stock} {med_name} in stock, asked for {requested_amount}"
                    )

                # 2. Write-Ahead Logging: Write UPDATE record to log on disk FIRST
                self.log.append({
                    "type": "UPDATE",
                    "tx": tx,
                    "pid": pid,
                    "before": rec["stock"],
                    "after": new_stock
                })

                # 3. Apply modification to buffer pool (and through to disk) SECOND
                rec["stock"] = new_stock
                self.pool.write(pid, rec)

                # Save previous stock level in case we need to abort and rollback
                undo_stack.append((pid, new_stock - delta))

            # Simulated crash feature: crash the system before writing COMMIT to WAL
            if crash:
                raise SimulatedCrash()

            # 4. Durability: Write COMMIT to log, finalizing the transaction
            self.log.append({"type": "COMMIT", "tx": tx})
            return tx

        except SimulatedCrash:
            # Let the simulated crash bubble up to test recovery
            raise

        except Exception:
            # Atomicity: Roll back any partially applied changes in reverse order
            for pid, old_stock in reversed(undo_stack):
                current_record = self.pool.get(pid)
                current_record["stock"] = old_stock
                self.pool.write(pid, current_record)

            # Record ABORT in the log so future crash recovery knows this failed
            self.log.append({"type": "ABORT", "tx": tx})
            raise

        finally:
            # Strict 2-Phase Locking rule: Release all locks held by this transaction at the end
            self.locks.release_all(tx)

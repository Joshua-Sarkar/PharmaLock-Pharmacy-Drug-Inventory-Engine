# OS SIDE - Lock Manager: ensures only one department modifies a medicine at a time.
# Includes deadlock detection using a wait-for graph.
from collections import deque
import threading
import time


class Deadlock(Exception):
    """Raised when a transaction must abort to break a circular wait."""
    pass


class LockManager:
    def __init__(self):
        # Condition variable coordinates threads waiting for locks to be released
        self.cv = threading.Condition()

        # owner: maps medicine_id -> transaction_id currently holding the lock
        self.owner = {}

        # waiting: maps transaction_id -> medicine_id it is currently blocked on
        self.waiting = {}

        # names: maps transaction_id -> department name (for human-readable logging)
        self.names = {}

        # doomed: transactions picked as victims to abort and break deadlocks
        self.doomed = set()

        # Live history of lock events for the frontend dashboard
        self.events = deque(maxlen=60)
        self.quiet = False

    def event(self, msg):
        # Record a timestamped message in the event log (unless suppressed during stress tests)
        if not self.quiet:
            timestamp = time.strftime("%H:%M:%S  ")
            self.events.appendleft(timestamp + msg)

    def acquire(self, tx, pid, dept):
        # Request exclusive lock for medicine `pid` on behalf of transaction `tx`
        with self.cv:
            self.names[tx] = dept

            # Loop while the lock is held by another transaction
            while self.owner.get(pid) not in (None, tx):
                # Check if this transaction was chosen as the deadlock victim to abort
                if tx in self.doomed:
                    self.doomed.discard(tx)
                    self.waiting.pop(tx, None)
                    raise Deadlock(f"T{tx} ({dept}) CANCELLED: chosen as deadlock victim")

                # If this is our first time waiting for this medicine, update the graph
                if self.waiting.get(tx) != pid:
                    self.waiting[tx] = pid
                    current_holder = self.owner[pid]
                    holder_dept = self.names[current_holder]
                    self.event(f"T{tx} ({dept}) waits for medicine #{pid}, held by T{current_holder} ({holder_dept})")

                    # PHASE 3 FEATURE 1: DEADLOCK DETECTION
                    # Check if waiting for this lock creates a circular dependency
                    cycle = self._find_cycle(tx)
                    if cycle:
                        # Pick the newest transaction (highest ID) as the victim so older work finishes
                        victim = max(cycle)
                        chain_names = [f"T{t}({self.names[t]})" for t in cycle + [cycle[0]]]
                        chain_str = " -> ".join(chain_names)
                        self.event(f"DEADLOCK DETECTED: {chain_str}. Cancelling T{victim}")

                        # Mark victim doomed and wake up all waiting threads so victim aborts
                        self.doomed.add(victim)
                        self.cv.notify_all()
                        continue

                # Sleep briefly to give the lock holder time to finish
                self.cv.wait(0.2)

            # Successfully acquired the lock
            self.waiting.pop(tx, None)
            self.owner[pid] = tx

    def _find_cycle(self, start):
        """Wait-for graph: follow 'who am I waiting for' arrows. Back at start = deadlock."""
        # Trace who is waiting for whom: Transaction -> Medicine -> Lock Holder -> Next Medicine...
        path = [start]
        current_tx = start

        while True:
            # Find which medicine this transaction is waiting for
            waited_pid = self.waiting.get(current_tx)
            if waited_pid is None:
                return None

            # Find which transaction owns that medicine
            next_tx = self.owner.get(waited_pid)
            if next_tx is None:
                return None

            # If we looped back to the start transaction, we found a circular deadlock!
            if next_tx == start:
                return path

            # If we hit an already visited node (different cycle), stop tracing
            if next_tx in path:
                return None

            # Follow the dependency arrow to the next transaction
            path.append(next_tx)
            current_tx = next_tx

    def release_all(self, tx):
        # Release all locks held by this transaction (Strict 2-Phase Locking rule)
        with self.cv:
            # Find every medicine owned by this transaction and delete the ownership entry
            held_medicines = [pid for pid, holder in self.owner.items() if holder == tx]
            for pid in held_medicines:
                del self.owner[pid]

            # Clean up waiting and doomed tracking
            self.waiting.pop(tx, None)
            self.doomed.discard(tx)

            # Wake up all waiting transactions so they can try to grab the freed locks
            self.cv.notify_all()

    def reset(self):
        # Clear all locks, wait queues, and doomed flags
        with self.cv:
            self.owner.clear()
            self.waiting.clear()
            self.doomed.clear()
            self.cv.notify_all()

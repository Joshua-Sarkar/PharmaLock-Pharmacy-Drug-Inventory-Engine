# OS SIDE - Buffer Pool: keeps recently accessed medicines in memory to avoid slow disk reads.
# Uses LRU (Least Recently Used) eviction when memory is full.
from collections import OrderedDict
import threading


class BufferPool:
    def __init__(self, disk, cap=4):
        self.disk = disk
        self.cap = cap
        # OrderedDict tracks usage order: front is oldest accessed, end is newest accessed
        self.pages = OrderedDict()
        self.hits = 0
        self.misses = 0
        # Reentrant lock allows the same thread to acquire it multiple times safely
        self.mu = threading.RLock()

    def get(self, pid):
        with self.mu:
            # Cache hit: record is already in memory
            if pid in self.pages:
                self.pages.move_to_end(pid)
                self.hits += 1
            else:
                # Cache miss: load from disk into memory
                self.misses += 1
                disk_record = self.disk.read(pid)
                self._put(pid, disk_record)

            # Return a copy so caller modifications don't corrupt cache without write()
            return dict(self.pages[pid])

    def write(self, pid, rec):
        # Write-through caching: write to disk immediately, then update cache
        with self.mu:
            self.disk.write(rec)
            self._put(pid, rec)

    def _put(self, pid, rec):
        # Store a fresh copy in memory and mark it as most recently used
        self.pages[pid] = dict(rec)
        self.pages.move_to_end(pid)

        # Evict oldest record if cache exceeds capacity (LRU policy)
        if len(self.pages) > self.cap:
            self.pages.popitem(last=False)

    # PHASE 3 FEATURE 4: EXPIRY RULE - refresh memory copies, soonest-to-expire medicine FIRST
    def refresh(self):
        # Reload cached items from disk, prioritized by nearest expiration date
        with self.mu:
            order = sorted(self.pages, key=lambda pid: self.pages[pid]["expiry"])
            for pid in order:
                self.pages[pid] = self.disk.read(pid)
            return order

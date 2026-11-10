# OS SIDE - Disk Manager: stores medicine records as fixed-size binary records in a single file.
import os
import struct
import threading

# Record layout: id (unsigned int), name (30 bytes), stock (signed int), expiry date (YYYYMMDD int) = 42 bytes.
# Fixed record sizes allow us to seek directly to any record in O(1) time without scanning.
REC = struct.Struct("<I30siI")


class DiskManager:
    def __init__(self, path):
        self.path = path
        # Create an empty file if it doesn't already exist
        if not os.path.exists(path):
            with open(path, "wb"):
                pass

        # Open in binary read-write mode
        self.f = open(path, "r+b")
        # Lock to protect file pointer seeks and reads/writes across multiple threads
        self.io = threading.Lock()

    def count(self):
        # Total records is file size divided by the fixed 42-byte record size
        file_size = os.path.getsize(self.path)
        return file_size // REC.size

    def write(self, r):
        # Jump directly to record position: record N starts at byte N * 42
        with self.io:
            offset = r["id"] * REC.size
            self.f.seek(offset)
            encoded_name = r["name"].encode()[:30]
            packed_bytes = REC.pack(r["id"], encoded_name, r["stock"], r["expiry"])
            self.f.write(packed_bytes)
            # Flush internal buffer so data leaves Python (WAL handles crash protection)
            self.f.flush()

    def read(self, pid):
        # Jump straight to the medicine record by ID
        with self.io:
            offset = pid * REC.size
            self.f.seek(offset)
            raw_bytes = self.f.read(REC.size)

        if len(raw_bytes) < REC.size:
            return None

        record_id, raw_name, stock, expiry = REC.unpack(raw_bytes)
        clean_name = raw_name.rstrip(b"\0").decode()
        return {
            "id": record_id,
            "name": clean_name,
            "stock": stock,
            "expiry": expiry,
        }

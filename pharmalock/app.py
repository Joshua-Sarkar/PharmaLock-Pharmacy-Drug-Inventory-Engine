# Flask web server: the frontend dashboard communicates with the backend engine via these JSON endpoints.
import threading
from flask import Flask, jsonify, request, send_from_directory
from pharmacy import Pharmacy, days_left
from transaction import SimulatedCrash

app = Flask(__name__, static_folder="static")
P = Pharmacy()


def body():
    """Extracts JSON body safely, returning an empty dictionary on error or empty body."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    return data


def attempt(action_fn, *args):
    """Executes an engine action and converts exceptions into structured 400 error responses."""
    try:
        tx_id = action_fn(*args)
        return jsonify(ok=True, tx=tx_id)
    except Exception as err:
        return jsonify(ok=False, error=str(err)), 400


def args():
    """Parses standard pharmacy request arguments from the incoming JSON payload."""
    payload = body()
    department = payload.get("dept", "Pharmacy")
    medicine_id = int(payload["pid"])
    quantity = max(1, int(payload.get("qty", 1)))
    hold_duration = min(10.0, float(payload.get("hold", 0.0)))
    return department, medicine_id, quantity, hold_duration


@app.get("/")
def home():
    """Serves the main frontend dashboard HTML."""
    return send_from_directory("static", "index.html")


@app.get("/api/state")
def state():
    """Provides a complete snapshot of database, memory cache, locks, and logs for the dashboard."""
    # Capture thread-safe lock state
    lock_mgr = P.locks
    with lock_mgr.cv:
        owners = dict(lock_mgr.owner)
        waiting = dict(lock_mgr.waiting)
        dept_names = dict(lock_mgr.names)

    # Format medicine list with calculated days remaining
    meds = []
    for item in P.check_stock():
        med_dict = dict(item)
        med_dict["days_left"] = days_left(item["expiry"])
        meds.append(med_dict)

    # Format the last 14 Write-Ahead Log entries for human readability
    recent_logs = P.log.read_all()[-14:]
    formatted_logs = []
    for rec in recent_logs:
        rec_type = rec.get("type", "")
        tx_id = rec.get("tx", "")
        entry = f"{rec_type} T{tx_id}"
        if rec_type == "UPDATE":
            entry += f" med#{rec['pid']} {rec['before']}->{rec['after']}"
        formatted_logs.append(entry)

    # Buffer pool stats
    pool_info = {
        "cap": P.pool.cap,
        "order": list(P.pool.pages.keys()),
        "hits": P.pool.hits,
        "misses": P.pool.misses,
    }

    return jsonify(
        meds=meds,
        owners=owners,
        waiting=waiting,
        names=dept_names,
        events=list(lock_mgr.events),
        log=formatted_logs,
        crashed=P.crashed,
        pool=pool_info,
    )


@app.post("/api/dispense")
def dispense():
    """Dispenses medicine stock to a department."""
    dept, pid, qty, hold = args()
    return attempt(P.dispense, dept, pid, qty, hold)


@app.post("/api/restock")
def restock():
    """Restocks medicine inventory from a supplier."""
    dept, pid, qty, hold = args()
    return attempt(P.restock, dept, pid, qty, hold)


@app.get("/api/expiry")
def expiry():
    """Returns medicines that expire within the requested number of days."""
    days = int(request.args.get("days", 30))
    expiring_medicines = P.check_expiry(days)
    return jsonify(expiring_medicines)


@app.post("/api/refresh")
def refresh():
    """Refreshes buffer pool pages sorted by earliest expiry date."""
    refreshed_ids = P.pool.refresh()
    medicine_names = [P.disk.read(pid)["name"] for pid in refreshed_ids]

    summary = ", ".join(medicine_names) if medicine_names else "(memory empty)"
    P.locks.event(f"Expiry refresh order: {summary}")

    return jsonify(order=medicine_names)


@app.post("/api/demo/deadlock")  # PHASE 3 FEATURE 2: two departments, two medicines, live
def deadlock():
    """Creates an intentional circular wait between Emergency and Surgery to demonstrate deadlock detection."""
    def worker(department, items):
        try:
            # Hold locks for 1.5s to reliably trigger the circular wait condition
            P.run(department, items, hold=1.5)
        except Exception:
            pass

    # Thread 1: Emergency grabs #0 (Paracetamol) then requests #1 (Amoxicillin)
    # Thread 2: Surgery grabs #1 (Amoxicillin) then requests #0 (Paracetamol)
    scenarios = [
        ("Emergency", [(0, -1), (1, -1)]),
        ("Surgery", [(1, -1), (0, -1)]),
    ]

    for dept, items in scenarios:
        thread = threading.Thread(target=worker, args=(dept, items), daemon=True)
        thread.start()

    return jsonify(ok=True)


@app.post("/api/demo/crash")  # PHASE 3 FEATURE 3: stop in the middle of a dispense
def crash():
    """Simulates a power failure mid-transaction before the COMMIT record is logged."""
    payload = body()
    pid = int(payload.get("pid", 0))
    qty = int(payload.get("qty", 10))

    try:
        P.run("Pharmacy", [(pid, -qty)], hold=0, crash=True)
        return jsonify(ok=True)
    except SimulatedCrash:
        # Stock was updated on disk, but power died before COMMIT was written
        current_disk_stock = P.disk.read(pid)["stock"]
        return jsonify(ok=True, disk=current_disk_stock)
    except Exception as err:
        return jsonify(ok=False, error=str(err)), 400


@app.post("/api/recover")
def recover():
    """Triggers WAL recovery pass to undo uncommitted transactions and restore consistency."""
    report = P.recover()
    return jsonify(ok=True, report=report)


@app.post("/api/stress")
def stress():
    """Runs concurrent stress test with N simultaneous requests."""
    requested_n = int(body().get("n", 150))
    safe_n = min(300, max(1, requested_n))
    results = P.stress(safe_n)
    return jsonify(results)


@app.post("/api/reset")
def reset():
    """Resets the database, WAL, memory cache, and locks to pristine initial state."""
    P.reset()
    return jsonify(ok=True)


if __name__ == "__main__":
    print("PharmaLock running -> open http://127.0.0.1:5000")
    app.run(port=5000, threaded=True)

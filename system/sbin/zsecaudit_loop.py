#!/usr/bin/env python3
import sys, time
import os as _os; sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "lib", "zenos")))
import zsecnote, zconf

LOCAL = _os.path.join(zconf.data(), "ledger.jsonl")
CON = _os.path.join(zconf.data(), "consortium.jsonl")
INTERVAL = 300   # periodic endpoint audit: anchor new edits, reconcile, verdict

while True:
    try:
        v, reasons, alerts = zsecnote.audit(LOCAL, CON)
        print("secaudit:", v, reasons, "attention=", alerts, flush=True)
    except Exception as e:
        print("secaudit error:", e, flush=True)
    time.sleep(INTERVAL)

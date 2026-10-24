#!/usr/bin/env python3
"""ZENOS security audit loop (user service): runs the Security Note endpoint audit (zsecnote) on a timer."""
import os, sys, time
# the ZENOS library is ../lib/zenos beside this program (/usr/lib/zenos, root-owned)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
import zsecnote, zconf

LOCAL = os.path.join(zconf.data(), "ledger.jsonl")
CON = os.path.join(zconf.data(), "consortium.jsonl")
INTERVAL = 300   # periodic endpoint audit: anchor new edits, reconcile, verdict

while True:
    try:
        v, reasons, alerts = zsecnote.audit(LOCAL, CON)
        print("secaudit:", v, reasons, "attention=", alerts, flush=True)
    except Exception as e:
        print("secaudit error:", e, flush=True)
    time.sleep(INTERVAL)

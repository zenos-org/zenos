#!/usr/bin/env python3
import sys, time
sys.path.insert(0, "/usr/local/lib/zenos")
import zsecnote

LOCAL = "/home/zenos/.local/share/zenos/ledger.jsonl"
CON = "/home/zenos/.local/share/zenos/consortium.jsonl"
INTERVAL = 300   # periodic endpoint audit: anchor new edits, reconcile, verdict

while True:
    try:
        v, reasons, alerts = zsecnote.audit(LOCAL, CON)
        print("secaudit:", v, reasons, "attention=", alerts, flush=True)
    except Exception as e:
        print("secaudit error:", e, flush=True)
    time.sleep(INTERVAL)

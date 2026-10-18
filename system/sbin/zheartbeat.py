#!/usr/bin/env python3
"""ZENOS sensor liveness (dead-man's switch, PoC).

emitter: stands in for the resident sensor. Writes a heartbeat every INTERVAL seconds.
watcher: stands in for ANOTHER node. If the heartbeat goes stale past TIMEOUT, it raises an alarm
         and writes it to the tamper-evident ledger. Silencing the sensor is therefore itself the
         loudest event, and the alarm lives on a different node than the one being attacked.
"""
import os, sys, time
import os as _os; sys.path.insert(0, _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "lib", "zenos")))
import zledger
try:
    import zalarm
except Exception:
    zalarm = None

HB = "/run/zenos-sensor.hb"
LEDGER = "/var/log/zenos/access-ledger.jsonl"
INTERVAL = 1.0
TIMEOUT = 3.0


def emitter():
    while True:
        open(HB, "w").write(str(time.time()))
        time.sleep(INTERVAL)


def watcher(run_sec):
    run_sec = float(run_sec)
    forever = run_sec <= 0
    t0 = time.time()
    alarmed = False
    while forever or time.time() - t0 < run_sec:
        try:
            age = time.time() - float(open(HB).read().strip())
        except Exception:
            age = 999
        if age <= TIMEOUT and alarmed:
            zledger.append(LEDGER, 'sensor-recovered', 'node-B', 'watcher', target='node-A')
            print('recovered: heartbeat fresh again', flush=True); alarmed = False  # re-arm
        if age > TIMEOUT and not alarmed:
            detect = round(age, 2)
            zledger.append(LEDGER, "sensor-silenced", "node-B", "watcher",
                           target="node-A", stale_sec=detect, action="escalate")
            print("ALARM: sensor silenced, heartbeat stale %.2fs -> escalate" % detect, flush=True)
            if zalarm is not None:
                try:
                    zalarm.raise_alert("red", "ZENOS RED ALERT", "sensor silenced %.2fs -> escalate" % detect)
                except Exception:
                    pass
            alarmed = True
        time.sleep(0.5)
    if not alarmed:
        print("no alarm: heartbeat stayed fresh", flush=True)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])

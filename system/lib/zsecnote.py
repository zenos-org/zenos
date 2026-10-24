#!/usr/bin/env python3
"""ZENOS Security Note (PoC): periodic endpoint audit with a hard local<->consortium reconciliation.

Soft (management metadata, NOT a security root; a compromised endpoint can lie about these):
  hostname, kernel, connected block/USB devices + models.
Hard (the trust root; a compromised endpoint cannot retroactively match its own past anchors):
  1. local ledger self-integrity        (zledger.verify)
  2. consortium ledger self-integrity    (zledger.verify)
  3. local <-> consortium reconciliation (zanchor.verify_anchor)  <- the "double check"
  4. sensor liveness                      (heartbeat freshness)
Verdict: trusted | SUSPECT(reasons). Any hard check failing => the endpoint's OS may be modified.
The audit first anchors new local edits (the scheduler), then reconciles. Verdict is logged.
"""
import os, socket, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zledger, zanchor, zalarm

HB = "/run/zenos-sensor.hb"
HB_MAX = 10.0      # same limit as the dead-man watcher (zenos_heartbeat.TIMEOUT)


def inventory():
    inv = {"host": socket.gethostname()}
    try:
        inv["kernel"] = subprocess.check_output(["uname", "-r"], text=True).strip()
    except Exception:
        inv["kernel"] = "?"
    devs = []
    try:
        for b in sorted(os.listdir("/sys/block")):
            model = "?"
            mp = "/sys/block/%s/device/model" % b
            if os.path.exists(mp):
                model = open(mp).read().strip()
            devs.append({"dev": b, "model": model})
    except Exception:
        pass
    inv["block_devices"] = devs
    return inv


def hb_age():
    for attempt in range(3):              # an older sensor rewrote the file in place: retry a torn read
        try:
            with open(HB) as f:
                return time.time() - float(f.read().strip())
        except (OSError, ValueError):
            time.sleep(0.2)
    return 1e9


# --- machine health (we watch the COMPUTER, not the person) ---
GPU_BUSY = 50      # % utilization that is abnormal for deskwork
GPU_HOT = 75       # degrees C
CPU_HOT = 0.85     # load1 / ncpu

NET_TX_HI = 5 * 1024 * 1024   # bytes/sec outbound that is abnormal for deskwork

def net_rates(interval=1.0):
    """Task-Manager-style whole-machine throughput: bytes/sec tx/rx across non-lo interfaces."""
    def snap():
        tx = rx = 0
        for line in open("/proc/net/dev").read().splitlines()[2:]:
            name, _, data = line.partition(":")
            if name.strip() == "lo":
                continue
            f = data.split()
            if len(f) >= 16:
                rx += int(f[0]); tx += int(f[8])
        return rx, tx
    import time as _t
    r0, t0 = snap(); _t.sleep(interval); r1, t1 = snap()
    return {"tx_bps": int((t1 - t0) / interval), "rx_bps": int((r1 - r0) / interval)}


def health():
    h = {}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"], text=True, timeout=5).strip().splitlines()[0]
        u, t = [x.strip() for x in out.split(",")]
        h["gpu_util"] = int(u); h["gpu_temp"] = int(t)
    except Exception:
        h["gpu_util"] = None; h["gpu_temp"] = None
    try:
        load1 = float(open("/proc/loadavg").read().split()[0])
        h["cpu_ratio"] = round(load1 / (os.cpu_count() or 1), 2)
    except Exception:
        h["cpu_ratio"] = None
    try:
        h.update(net_rates())
    except Exception:
        h["tx_bps"] = None; h["rx_bps"] = None
    return h

def health_alerts(h, deskwork=True):
    a = []
    if deskwork and h.get("gpu_util") is not None and h["gpu_util"] >= GPU_BUSY:
        a.append("gpu-busy-while-deskwork")        # mining / remote compute / exfil signature
    if h.get("gpu_temp") is not None and h["gpu_temp"] >= GPU_HOT:
        a.append("gpu-overheat")
    if h.get("cpu_ratio") is not None and h["cpu_ratio"] >= CPU_HOT:
        a.append("cpu-sustained-high")
    if deskwork and h.get("tx_bps") is not None and h["tx_bps"] >= NET_TX_HI:
        a.append("sustained-outbound-high")
    return a


def audit(local_ledger, consortium_ledger, actor="secnote", device="node-A"):
    zanchor.anchor(local_ledger, consortium_ledger, actor, device)   # scheduler: anchor new edits first
    reasons = []
    if not zledger.verify(local_ledger)[0]:
        reasons.append("local-ledger-broken")
    if not zledger.verify(consortium_ledger)[0]:
        reasons.append("consortium-ledger-broken")
    if not zanchor.verify_anchor(local_ledger, consortium_ledger)[0]:
        reasons.append("local-vs-consortium-mismatch")
    if hb_age() > HB_MAX:
        reasons.append("sensor-silent")
    verdict = "trusted" if not reasons else "SUSPECT"
    hw = health(); alerts = health_alerts(hw)
    zledger.append(consortium_ledger, "endpoint-audit", actor, device,
                   verdict=verdict, reasons=reasons, attention=alerts,
                   health=hw, inventory=inventory())
    if verdict == "SUSPECT":
        zalarm.raise_alert("red", "ZENOS RED ALERT", "Endpoint integrity check failed: " + ", ".join(reasons))
    elif alerts:
        zalarm.raise_alert("low", "ZENOS notice", "Device attention: " + ", ".join(alerts))
    return verdict, reasons, alerts


if __name__ == "__main__":
    v, r = audit(sys.argv[1], sys.argv[2])
    print(v, r)

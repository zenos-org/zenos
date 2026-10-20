#!/usr/bin/env python3
"""ZENOS security monitor feed (root service).

Counts what the System Monitor's Security graph shows and raises plain alerts. Nothing leaves the machine.
  inbound  : new inbound TCP connections dropped by the ZENOS_IN firewall chain (packet counter), and the
             source/port of each from the rate-limited "ZENOS_IN_DROP " kernel log line
  contained: outbound destinations the network sentinel cut (ZENOS_OUT rules) and its incidents log
  sign-in  : failed passwords (sudo, su, login screen, lock screen, ssh) from the system journal
Alerts (deterministic thresholds, no AI): port scan, inbound burst, repeated failed sign-ins, sentinel incident,
firewall missing. Written every 2 s to /run/zenos/secstat.json (world-readable, no secrets in it).
"""
import json, os, re, subprocess, threading, time
from collections import deque, Counter

OUT = "/run/zenos/secstat.json"
INCIDENTS = "/var/log/zenos/incidents.jsonl"
SCAN_PORTS, SCAN_WIN = 10, 60          # one source touching >= 10 different ports within 60 s
BURST_N, BURST_WIN = 50, 60            # >= 50 blocked attempts within 60 s
AUTH_N, AUTH_WIN = 5, 300              # >= 5 failed sign-ins within 5 min
QUIET = 600                            # the same alert is not repeated for 10 min
# one line per wrong password: PAM's own record (sudo, su, login screen, lock screen and ssh all go through PAM);
# the summaries sudo/sshd add on top ("incorrect password attempts", "Failed password") would count it twice
AUTH_RE = re.compile(r"pam_\w+\([\w-]+:auth\): authentication failure", re.I)
DROP_RE = re.compile(r"ZENOS_IN_DROP .*?SRC=(\S+) .*?PROTO=(\S+)(?: .*?DPT=(\d+))?")
SAFE = re.compile(r"[^0-9A-Za-z.:_ -]")

lock = threading.Lock()
drops = deque(maxlen=2000)             # (t, src, port) from the kernel log
auth = deque(maxlen=500)               # (t, service)
alerts = deque(maxlen=20)
last_alert = {}
auth_total = 0
start = time.time()


def sh(*a):
    return subprocess.run(a, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout


def chain_counts(chain, target):
    """packets matched by rules with this target in this chain, IPv4 + IPv6; None if the chain is missing"""
    total, seen = 0, False
    for ipt in ("iptables", "ip6tables"):
        out = sh(ipt, "-w", "-nvxL", chain)
        if not out.startswith("Chain"):
            continue
        seen = True
        for line in out.splitlines()[2:]:
            f = line.split()
            if len(f) > 2 and f[2] == target:
                total += int(f[0])
    return total if seen else None


def alert(key, sev, title, text):
    now = time.time()
    if now - last_alert.get(key, 0) < QUIET:
        return
    last_alert[key] = now
    alerts.append({"id": "%d-%s" % (int(now * 1000), key.split(":")[0]), "t": int(now), "sev": sev,
                   "title": title, "text": SAFE.sub("", text)[:160]})


def journal():
    global auth_total
    while True:
        p = subprocess.Popen(["journalctl", "-f", "-n", "0", "-o", "json"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        for line in p.stdout:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("MESSAGE")
            if not isinstance(msg, str):
                continue
            now = time.time()
            if e.get("_TRANSPORT") == "kernel":
                m = DROP_RE.search(msg)
                if m:
                    with lock:
                        drops.append((now, m.group(1), m.group(3) or m.group(2)))
            elif AUTH_RE.search(msg):
                svc = e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "system"
                with lock:
                    auth.append((now, svc)); auth_total += 1
        time.sleep(2)


def incidents_since(pos):
    try:
        with open(INCIDENTS) as f:
            f.seek(pos)
            new = f.read()
            return f.tell(), [json.loads(l) for l in new.splitlines() if l.strip()]
    except (OSError, ValueError):
        return pos, []


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    threading.Thread(target=journal, daemon=True).start()
    try:
        pos = os.path.getsize(INCIDENTS)
    except OSError:
        pos = 0
    base_in = base_out = None
    contained_total = 0
    hist_in, hist_auth = deque(maxlen=60), deque(maxlen=60)
    prev_in, prev_auth = None, 0
    while True:
        now = time.time()
        tin = chain_counts("ZENOS_IN", "DROP")
        tout = chain_counts("ZENOS_OUT", "DROP") or 0
        fw_ok = tin is not None
        if fw_ok and base_in is None:
            base_in = tin
        if base_out is None:
            base_out = tout
        blocked = (tin - base_in) if fw_ok else 0
        if blocked < 0:                  # chain was re-created: counters restart
            base_in, blocked = tin, 0
        if not fw_ok:
            alert("fw", "red", "Firewall is off", "The inbound lockdown chain ZENOS_IN is missing.")
        pos, inc = incidents_since(pos)
        for r in inc:
            ty = r.get("type", "")
            if ty == "egress":
                contained_total += 1
                alert("inc:egress:%s" % r.get("dst"), "red", "Outbound connection cut",
                      "Unapproved data to %s:%s was stopped by the sentinel." % (r.get("dst", "?"), r.get("port", "?")))
            elif ty == "listener":
                contained_total += 1
                alert("inc:listener:%s" % r.get("port"), "red", "Unexpected listening port closed",
                      "A program opened port %s to outside connections; the sentinel contained it." % r.get("port", "?"))
            elif ty == "firewall-tamper":
                alert("inc:fw", "red", "Firewall was changed", "Someone removed the inbound lockdown. It was put back.")
        with lock:
            d60 = [x for x in drops if now - x[0] <= SCAN_WIN]
            a5 = [x for x in auth if now - x[0] <= AUTH_WIN]
            at = auth_total
            ports = {}
            for _, src, port in d60:
                ports.setdefault(src, set()).add(port)
            for src, ps in ports.items():
                if len(ps) >= SCAN_PORTS:
                    alert("scan:" + src, "amber", "Port scan blocked",
                          "%s tried %d ports in the last minute. All were dropped." % (src, len(ps)))
            if len(d60) >= BURST_N:
                alert("burst", "amber", "Many connection attempts",
                      "%d inbound attempts in the last minute. All were dropped." % len(d60))
            if len(a5) >= AUTH_N:
                c = Counter(s for _, s in a5).most_common(1)[0][0]
                alert("auth", "amber", "Repeated failed sign-ins",
                      "%d wrong passwords in 5 minutes, via %s." % (len(a5), c))
            top = Counter(s for t, s, p in drops if now - t <= 3600).most_common(3)
            recent = [{"t": int(t), "src": s, "port": p} for t, s, p in list(drops)[-5:]]
            al = list(alerts)
        hist_in.append(0 if prev_in is None else max(0, blocked - prev_in)); prev_in = blocked
        hist_auth.append(max(0, at - prev_auth)); prev_auth = at
        state = {"t": int(now), "since": int(start), "firewall": fw_ok,
                 "inbound_blocked": blocked, "outbound_contained": max(0, tout - base_out) + contained_total,
                 "auth_failed": at, "h_in": list(hist_in), "h_auth": list(hist_auth),
                 "top_sources": [{"src": s, "n": n} for s, n in top], "recent": recent, "alerts": al}
        tmp = OUT + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.chmod(tmp, 0o644)
        os.replace(tmp, OUT)
        time.sleep(2)


if __name__ == "__main__":
    main()

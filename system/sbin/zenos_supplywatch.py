#!/usr/bin/env python3
"""ZENOS: watch the places updates arrive (root).

apt's download folder (/var/cache/apt/archives) is where every package waits before it is installed: the same role
as the Windows update folder where NetamLoader was found. A file that appears there is checked at once: a package
file must be in the release ledger (zsupply.py, the same proven decision as apt's own check); anything that is not a
package file does not belong there. Either is moved to /var/lib/zenos/quarantine (root only), written to the PC's
ledger as "supply-alert" (the audit nodes alert the officers) and, with "mode": "enforce", never installed.

Watched: /var/cache/apt/archives, /var/lib/zenos/updates (ZENOS's own updates, when used).
"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
import zdecide, zsupply                                         # noqa: E402
try:
    import zledger                                              # noqa: E402
except Exception:
    zledger = None

WATCH = [p for p in os.environ.get("ZENOS_SUPPLY_WATCH", "/var/cache/apt/archives:/var/lib/zenos/updates").split(":") if p]
QUARANTINE = Path(os.environ.get("ZENOS_QUARANTINE", "/var/lib/zenos/quarantine"))
LEDGER = os.environ.get("ZENOS_SUPPLYWATCH_LEDGER", "/var/log/zenos/access-ledger.jsonl")
EXPECTED = {"lock", "partial"}


def record(event, **kw):
    if zledger is not None:
        try:
            zledger.append(LEDGER, event, "root", "supplywatch", **kw)
        except Exception:
            pass


def quarantine(path, why):
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    os.chmod(QUARANTINE, 0o700)
    dst = QUARANTINE / f"{int(time.time())}-{os.path.basename(path)}"
    try:
        sha = zsupply.sha256_file(path)
        shutil.move(path, dst)
        os.chmod(dst, 0o600)
    except OSError as e:
        sha = None
        why += f" (could not move: {e})"
    record("supply-alert", file=str(path), reason=why, sha256=sha, quarantined=str(dst))
    print(json.dumps({"event": "supply-alert", "path": str(path), "reason": why}), flush=True)


def inspect(path, c=None, get=zsupply.fetch):
    """'ok', 'skipped' or 'quarantined'"""
    path = str(path)
    name = os.path.basename(path)
    if name in EXPECTED or not os.path.isfile(path) or os.path.islink(path):
        return "skipped"
    if os.path.basename(os.path.dirname(path)) == "partial":
        return "skipped"                                   # still downloading; checked when apt moves it in
    c = c or zsupply.conf()
    if c.get("mode", "off") == "off":
        return "skipped"
    if not name.endswith(".deb"):
        quarantine(path, "not a package file, in a folder that holds only package files")
        return "quarantined"
    try:
        ok, why, f = zsupply.decide(path, zsupply.audit_nodes(), zsupply.officers(), c.get("required", 2),
                                    c.get("ring", 1), get=get)
        reachable = f.get("_reachable", 0)
    except Exception as e:
        ok, why, reachable = False, f"unreadable package: {e}", 1
    if ok:
        return "ok"
    if not reachable:
        # no audit node answered (an outage): no verdict, so nothing is moved; apt's own check will refuse it
        record("supply-unverified", file=path, reason=why)
        return "unverified"
    if c.get("mode") == "enforce":
        quarantine(path, f"not in the release ledger as required ({why})")
        return "quarantined"
    record("supply-warning", file=path, reason=why)
    return "ok"


def main():
    for d in WATCH:
        os.makedirs(d, exist_ok=True)
    # watch first, then look at what is already there: nothing that arrives during the first look is missed
    p = subprocess.Popen(["inotifywait", "-m", "-q", "-e", "close_write", "-e", "moved_to", "--format", "%w%f", *WATCH],
                         stdout=subprocess.PIPE, text=True)
    time.sleep(1)
    for d in WATCH:
        for f in sorted(os.listdir(d)):
            inspect(os.path.join(d, f))
    for line in p.stdout:
        if os.path.exists(line.rstrip("\n")):
            inspect(line.rstrip("\n"))
    return p.wait()


if __name__ == "__main__":
    sys.exit(main())

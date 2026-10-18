#!/usr/bin/env python3
"""ZENOS anomaly monitor (PoC).

Watches the security folders and the external exit (USB Drive). When an operation looks like a leak,
it stops at once: the processes involved are frozen, what reached the exit is quarantined, the screen
is locked, and an emergency release request goes to the officers.
If the same operation was pre-filed and approved, it is allowed and only recorded.

Rules
  exfiltration   a protected file (L2 or higher) reaches the USB Drive
  bulk-transfer  5 or more files reach the USB Drive within 30 seconds
  bulk-read      6 or more different protected files are opened within 20 seconds
Production: fanotify (with the process id) in a root service, plus network and messenger egress.
"""
import json, os, shutil, signal, subprocess, sys, time
from collections import deque
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zenos

BULK_READ_N, BULK_READ_SEC = 6, 20
BULK_XFER_N, BULK_XFER_SEC = 5, 30
SPARE = {"plasmashell", "kwin_x11", "Xvnc", "Xtigervnc", "systemd", "dbus-daemon", "kded6", "ksmserver",
         "inotifywait", "python3", "bash", "sh", "kdialog", "startplasma-x11"}
BIN = Path(__file__).resolve().parent
RULE_TEXT = {"exfiltration": "a protected file was copied to the USB Drive",
             "bulk-transfer": "many files were copied to the USB Drive at once",
             "bulk-read": "many protected files were opened at once"}

reads = deque()        # (time, path) of protected files opened
xfers = deque()        # (time, path) of files that reached the USB Drive
recent_write = {}      # path -> time; opens right after a write are the guard checking it, not a read


def level_of(p):
    try:
        if p.suffix == ".zen":
            return zenos.parse(p.read_bytes())[0]["level"]
    except Exception:
        pass
    return 1


def in_security(p):
    return p.parent.parent == zenos.DESK and p.parent.name in zenos.FOLDERS


def holders(paths):
    """Processes that have the watched folders open (PoC: inotify gives no pid, so scan /proc)."""
    roots = [str(zenos.USB)] + [str(zenos.DESK / n) for n in zenos.FOLDERS]
    me, out = os.getpid(), []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == me:
            continue
        try:
            comm = (d / "comm").read_text().strip()
            if comm in SPARE:
                # python3/bash are spared only when they are ZENOS itself or the desktop
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
                if comm not in ("python3", "bash", "sh") or (str(BIN) + "/") in cmd:
                    continue
            hit = False
            for fd in (d / "fd").iterdir():
                t = os.readlink(fd)
                if any(t.startswith(r) for r in roots):
                    hit = True
                    break
            if not hit:
                cwd = os.readlink(d / "cwd")
                hit = any(cwd.startswith(r) for r in roots)
            if hit:
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore").strip()
                out.append({"pid": int(d.name), "comm": comm, "cmd": cmd[:120]})
        except Exception:
            continue
    return out


def quarantine(paths, hid):
    q = zenos.QUAR / hid
    q.mkdir(parents=True, exist_ok=True)
    moved = []
    for p in paths:
        try:
            if p.exists() and p.parent == zenos.USB:
                shutil.move(str(p), q / p.name)
                moved.append(p.name)
        except Exception:
            pass
    return moved


def halt(rule, paths, level):
    hid = time.strftime("%Y%m%d-%H%M%S")
    procs = holders(paths)
    for pr in procs:                      # stop first, then record
        try:
            os.kill(pr["pid"], signal.SIGSTOP)
        except Exception:
            pass
    moved = quarantine(paths, hid)
    r = zenos.new_request("release", level, zenos.release_required(level), RULE_TEXT[rule],
                          scope={"halt": hid, "rule": rule, "files": [p.name for p in paths][:20]})
    h = {"id": hid, "status": "halted", "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rule": rule,
         "rule_text": RULE_TEXT[rule], "level": level, "files": [p.name for p in paths][:20],
         "quarantined": moved, "pids": procs, "request": r["id"], "code": r["code"], "required": r["required"]}
    zenos.CFG.mkdir(parents=True, exist_ok=True)
    zenos.HALT.write_text(json.dumps(h, ensure_ascii=False, indent=1))
    zenos.audit("anomaly", rule=rule, level=level, files=h["files"], halt=hid)
    zenos.audit("halt", halt=hid, frozen=[f"{p['comm']}:{p['pid']}" for p in procs], quarantined=moved,
                request=r["id"], required=r["required"])
    subprocess.Popen([sys.executable, "-I", str(BIN / "zenos_lock.py")], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def permitted(rule, paths, level):
    """A pre-filed, approved operation is not stopped. It is recorded and counted against its quota."""
    p, g = zenos.active_plan(rule, level)
    if not p:
        return False
    zenos.use_plan(p, g, 1)
    if rule == "usb-export":   # the copy had to open its source: those opens belong to the approved operation
        names = {x.name for x in paths}
        for item in [r for r in reads if r[1].name in names]:
            reads.remove(item)
    zenos.audit("anomaly-permitted", rule=rule, level=level, files=[x.name for x in paths][:20],
                plan=g["request"], used=g["used"], max_files=g["core"]["scope"]["max_files"])
    return True


def on_event(ev, p):
    now = time.time()
    if zenos.halted():
        # while stopped, anything else reaching the exit is quarantined straight away
        if p.parent == zenos.USB and ("CLOSE_WRITE" in ev or "MOVED_TO" in ev):
            h = zenos.halted()
            moved = quarantine([p], h["id"])
            if moved:
                zenos.audit("quarantine", halt=h["id"], files=moved)
        return
    if "CLOSE_WRITE" in ev or "MOVED_TO" in ev:
        recent_write[str(p)] = now
        if p.parent != zenos.USB or p.name.startswith(".") or p.suffix in (".part", ".tmp"):
            return
        lvl = level_of(p)
        while xfers and now - xfers[0][0] > BULK_XFER_SEC:
            xfers.popleft()
        # only files that no approved operation covers are counted, stopped and quarantined
        if lvl >= 2:
            if not permitted("usb-export", [p], lvl):
                halt("exfiltration", [x for _, x in xfers if x.exists()] + [p], lvl)
            return
        xfers.append((now, p))
        if len(xfers) >= BULK_XFER_N:
            if permitted("usb-export", [p], lvl):
                xfers.pop()
            else:
                halt("bulk-transfer", [x for _, x in xfers], max(level_of(x) for _, x in xfers))
        return
    if "OPEN" in ev and p.suffix == ".zen" and in_security(p):
        if now - recent_write.get(str(p), 0) < 5:
            return
        reads.append((now, p))
        while reads and now - reads[0][0] > BULK_READ_SEC:
            reads.popleft()
        distinct = {str(x) for _, x in reads}
        if len(distinct) >= BULK_READ_N:
            files = [Path(x) for x in distinct]
            lvl = max(level_of(x) for x in files)
            reads.clear()
            if not permitted("bulk-read", files, lvl):
                halt("bulk-read", files, lvl)


def main():
    zenos.USB.mkdir(parents=True, exist_ok=True)
    d = zenos.USB / ".directory"
    if not d.exists():
        d.write_text(f"[Desktop Entry]\nIcon={zenos.Z}/icons/zenos-usb.svg\n")
    zenos.audit("sentinel-start")
    if zenos.halted():   # a stop survives a restart: the lock comes back
        subprocess.Popen([sys.executable, "-I", str(BIN / "zenos_lock.py")], start_new_session=True)
    w = subprocess.Popen(["inotifywait", "-m", "-r", "-q", "-e", "open", "-e", "close_write", "-e", "moved_to",
                          "--format", "%e|%w%f", str(zenos.DESK)], stdout=subprocess.PIPE, text=True)
    for line in w.stdout:
        try:
            ev, path = line.rstrip("\n").split("|", 1)
            on_event(ev, Path(path))
        except Exception as e:
            print("sentinel:", e, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()

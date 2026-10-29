#!/usr/bin/env python3
"""ZENOS restart window (root, run hourly by zenos-restartwindow.timer): a kernel fix takes effect only after a
restart, so a PC that has one waiting is restarted at a moment nobody loses work.

Policy, /etc/zenos/policy.conf:
  kernel_restart = no-session   (default) restart when a fix is waiting and nobody is signed in to the PC
  kernel_restart = idle         also restart between 01:00 and 05:00 when every session has been idle for an hour
  kernel_restart = off          never restart by itself (the monitor and the audit nodes still show the fix waiting)
A waiting fix is /run/reboot-required (written by Debian's package scripts) or a newer kernel installed than the
one running. Every restart it makes, and every one it holds back, is written to the ledger.
  zenos_restartwindow.py          decide and act
  zenos_restartwindow.py --dry    decide and print, do nothing
"""
import glob, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
try:
    import zledger
except Exception:
    zledger = None

POLICY = os.environ.get("ZENOS_POLICY", "/etc/zenos/policy.conf")
FLAG = os.environ.get("ZENOS_REBOOT_FLAG", "/run/reboot-required")
LEDGER = "/var/log/zenos/access-ledger.jsonl"
STATE = os.environ.get("ZENOS_RESTART_STATE", "/var/lib/zenos/restartwindow.json")
MODES = ("no-session", "idle", "off")
IDLE_SEC = 3600
NIGHT = range(1, 5)        # 01:00-04:59 local time


def policy():
    mode = "no-session"
    try:
        with open(POLICY) as f:
            for line in f:
                k, _, v = line.split("#", 1)[0].partition("=")
                if k.strip() == "kernel_restart" and v.strip() in MODES:
                    mode = v.strip()
    except OSError:
        pass
    return mode


def vkey(s):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def newest_kernel(boot="/boot"):
    ks = [os.path.basename(p)[len("vmlinuz-"):] for p in glob.glob(os.path.join(boot, "vmlinuz-*"))]
    return max(ks, key=vkey) if ks else None


def fix_waiting(running=None, newest=None, flag=None):
    running = running or os.uname().release
    newest = newest if newest is not None else newest_kernel()
    if os.path.exists(flag or FLAG):
        return True, "restart-required flag"
    if newest and vkey(newest) > vkey(running):
        return True, "kernel %s installed, %s running" % (newest, running)
    return False, ""


def sessions():
    """[(id, class, idle, idle_since_epoch_seconds)] for every logind session"""
    out = []
    r = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        sid = line.split()[0] if line.split() else None
        if not sid:
            continue
        p = subprocess.run(["loginctl", "show-session", sid, "-p", "Class", "-p", "IdleHint", "-p", "IdleSinceHint"],
                           capture_output=True, text=True).stdout
        kv = dict(l.split("=", 1) for l in p.splitlines() if "=" in l)
        out.append((sid, kv.get("Class", ""), kv.get("IdleHint") == "yes", int(kv.get("IdleSinceHint") or 0) / 1e6))
    return out


def decide(mode, waiting, sess, now, hour):
    """(restart?, reason). Pure: the tests call it directly."""
    if not waiting:
        return False, "no fix waiting"
    if mode == "off":
        return False, "policy off"
    users = [s for s in sess if s[1] in ("user", "user-early", "user-incomplete")]
    if not users:
        return True, "nobody signed in"
    if mode == "idle" and hour in NIGHT and all(s[2] and s[3] and now - s[3] >= IDLE_SEC for s in users):
        return True, "night, every session idle for an hour"
    return False, "%d session(s) in use" % len(users)


def main():
    mode = policy()
    waiting, why = fix_waiting()
    sess = sessions() if waiting else []
    go, reason = decide(mode, waiting, sess, time.time(), time.localtime().tm_hour)
    key = "%s>%s" % (os.uname().release, newest_kernel())
    try:
        with open(STATE) as f:
            last = json.load(f).get("restarted_for")
    except (OSError, ValueError):
        last = None
    if go and last == key and "flag" not in why:
        go, reason = False, "already restarted once for this kernel and it is still not running: check the boot entry"
    rec = {"policy": mode, "waiting": why, "decision": reason, "restart": go}
    print(json.dumps(rec))
    if "--dry" in sys.argv or not waiting:
        return
    if zledger is not None:
        try:
            zledger.append(LEDGER, "kernel-restart" if go else "kernel-restart-held", "restartwindow", "restartwindow", **rec)
        except Exception:
            pass
    if go:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w") as f:
            json.dump({"restarted_for": key, "t": time.time()}, f)
        subprocess.run(["systemctl", "reboot"])


if __name__ == "__main__":
    main()

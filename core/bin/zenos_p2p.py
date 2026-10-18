#!/usr/bin/env python3
"""ZENOS Vault: sealed files are also stored across the storage grid (P2P).

What happens
  - Every .zen file that settles in a security folder is copied to the grid in the background:
    encrypted again with a fresh per-file key, erasure-coded 3-of-5, one shard per storage node.
    Any 3 nodes are enough to restore. Storage nodes never hold a key.
  - The capability (the per-file key that restores a copy) is kept in an index entry that is itself
    sealed with the SAME level key as the file. An L4 file's capability can only be read by an L4 session.
  - Nothing that can restore a file is written to the audit log: the log gets metadata only.
  - The name sent to storage nodes is an opaque id, not the file name.
  - "Vault" lists the files the current session level is cleared to see and restores any version.

Commands (run as the ZENOS user)
  zenos_p2p.py setup            create the local grid (admin key, 5 test nodes with certificates)
  zenos_p2p.py grid-start | grid-stop | grid-status
  zenos_p2p.py backup FILE      store one .zen file (the guard calls this after every check)
  zenos_p2p.py backup-all       store every .zen file in the security folders (rate-limited)
  zenos_p2p.py list             files visible at the session level (JSON)
  zenos_p2p.py restore NAME [--version N] [--to DIR]
  zenos_p2p.py vault            the Vault window (kdialog)
  zenos_p2p.py status           grid status window

PoC notes
  - The grid admin key lives on this machine (p2p/admin.json). In production it stays off the machine.
  - Level keys are read from disk like the rest of the PoC. In production they come from the FIDO2 device.
"""
import base64, fcntl, hashlib, json, os, secrets, signal, socket, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zenos  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

P2P = zenos.Z / "p2p"
INDEX = P2P / "index"
LOCKS = P2P / "locks"
TMP = P2P / "tmp"
RUN = P2P / "run"
LOGS = P2P / "logs"
NODES = P2P / "nodes"
CONF = P2P / "grid.json"
STORE = Path(os.environ.get("ZENOS_STORE", str(zenos.Z / "store"))) / "bin" / "zenos.js"
NODEJS = os.environ.get("ZENOS_NODEJS", "node")
MAX_VERSIONS = 50

# Test nodes inside this machine. Neutral labels: not connected to any real organisation.
DEFAULT_NODES = [
    ("Node A", "node-a"),
    ("Node B", "node-b"),
    ("Node C", "node-c"),
    ("Node D", "node-d"),
    ("Node E", "node-e"),
]


# ---------------- storage layer ----------------

def conf():
    return json.loads(CONF.read_text())


def grid_args(c):
    return ["--grid", c["grid"], "--bootstrap", c["bootstrap"], "--host", c["host"], "--admin", c["admin"]]


def store(args, stdin=None, timeout=120, grid=True):
    cmd = [NODEJS, str(STORE), *args, *(grid_args(conf()) if grid else []), "--json"]
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("{")]
    try:
        res = json.loads(lines[-1])
    except Exception:
        res = {"ok": False, "error": (r.stderr or r.stdout).strip()[-400:] or "no output"}
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "storage layer error"))
    return res


def store_text(args):
    r = subprocess.run([NODEJS, str(STORE), *args], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


# ---------------- index (sealed at the file's level) ----------------

def entry_key(folder, name):
    return hashlib.sha256(f"{folder}/{name}".encode()).hexdigest()[:32]


def unseal(blob):
    """Verify the device signature and decrypt with the level key. Callers check the session level first."""
    h, hb, sig, ct = zenos.parse(blob)
    zenos.verify(hb, sig, ct)
    data = zenos.decrypt_ct(h, hb, ct, sig=sig)
    return h, data


def read_entry(key):
    p = INDEX / f"{key}.zen"
    if not p.exists():
        return None
    _, data = unseal(p.read_bytes())
    return json.loads(data)


def write_entry(key, entry):
    INDEX.mkdir(parents=True, exist_ok=True)
    p = INDEX / f"{key}.zen"
    tmp = INDEX / f".{key}.{secrets.token_hex(4)}.tmp"
    tmp.write_bytes(zenos.seal(json.dumps(entry, ensure_ascii=False).encode(), entry["level"], "vault-index"))
    os.chmod(tmp, 0o600)
    tmp.replace(p)


def visible_entries(level=None):
    """Index entries whose level is at or below the session level. Higher entries are never decrypted."""
    s = zenos.session_level() if level is None else level
    out = []
    for p in sorted(INDEX.glob("*.zen")) if INDEX.exists() else []:
        try:
            h, *_ = zenos.parse(p.read_bytes())
            if h["level"] > s:
                continue
            out.append(read_entry(p.stem))
        except Exception:
            zenos.audit("vault-index-invalid", entry=p.name)
    return out


# ---------------- backup ----------------

class Lock:
    def __init__(self, key):
        LOCKS.mkdir(parents=True, exist_ok=True)
        self.f = open(LOCKS / f"{key}.lock", "w")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def enabled():
    return (P2P / "enabled").exists() and CONF.exists()


def backup(path, quiet=False):
    p = Path(path)
    if not enabled() or not p.is_file() or p.suffix != ".zen" or not zenos.folder_range(p):
        return {"skipped": "not a sealed file in a security folder"}
    blob = p.read_bytes()
    try:
        h, hb, sig, ct = zenos.parse(blob)
        zenos.verify(hb, sig, ct)
    except Exception:
        zenos.audit("vault-backup-refused", file=p.name, reason="signature")
        return {"skipped": "signature check failed"}
    lvl, folder = h["level"], p.parent.name
    if lvl > zenos.folder_range(p)[1]:
        return {"skipped": "level above folder (downgrade is handled by the guard)"}
    key = entry_key(folder, p.name)
    sha = hashlib.sha256(blob).hexdigest()
    with Lock(key):
        entry = read_entry(key) or {"file": p.name, "folder": folder, "level": lvl, "versions": []}
        if entry["versions"] and entry["versions"][-1]["sha256"] == sha:
            return {"skipped": "already stored"}
        c = conf()
        TMP.mkdir(parents=True, exist_ok=True)
        t = TMP / f"{secrets.token_hex(8)}.zen"
        t.write_bytes(blob)  # the file is already sealed; this copy is ciphertext
        try:
            res = store(["put", str(t), "--level", f"L{lvl}", "--k", str(c["k"]), "--n", str(c["n"]),
                         "--min-nodes", str(c["k"]), "--name", key])
        except Exception as e:
            zenos.audit("vault-backup-failed", file=p.name, level=lvl, error=str(e)[:200])
            if not quiet:
                zenos.notify("ZENOS Vault", f"{p.name} could not be stored on the storage grid.\n{e}")
            raise
        finally:
            t.unlink(missing_ok=True)
        entry["level"] = max(entry["level"], lvl)
        entry["versions"].append({
            "t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "level": lvl, "sha256": sha, "bytes": len(blob),
            "fileId": res["fileId"], "capability": res["capability"],
            "nodes": sorted({x["zone"] for x in res["placement"]}),
        })
        entry["versions"] = entry["versions"][-MAX_VERSIONS:]
        write_entry(key, entry)
    zenos.audit("vault-backup", file=p.name, level=lvl, folder=folder, version=len(entry["versions"]),
                fileId=res["fileId"], shards=res["stored"], nodes=len(entry["versions"][-1]["nodes"]))
    return {"stored": p.name, "version": len(entry["versions"]), "fileId": res["fileId"]}


def backup_all(interval=5.0):
    """Store every sealed file once. Slow on purpose: the sentinel halts on 6 protected files opened within 20 s, so one every 5 s stays under it."""
    n = 0
    for name in zenos.FOLDERS:
        d = zenos.DESK / name
        for f in sorted(d.glob("*.zen")) if d.exists() else []:
            r = backup(f, quiet=True)
            if r.get("stored"):
                n += 1
                time.sleep(interval)
    return n


# ---------------- restore ----------------

def find(name):
    for e in visible_entries():
        if e["file"] == name:
            return e
    return None


def restore(name, version=None, to=None):
    halted = getattr(zenos, "refuse_if_halted", None)
    if halted and halted("restore"):
        return None
    e = find(name)
    if not e:
        zenos.audit("vault-restore-refused", file=name, reason="not visible at session level")
        raise LookupError(f"{name} is not in the Vault at L{zenos.session_level()}")
    v = e["versions"][(version or len(e["versions"])) - 1]
    if v["level"] > zenos.session_level():
        raise PermissionError("this version is above the session level")
    TMP.mkdir(parents=True, exist_ok=True)
    t = TMP / f"{secrets.token_hex(8)}.zen"
    try:
        res = store(["get", "--cap-stdin", "--out", str(t), "--min-nodes", str(conf()["k"])], stdin=v["capability"])
        blob = t.read_bytes()
    finally:
        t.unlink(missing_ok=True)
    if hashlib.sha256(blob).hexdigest() != v["sha256"]:
        zenos.audit("vault-restore-refused", file=name, reason="content mismatch")
        raise ValueError("the restored copy does not match the stored version")
    h, hb, sig, ct = zenos.parse(blob)
    zenos.verify(hb, sig, ct)
    dest_dir = Path(to) if to else zenos.folder_for(h["level"])
    dest = dest_dir / name
    if dest.exists():
        if hashlib.sha256(dest.read_bytes()).hexdigest() == v["sha256"]:
            zenos.audit("vault-restore", file=name, level=h["level"], version=version or len(e["versions"]), result="already present")
            return dest
        base = name[:-4] if name.endswith(".zen") else name
        dest = dest_dir / f"{base} (restored {time.strftime('%Y-%m-%d %H%M%S')}).zen"
    tmp = dest_dir / f".{secrets.token_hex(4)}.part"
    tmp.write_bytes(blob)
    tmp.replace(dest)
    zenos.audit("vault-restore", file=dest.name, level=h["level"], version=version or len(e["versions"]),
                shards_used=len(res["used"]), rejected=len(res["rejected"]))
    return dest


# ---------------- local grid (PoC: five test nodes inside this machine) ----------------

def setup(host="127.0.0.1", port=49737):
    for d in (P2P, INDEX, LOCKS, TMP, RUN, LOGS, NODES):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(P2P, 0o700)
    admin_file = P2P / "admin.json"
    if not admin_file.exists():
        store_text(["admin-init", "--out", str(admin_file)])
    admin = json.loads(admin_file.read_text())["publicKey"]
    nodes = []
    for zone, slug in DEFAULT_NODES:
        d = NODES / slug
        cert = d / "cert.json"
        if not cert.exists():
            pub = store_text(["node-id", "--dir", str(d)]).splitlines()[-1].strip()
            store_text(["certify", "--admin-file", str(admin_file), "--node", pub,
                        "--clearance", "L5", "--zone", zone, "--out", str(cert)])
        nodes.append({"label": zone, "slug": slug, "dir": str(d), "cert": str(cert)})
    c = {"grid": "zenos-local", "bootstrap": f"{host}:{port}", "host": host, "port": port,
         "admin": admin, "k": 3, "n": 5, "repair": 30, "nodes": nodes}
    CONF.write_text(json.dumps(c, ensure_ascii=False, indent=1))
    (P2P / "enabled").write_text("on\n")
    zenos.audit("vault-setup", nodes=len(nodes), k=3, n=5)
    return c


def _alive(pidfile):
    try:
        pid = int(pidfile.read_text())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def _port_open(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def _spawn(name, args):
    LOGS.mkdir(parents=True, exist_ok=True)
    RUN.mkdir(parents=True, exist_ok=True)
    pf = RUN / f"{name}.pid"
    if _alive(pf):
        return False
    log = open(LOGS / f"{name}.log", "a")
    p = subprocess.Popen([NODEJS, str(STORE), *args], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    pf.write_text(str(p.pid))
    return True


def grid_start(only=None):
    c = conf()
    if not _alive(RUN / "bootstrap.pid") and not _port_open(c["host"], c["port"]):
        _spawn("bootstrap", ["bootstrap", "--host", c["host"], "--port", str(c["port"])])
        time.sleep(3)
    started = []
    for n in c["nodes"]:
        if only and n["slug"] not in only:
            continue
        if _spawn(n["slug"], ["node", "--dir", n["dir"], "--label", n["label"], "--cert", n["cert"],
                              "--repair", str(c["repair"]), *grid_args(c)]):
            started.append(n["label"])
    return started


def grid_stop(only=None):
    stopped = []
    for pf in sorted(RUN.glob("*.pid")) if RUN.exists() else []:
        if only and pf.stem not in only:
            continue
        pid = _alive(pf)
        if pid:
            os.kill(pid, signal.SIGINT)
            stopped.append(pf.stem)
        pf.unlink(missing_ok=True)
    return stopped


def grid_status():
    c = conf()
    local = {n["slug"]: bool(_alive(RUN / f"{n['slug']}.pid")) for n in c["nodes"]}
    try:
        seen = store(["status", "--wait", "1500"], timeout=40)["nodes"]
    except Exception as e:
        seen = []
        local["error"] = str(e)
    return {"local_processes": local, "reachable": seen}


# ---------------- windows (kdialog) ----------------

def win_vault():
    s = zenos.session_level()
    try:
        entries = visible_entries()
    except Exception as e:
        zenos.kd("--title", "ZENOS Vault", "--sorry", f"The Vault index could not be read.\n{e}")
        return
    if not entries:
        zenos.kd("--title", f"ZENOS Vault · L{s}", "--msgbox",
                 f"No files are stored on the storage grid at L{s} or below yet.\n\n"
                 "Files saved in the security folders are stored automatically.")
        return
    items = []
    for i, e in enumerate(sorted(entries, key=lambda x: x["versions"][-1]["t"], reverse=True)):
        v = e["versions"][-1]
        items += [str(i), f"L{e['level']} · {e['file']} · {e['folder']} · {v['t'][:16].replace('T', ' ')} · "
                          f"{len(e['versions'])} version(s)"]
    order = sorted(entries, key=lambda x: x["versions"][-1]["t"], reverse=True)
    rc, pick = zenos.kd("--title", f"ZENOS Vault · L{s}", "--menu",
                        f"Files stored across the storage grid (shown up to L{s}).\n"
                        "Any 3 of 5 nodes can restore a file. Choose one to restore.", *items)
    if rc != 0 or pick == "":
        return
    e = order[int(pick)]
    version = None
    if len(e["versions"]) > 1:
        vitems = []
        for i, v in reversed(list(enumerate(e["versions"], 1))):
            vitems += [str(i), f"Version {i} · {v['t'][:19].replace('T', ' ')} · {v['bytes']:,} bytes"]
        rc, pv = zenos.kd("--title", f"ZENOS Vault · {e['file']}", "--menu", "Choose the version to restore.", *vitems)
        if rc != 0 or pv == "":
            return
        version = int(pv)
    try:
        dest = restore(e["file"], version)
    except Exception as ex:
        zenos.kd("--title", "ZENOS Vault", "--sorry", f"{e['file']} could not be restored.\n\n{ex}")
        return
    if dest:
        zenos.notify("ZENOS Vault", f"{dest.name} was restored into {dest.parent.name}.\n"
                                   "Signature checked. The copy is identical to the stored version.")


def win_status():
    st = grid_status()
    reach = st["reachable"]
    lines = [f"{n['label']}: up to {n['clearance']} · {n['zone']} · {'certificate valid' if n['certified'] else 'NOT certified'}"
             for n in reach]
    s = zenos.session_level()
    try:
        count = len(visible_entries())
    except Exception:
        count = 0
    zenos.kd("--title", "ZENOS Vault · Storage grid", "--msgbox",
             f"Reachable storage nodes: {len(reach)}\n" + "\n".join(lines) +
             f"\n\nFiles visible at L{s}: {count}\nAny {conf()['k']} of {conf()['n']} nodes can restore a file.")


# ---------------- entry point ----------------

def main(argv):
    cmd, *args = argv or ["help"]
    opt = {}
    pos = []
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            opt[args[i][2:]] = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        else:
            pos.append(args[i])
            i += 1
    if cmd == "setup":
        print(json.dumps({k: v for k, v in setup().items() if k != "nodes"}, ensure_ascii=False))
    elif cmd == "grid-start":
        print(json.dumps({"started": grid_start(opt.get("only", "").split(",") if opt.get("only") else None)}))
    elif cmd == "grid-stop":
        print(json.dumps({"stopped": grid_stop(opt.get("only", "").split(",") if opt.get("only") else None)}))
    elif cmd == "grid-status":
        print(json.dumps(grid_status(), ensure_ascii=False))
    elif cmd == "backup":
        print(json.dumps(backup(pos[0], quiet="quiet" in opt), ensure_ascii=False))
    elif cmd == "backup-all":
        print(json.dumps({"stored": backup_all(float(opt.get("interval", 5)))}))
    elif cmd == "list":
        print(json.dumps([{"file": e["file"], "folder": e["folder"], "level": e["level"],
                           "versions": len(e["versions"]), "latest": e["versions"][-1]["t"]}
                          for e in visible_entries()], ensure_ascii=False))
    elif cmd == "restore":
        d = restore(pos[0], int(opt["version"]) if opt.get("version") else None, opt.get("to"))
        print(json.dumps({"restored": str(d) if d else None}, ensure_ascii=False))
    elif cmd == "vault":
        win_vault()
    elif cmd == "status":
        win_status()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

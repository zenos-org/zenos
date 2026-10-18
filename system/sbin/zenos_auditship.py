#!/usr/bin/env python3
"""ZENOS audit shipping (root): sends this PC's tamper-evident ledgers to the audit nodes, as they grow.

Once a record has reached a node, rewriting it on this PC is detected there (the node refuses the changed history
and raises an alert). Batches are signed with this PC's audit key (/etc/zenos/audit-device.key, root only); the
node's signed receipts are kept in /var/lib/zenos/audit-receipts.jsonl.

Configuration: /etc/zenos/audit.json
  {"machine": "pc-0042",                         (optional; default: from /etc/machine-id)
   "nodes": [{"name": "Ministry audit", "url": "https://audit.example.go.jp:8443", "pub": "<node key>"}],
   "ledgers": {"guard": "/var/log/zenos/access-ledger.jsonl",
               "user-*": "/home/*/.local/share/zenos/ledger.jsonl"}}      ("*" = the user name)
  zenos_auditship.py --show-key     the line to enroll this PC on a node
  zenos_auditship.py --once         ship once and exit
"""
import base64, glob, hashlib, json, os, ssl, sys, time, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urlparse
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

CONF = Path(os.environ.get("ZENOS_AUDIT_CONF", "/etc/zenos/audit.json"))
KEY = Path(os.environ.get("ZENOS_AUDIT_KEY", "/etc/zenos/audit-device.key"))
STATE = Path(os.environ.get("ZENOS_AUDIT_STATE", "/var/lib/zenos/audit-ship.json"))
RECEIPTS = STATE.with_name("audit-receipts.jsonl")
LOG = Path(os.environ.get("ZENOS_AUDIT_LOG", "/var/log/zenos/guard.jsonl"))
DEFAULT_LEDGERS = {"guard": "/var/log/zenos/access-ledger.jsonl", "user-*": "/home/*/.local/share/zenos/ledger.jsonl"}
BATCH = 500


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def log(**kw):
    kw = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **kw}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(json.dumps(kw, ensure_ascii=False), flush=True)


_said = {}


def once(key, every, **kw):
    """log a recurring problem when it starts, then at most once per `every` seconds"""
    if time.time() - _said.get(key, 0) > every:
        _said[key] = time.time()
        log(**kw)


def device_key():
    if not KEY.exists():
        KEY.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
    return Ed25519PrivateKey.from_private_bytes(KEY.read_bytes())


def conf():
    try:
        c = json.loads(CONF.read_text())
    except (OSError, ValueError):
        c = {}
    if not c.get("machine"):
        try:
            c["machine"] = "pc-" + Path("/etc/machine-id").read_text().strip()[:12]
        except OSError:
            c["machine"] = "pc-unknown"
    c.setdefault("nodes", [])
    c.setdefault("ledgers", DEFAULT_LEDGERS)
    return c


def ledgers(c):
    """chain name -> file"""
    out = {}
    for name, pat in c["ledgers"].items():
        if "*" in name:
            for p in glob.glob(pat):
                user = Path(p).relative_to(Path(pat.split("*")[0])).parts[0]
                out[name.replace("*", user)] = p
        elif os.path.exists(pat):
            out[name] = pat
    return out


def read_records(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def post(url, body):
    u = urlparse(url)
    if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("audit nodes must be reached over https")
    req = urllib.request.Request(url.rstrip("/") + "/v1/batch", data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context() if u.scheme == "https" else None) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def ship_once(c, key, state):
    for node in c["nodes"]:
        try:
            npub = Ed25519PublicKey.from_public_bytes(base64.b64decode(node["pub"]))
        except Exception:
            log(event="audit-node-misconfigured", node=node.get("name"))
            continue
        st = state.setdefault(node["url"], {})
        for chain, path in ledgers(c).items():
            try:
                recs = read_records(path)
            except (OSError, ValueError):
                continue
            for attempt in range(50):                             # until this node has everything
                frm = min(st.get(chain, 0), len(recs))
                if frm >= len(recs) and (attempt or chain != "guard"):
                    break                                         # (the guard chain always sends: a heartbeat)
                b = {"machine": c["machine"], "chain": chain, "from": frm, "records": recs[frm:frm + BATCH]}
                b["sig"] = base64.b64encode(key.sign(hashlib.sha256(canon({k: b[k] for k in ("machine", "chain", "from", "records")})).digest())).decode()
                try:
                    code, ans = post(node["url"], b)
                except Exception as e:
                    once(("down", node["url"]), 3600, event="audit-node-unreachable", node=node.get("name"), error=str(e)[:120])
                    return
                if _said.pop(("down", node["url"]), None):
                    log(event="audit-node-reachable", node=node.get("name"))
                if code == 200 and ans.get("ok"):
                    try:
                        npub.verify(base64.b64decode(ans["sig"]), canon(ans["receipt"]))
                    except Exception:
                        log(event="audit-receipt-invalid", node=node.get("name"), chain=chain)
                        return
                    st[chain] = ans["receipt"]["count"]
                    if ans.get("added"):
                        with open(RECEIPTS, "a") as f:
                            f.write(json.dumps({"node": node.get("name"), **ans}, ensure_ascii=False) + "\n")
                    if frm >= len(recs):
                        break
                elif code == 409 and "need" in ans:                 # the node holds less (or a restart): resend from there
                    st[chain] = int(ans["need"])
                else:
                    once(("refused", node["url"], chain, ans.get("error")), 3600, event="audit-node-refused", node=node.get("name"),
                         chain=chain, code=code, error=str(ans.get("error"))[:120], index=ans.get("index"))
                    break
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_name(STATE.name + ".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE)


def main():
    key = device_key()
    c = conf()
    if "--show-key" in sys.argv:
        pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        return print(f"zenos_auditnode.py --store <dir> --enroll {c['machine']} {pub}")
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    while True:
        ship_once(conf(), key, state)
        if "--once" in sys.argv:
            return
        time.sleep(30)


if __name__ == "__main__":
    main()

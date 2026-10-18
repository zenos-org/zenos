#!/usr/bin/env python3
"""ZENOS audit node: keeps a copy of every enrolled PC's tamper-evident ledger, outside that PC.

A ledger on the PC itself can be rewritten by whoever controls the PC. This node accepts only records that
continue the chain it already holds: a changed past record, a gap, a broken link or a bad signature is refused
and written to the node's alert log. Each accepted batch gets a receipt signed by the node, which the PC keeps.

Run it on a machine the PC users do not control (a ministry server), behind TLS:
  zenos_auditnode.py --store /var/lib/zenos-audit --port 8443 --cert node.crt --key node.key
Enroll a PC (its key is printed by `zenos_auditship.py --show-key` on that PC):
  zenos_auditnode.py --store /var/lib/zenos-audit --enroll MACHINE PUBKEY
Print this node's public key (goes into the PC's /etc/zenos/audit.json):
  zenos_auditnode.py --store /var/lib/zenos-audit --show-key
"""
import base64, hashlib, json, os, re, ssl, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "zenos")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))
import zledger                                                     # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey   # noqa: E402
from cryptography.hazmat.primitives import serialization          # noqa: E402

NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_BATCH = 2000
lock = threading.Lock()


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def batch_digest(b):
    return hashlib.sha256(canon({"machine": b["machine"], "chain": b["chain"], "from": b["from"], "records": b["records"]})).digest()


class Node:
    def __init__(self, store):
        self.dir = Path(store)
        (self.dir / "machines").mkdir(parents=True, exist_ok=True)
        (self.dir / "chains").mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        kp = self.dir / "node.key"
        if not kp.exists():
            fd = os.open(kp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        self.key = Ed25519PrivateKey.from_private_bytes(kp.read_bytes())

    def pub_b64(self):
        return base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()

    def enroll(self, machine, pub_b64):
        if not NAME.match(machine):
            raise ValueError("bad machine name")
        raw = base64.b64decode(pub_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(raw)
        (self.dir / "machines" / f"{machine}.pub").write_bytes(raw)
        self.alert("machine-enrolled", machine=machine, fingerprint=hashlib.sha256(raw).hexdigest()[:16])

    def alert(self, event, **kw):
        with open(self.dir / "alerts.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **kw}, ensure_ascii=False) + "\n")

    def chain_path(self, machine, chain):
        return self.dir / "chains" / f"{machine}__{chain}.jsonl"

    def held(self, machine, chain):
        p = self.chain_path(machine, chain)
        hashes = []
        if p.exists():
            with open(p, encoding="utf-8") as f:
                hashes = [json.loads(l)["hash"] for l in f if l.strip()]
        return hashes

    def receipt(self, machine, chain, count, last):
        r = {"machine": machine, "chain": chain, "count": count, "last": last, "t": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        return {"receipt": r, "sig": base64.b64encode(self.key.sign(canon(r))).decode()}

    def accept(self, b):
        """returns (http status, answer)"""
        try:
            machine, chain, frm, recs = str(b["machine"]), str(b["chain"]), int(b["from"]), list(b["records"])
        except Exception:
            return 400, {"ok": False, "error": "malformed batch"}
        if not (NAME.match(machine) and NAME.match(chain)) or frm < 0 or len(recs) > MAX_BATCH:
            return 400, {"ok": False, "error": "malformed batch"}
        pk = self.dir / "machines" / f"{machine}.pub"
        if not pk.exists():
            return 403, {"ok": False, "error": "machine not enrolled"}
        try:
            Ed25519PublicKey.from_public_bytes(pk.read_bytes()).verify(base64.b64decode(b.get("sig", "")), batch_digest(b))
        except Exception:
            self.alert("bad-signature", machine=machine, chain=chain)
            return 403, {"ok": False, "error": "signature does not verify"}
        with lock:
            seen = self.dir / "machines" / f"{machine}.seen"         # heard from (even if the batch is refused below)
            if seen.exists() and seen.read_text().strip() == "silent":
                self.alert("machine-back", machine=machine)
            seen.write_text(str(time.time()))
            held = self.held(machine, chain)
            n = len(held)
            if frm > n:
                return 409, {"ok": False, "error": "gap", "need": n}
            for i, rec in enumerate(recs):                          # records this node already holds must be identical
                if frm + i < n and rec.get("hash") != held[frm + i]:
                    self.alert("history-rewritten", machine=machine, chain=chain, index=frm + i,
                               held=held[frm + i][:16], offered=str(rec.get("hash"))[:16])
                    return 409, {"ok": False, "error": "history differs from the copy held here", "index": frm + i}
            new = recs[max(0, n - frm):]
            prev = held[-1] if held else zledger.GENESIS
            for j, rec in enumerate(new):
                body = {k: v for k, v in rec.items() if k != "hash"}
                if rec.get("prev") != prev or hashlib.sha256(prev.encode() + zledger._canon(body)).hexdigest() != rec.get("hash"):
                    self.alert("broken-chain", machine=machine, chain=chain, index=n + j)
                    return 422, {"ok": False, "error": "broken chain", "index": n + j}
                prev = rec["hash"]
            if new:
                with open(self.chain_path(machine, chain), "a", encoding="utf-8") as f:
                    for rec in new:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            count = n + len(new)
            return 200, {"ok": True, "added": len(new), **self.receipt(machine, chain, count, prev)}


    def check_silence(self, limit):
        """a PC that stops reporting (switched off the network, shipping stopped) is itself a signal"""
        for p in (self.dir / "machines").glob("*.seen"):
            try:
                v = p.read_text().strip()
                if v != "silent" and time.time() - float(v) > limit:
                    p.write_text("silent")
                    self.alert("machine-silent", machine=p.stem, minutes=int(limit // 60))
            except (OSError, ValueError):
                continue


def serve(node, host, port, cert=None, key=None, silence=600):
    def watch():
        while True:
            time.sleep(60)
            node.check_silence(silence)
    threading.Thread(target=watch, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/v1/batch":
                return self.reply(404, {"ok": False})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 32 * 1024 * 1024:
                return self.reply(413, {"ok": False, "error": "too large"})
            try:
                b = json.loads(self.rfile.read(n))
            except Exception:
                return self.reply(400, {"ok": False, "error": "not JSON"})
            self.reply(*node.accept(b))

        def do_GET(self):
            m = re.match(r"^/v1/status/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", self.path)
            if not m:
                return self.reply(200, {"ok": True, "node": node.pub_b64()}) if self.path == "/v1/node" else self.reply(404, {"ok": False})
            held = node.held(*m.groups())
            self.reply(200, {"ok": True, **node.receipt(m.group(1), m.group(2), len(held), held[-1] if held else zledger.GENESIS)})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    if cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"audit node on {host}:{port} ({'TLS' if cert else 'plain HTTP, local testing only'})", flush=True)
    srv.serve_forever()


def main():
    a = sys.argv[1:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    store = opt("--store")
    if not store:
        sys.exit(__doc__)
    node = Node(store)
    if "--show-key" in a:
        return print(node.pub_b64())
    if "--enroll" in a:
        i = a.index("--enroll")
        node.enroll(a[i + 1], a[i + 2])
        return print(f"enrolled {a[i + 1]}")
    host = opt("--host", "0.0.0.0" if opt("--cert") else "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost") and not opt("--cert"):
        sys.exit("Listening beyond this machine needs TLS: give --cert and --key.")
    serve(node, host, int(opt("--port", "8443")), opt("--cert"), opt("--key"), int(opt("--silence-minutes", "10")) * 60)


if __name__ == "__main__":
    main()

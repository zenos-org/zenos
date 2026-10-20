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

Consortium: audit nodes run by different parties (ministries, an independent audit body) list each other
as peers in the config file and compare their copies every few minutes. A PC that sends different
histories to different nodes, or a node whose copy was altered, shows up as a fork on both sides:
  zenos_auditnode.py --config /etc/zenos/auditnode.json --store /var/lib/zenos-audit
  zenos_auditnode.py --config /etc/zenos/auditnode.json --store /var/lib/zenos-audit --check-peers
The history the consortium stands behind is the longest prefix a majority of the audit nodes hold identically:
  zenos_auditnode.py --config /etc/zenos/auditnode.json --store /var/lib/zenos-audit --consortium-status MACHINE CHAIN
"""
import base64, hashlib, json, os, re, ssl, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "zenos")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))       # zenos-grid package: zledger.py sits beside this file
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

    def held_chains(self):
        out = []
        for p in sorted((self.dir / "chains").glob("*__*.jsonl")):
            m, c = p.stem.split("__", 1)
            out.append((m, c))
        return out

    def receipt_at(self, machine, chain, at=None):
        """signed statement of what this node holds: the first `at` records (all when at is None) end in `last`"""
        held = self.held(machine, chain)
        n = len(held) if at is None else max(0, min(int(at), len(held)))
        return self.receipt(machine, chain, n, held[n - 1] if n else zledger.GENESIS)


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


# ---------------- consortium: audit nodes run by different parties check each other ----------------
#
# Each PC ships its ledgers to every audit node it is enrolled on. Every node keeps its own copy and
# signs what it holds. The nodes then compare their copies with each other: for every machine and chain,
# the shorter copy must be a prefix of the longer one. A mismatch is a fork: the PC sent different
# histories to different nodes, or one node's copy was altered. Both signed statements are kept as
# evidence, so neither party can later deny what it held.

def verify_receipt(pub_b64, ans):
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
    pub.verify(base64.b64decode(ans["sig"]), canon(ans["receipt"]))
    return ans["receipt"]


def _first_report(node, key):
    """a fork is recorded and alerted once, not on every check (the alert channel must not flood)"""
    seen = getattr(node, "_forks_seen", None)
    if seen is None:
        seen = set()
        try:
            for line in (node.dir / "forks.jsonl").read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                seen.add((e["peer"], e["machine"], e["chain"], e["at"], e["ours"]["receipt"]["last"], e["theirs"]["receipt"]["last"]))
        except (OSError, ValueError, KeyError):
            pass
        node._forks_seen = seen
    if key in seen:
        return False
    seen.add(key)
    return True


def cross_check(node, peers, fetch):
    """peers: [{"name", "url", "pub"}]; fetch(url, machine, chain, at) -> the peer's signed answer.
    Returns a list of findings; forks are also written to alerts.jsonl and forks.jsonl."""
    findings = []
    for machine, chain in node.held_chains():
        mine = node.held(machine, chain)
        for p in peers:
            try:
                ans = fetch(p["url"], machine, chain, None)
                theirs = verify_receipt(p["pub"], ans)
                if theirs["machine"] != machine or theirs["chain"] != chain:
                    raise ValueError("answer is about another chain")
            except Exception as e:
                findings.append({"peer": p.get("name"), "machine": machine, "chain": chain, "state": "unreachable", "error": str(e)[:120]})
                continue
            n = min(len(mine), theirs["count"])
            if n == 0:
                findings.append({"peer": p.get("name"), "machine": machine, "chain": chain, "state": "agree", "common": 0})
                continue
            if theirs["count"] > n:                       # the peer holds more: ask what it holds at our length
                try:
                    ans = fetch(p["url"], machine, chain, n)
                    theirs = verify_receipt(p["pub"], ans)
                except Exception as e:
                    findings.append({"peer": p.get("name"), "machine": machine, "chain": chain, "state": "unreachable", "error": str(e)[:120]})
                    continue
            if theirs["count"] != n:
                state = "fork"
            else:
                state = "agree" if theirs["last"] == mine[n - 1] else "fork"
            f = {"peer": p.get("name"), "machine": machine, "chain": chain, "state": state, "common": n,
                 "mine": len(mine), "theirs_signed": theirs}
            findings.append(f)
            if state == "fork" and _first_report(node, (p.get("name"), machine, chain, n, mine[n - 1], theirs.get("last"))):
                mine_signed = node.receipt_at(machine, chain, n)
                with open(node.dir / "forks.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "peer": p.get("name"), "machine": machine,
                                         "chain": chain, "at": n, "ours": mine_signed,
                                         "theirs": {"receipt": ans["receipt"], "sig": ans["sig"]}}, ensure_ascii=False) + "\n")
                node.alert("consortium-fork", peer=p.get("name"), machine=machine, chain=chain, at=n,
                           ours=mine[n - 1][:16], theirs=str(theirs.get("last"))[:16])
    return findings


def consortium_view(members, fetch, machine, chain, quorum=None):
    """One history for the whole consortium: the longest prefix that a quorum (default: a majority) of the
    audit nodes hold identically, each one's answer signed. members: [{"name", "url", "pub"}] (this node
    included as a member like the others). Returns {"final": n, "last": hash, "quorum": q, "members": [...]}:
    records up to `final` are agreed; a member whose copy differs within that prefix is a dissenter."""
    q = quorum or (len(members) // 2 + 1)
    answers = {}
    for m in members:
        try:
            r = verify_receipt(m["pub"], fetch(m["url"], machine, chain, None))
            if r["machine"] == machine and r["chain"] == chain:
                answers[m["name"]] = r
        except Exception:
            pass
    view = {"machine": machine, "chain": chain, "quorum": q, "final": 0, "last": zledger.GENESIS,
            "members": {m["name"]: ("reachable" if m["name"] in answers else "unreachable") for m in members}}

    def at(n):
        """what each member holds at length n: {hash: [names]}"""
        groups = {}
        for m in members:
            r = answers.get(m["name"])
            if not r or r["count"] < n:
                continue
            try:
                r = r if r["count"] == n else verify_receipt(m["pub"], fetch(m["url"], machine, chain, n))
            except Exception:
                continue
            if r["count"] == n:
                groups.setdefault(r["last"], []).append(m["name"])
        return groups

    def agreed(n):
        g = at(n)
        best = max(g.items(), key=lambda kv: len(kv[1])) if g else (None, [])
        return best if len(best[1]) >= q else None

    # Chains are hash-linked, so members that agree at length n agree on every shorter length:
    # the longest agreed length is found by bisection.
    lo, hi = 0, max([r["count"] for r in answers.values()] or [0])
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if agreed(mid):
            lo = mid
        else:
            hi = mid - 1
    if lo:
        last, holders = agreed(lo)
        view["final"], view["last"] = lo, last
        diverged = {name for h, names in at(lo).items() if h != last for name in names}
        for name, state in view["members"].items():
            if state == "unreachable":
                continue
            view["members"][name] = "agrees" if name in holders else "dissents" if name in diverged else "behind"
    return view


def http_fetch(url, machine, chain, at, timeout=15):
    import urllib.request
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("peer audit nodes must be reached over https")
    q = f"{url.rstrip('/')}/v1/status/{machine}/{chain}" + (f"?at={int(at)}" if at is not None else "")
    ctx = ssl.create_default_context() if u.scheme == "https" else None
    with urllib.request.urlopen(q, timeout=timeout, context=ctx) as r:
        return json.loads(r.read())


def serve(node, host, port, cert=None, key=None, silence=600, peers=(), check_every=120):
    def watch():
        while True:
            time.sleep(60)
            node.check_silence(silence)
    threading.Thread(target=watch, daemon=True).start()

    if peers:
        def consortium():
            while True:
                time.sleep(check_every)
                try:
                    for f in cross_check(node, peers, http_fetch):
                        if f["state"] == "unreachable":
                            node.alert("consortium-peer-unreachable", peer=f["peer"], error=f.get("error"))
                except Exception as e:
                    node.alert("consortium-check-error", error=str(e)[:160])
        threading.Thread(target=consortium, daemon=True).start()

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
            m = re.match(r"^/v1/status/([A-Za-z0-9_.-]{1,64})/([A-Za-z0-9_.-]{1,64})(?:\?at=(\d{1,9}))?$", self.path)
            if not m:
                return self.reply(200, {"ok": True, "node": node.pub_b64()}) if self.path == "/v1/node" else self.reply(404, {"ok": False})
            machine, chain, at = m.groups()
            self.reply(200, {"ok": True, **node.receipt_at(machine, chain, int(at) if at is not None else None)})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    if cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"audit node on {host}:{port} ({'TLS' if cert else 'plain HTTP, local testing only'}), "
          f"{len(peers)} consortium peer(s)", flush=True)
    srv.serve_forever()


def main():
    a = sys.argv[1:]
    cfg = {}
    if "--config" in a:
        # /etc/zenos/auditnode.json: {"host", "port", "cert", "key", "silence_minutes",
        #                             "peers": [{"name", "url", "pub"}], "check_seconds"}
        cfg = json.loads(Path(a[a.index("--config") + 1]).read_text())
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else cfg.get(k.lstrip("-").replace("-", "_"), d)
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
    if "--consortium-status" in a:   # the history a majority of the consortium agrees on
        i = a.index("--consortium-status")
        port = int(opt("--port", "8443"))
        me = {"name": cfg.get("name", "this node"), "url": f"{'https' if opt('--cert') else 'http'}://127.0.0.1:{port}", "pub": node.pub_b64()}
        def fetch(url, machine, chain, at):
            if url == me["url"]:
                return {"ok": True, **node.receipt_at(machine, chain, at)}
            return http_fetch(url, machine, chain, at)
        print(json.dumps(consortium_view([me, *cfg.get("peers", [])], fetch, a[i + 1], a[i + 2]), ensure_ascii=False))
        return
    if "--check-peers" in a:   # one consortium check now, printed
        for f in cross_check(node, cfg.get("peers", []), http_fetch):
            f.pop("theirs_signed", None)
            print(json.dumps(f, ensure_ascii=False))
        return
    host = str(opt("--host", "0.0.0.0" if opt("--cert") else "127.0.0.1"))
    if host not in ("127.0.0.1", "::1", "localhost") and not opt("--cert"):
        sys.exit("Listening beyond this machine needs TLS: give --cert and --key.")
    serve(node, host, int(opt("--port", "8443")), opt("--cert"), opt("--key"), int(opt("--silence-minutes", "10")) * 60,
          peers=cfg.get("peers", []), check_every=int(cfg.get("check_seconds", 120)))


if __name__ == "__main__":
    main()

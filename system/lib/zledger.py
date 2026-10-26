#!/usr/bin/env python3
"""ZENOS tamper-evident access ledger (PoC).

Each record carries the hash of the previous record (a hash chain). Editing or deleting any past
record breaks every hash after it, so verify() names the first broken point. Records are the
consortium-chain events that pin attribution: who opened what, when, and every per-fragment key issue.
Replicated across the grid nodes so no single node can quietly rewrite its own history.
"""
import fcntl, hashlib, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zdecide                      # the chain check itself (proved: formal/ZenosFormal/Ledger.lean)

GENESIS = "0" * 64


def _canon(rec):
    return json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _last_hash(path):
    if not os.path.exists(path):
        return GENESIS
    last = GENESIS
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                last = json.loads(line)["hash"]
    return last


def append(path, event, actor, device, **kw):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)            # serialize concurrent writers
        try:
            prev = _last_hash(path)
            body = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event,
                    "actor": actor, "device": device, "prev": prev, **kw}
            body["hash"] = hashlib.sha256(prev.encode() + _canon(body)).hexdigest()
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(body, ensure_ascii=False) + "\n")
                f.flush(); os.fsync(f.fileno())    # durable before ack (WAL)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    return body["hash"]


def facts(records):
    """each record's link and stored hash, and whether the stored hash is SHA-256 of the link and its contents"""
    out = []
    for rec in records:
        body = {k: v for k, v in rec.items() if k != "hash"}
        stored = rec.get("hash")
        out.append({"prev": rec.get("prev"), "hash": stored,
                    "hash_ok": hashlib.sha256(str(rec.get("prev")).encode() + _canon(body)).hexdigest() == stored})
    return out


def verify(path):
    """Return (ok, index, reason). ok=True means the whole chain is intact (decided by zenos-decide)."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    except FileNotFoundError:
        return True, -1, "empty"
    recs = []
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                raise ValueError
        except ValueError:
            return False, i, "unreadable record"
        recs.append(rec)
    ok, index, reason, _ = zdecide.chain(GENESIS, facts(recs))
    return (True, len(recs) - 1, "intact") if ok else (False, index, reason)

#!/usr/bin/env python3
"""ZENOS pre-send check (PoC): nothing leaves unless it is sealed.

The OS-wide guarantee is "no plaintext leaves". Before any outbound file transfer, this gate verifies:
  - the content is a valid ZENOS sealed blob (MAGIC + signature verifies) -> ok
  - plaintext / unsealed / tampered -> BLOCK
  - size over the "huge" line -> allowed only with an approved transfer request (申請)
Every decision is written to the tamper-evident ledger. This sits in front of the network sensor as the
sanctioned path; the sensor still catches anything that tries to bypass it.
"""
import os, sys
sys.path.insert(0, "/home/zenos/.local/share/zenos/bin")
sys.path.insert(0, "/usr/local/lib/zenos")
import zenos, zledger

NORMAL_MAX = 50 * 1024 * 1024      # <= this and sealed: allowed
HUGE_MAX = NORMAL_MAX              # over this: requires an approved 申請
LEDGER = str(zenos.Z / "ledger.jsonl")


def _actor_device():
    return os.environ.get("USER", "zenos"), __import__("hashlib").sha256(
        (zenos.K / "device_ed25519.pub").read_bytes()).hexdigest()[:16]


def check_send(path):
    """Return (allowed: bool, reason: str). Logs the decision."""
    p = __import__("pathlib").Path(path)
    actor, device = _actor_device()
    try:
        blob = p.read_bytes()
    except Exception as e:
        return _deny("unreadable", p.name, 0, actor, device)
    size = len(blob)
    if not blob.startswith(zenos.MAGIC):
        return _deny("plaintext-or-unsealed", p.name, size, actor, device)
    try:
        h, hb, sig, ct = zenos.parse(blob)
        zenos.verify(hb, sig, ct)
    except Exception:
        return _deny("invalid-or-tampered", p.name, size, actor, device)
    level = h.get("level", 1)
    if size > HUGE_MAX:
        plan, grant = zenos.active_plan("external-send", level)
        if not plan:
            return _deny("too-large-needs-approval", p.name, size, actor, device, level=level)
    zledger.append(LEDGER, "send-allowed", actor, device, file=p.name, size=size, level=level)
    return True, "sealed-ok"


def _deny(reason, name, size, actor, device, level=None):
    zledger.append(LEDGER, "send-blocked", actor, device, file=name, size=size, reason=reason,
                   **({"level": level} if level is not None else {}))
    return False, reason


if __name__ == "__main__":
    ok, why = check_send(sys.argv[1])
    print(("ALLOW" if ok else "BLOCK"), why)
    sys.exit(0 if ok else 3)

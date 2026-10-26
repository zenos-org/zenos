#!/usr/bin/env python3
"""ZENOS pre-send check (PoC): nothing leaves unless it is sealed.

The OS-wide guarantee is "no plaintext leaves". Before any outbound file transfer, this gate verifies:
  - the content is a valid ZENOS sealed blob (MAGIC + signature verifies) -> ok
  - plaintext / unsealed / tampered -> BLOCK
  - size over the "huge" line -> allowed only with an approved transfer request
Every decision is written to the tamper-evident ledger. This sits in front of the network sensor as the
sanctioned path; the sensor still catches anything that tries to bypass it.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zenos                           # also puts the ZENOS library on the path
import zledger, zdecide

NORMAL_MAX = 50 * 1024 * 1024      # <= this and sealed: allowed
HUGE_MAX = NORMAL_MAX              # over this: requires an approved transfer request
LEDGER = str(zenos.Z / "ledger.jsonl")


def _actor_device():
    return os.environ.get("USER", "zenos"), zenos._device_id()


def check_send(path):
    """Return (allowed: bool, reason: str). Logs the decision."""
    p = __import__("pathlib").Path(path)
    actor, device = _actor_device()
    try:
        blob = p.read_bytes()
    except Exception:
        return _deny("unreadable", p.name, 0, actor, device)
    size = len(blob)
    sealed, sig_ok, level = blob.startswith(zenos.MAGIC), False, 1
    if sealed:
        try:
            h, hb, sig, ct = zenos.parse(blob)
            zenos.verify(hb, sig, ct)
            sig_ok, level = True, h.get("level", 1)
        except Exception:
            pass
    plan_ok = bool(zenos.active_plan("external-send", level)[0]) if sealed and sig_ok and size > HUGE_MAX else False
    # the decision itself (proved: formal/ZenosFormal/Egress.lean, send_sound)
    allowed, why = zdecide.send(sealed, sig_ok, size, HUGE_MAX, plan_ok)
    if not allowed:
        return _deny(why, p.name, size, actor, device, **({"level": level} if sealed and sig_ok else {}))
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

"""The proven ZENOS decisions, called from the root services.

Whether a sealed file may be opened, whether an officer's answer is recorded, whether a stop is released and how many
officers a release needs are decided by `zenos-decide`, a program built from the Lean sources in formal/ whose
properties are machine-checked (docs/FORMAL_VERIFICATION.md). This module only gathers the facts the decision needs
and runs it. Anything that goes wrong (program missing, timeout, unreadable answer) is a refusal.

The facts are checked here, outside the proof: signatures (Ed25519 with the enrolled officers' keys), digests, the
clearance file, the roster, the stop state, the clock.
"""
import json, math, os, subprocess, time

_HERE = os.path.dirname(os.path.abspath(__file__))
PROGRAM = os.environ.get("ZENOS_DECIDE") or next(
    (p for p in (os.path.join(_HERE, "zenos-decide"),                                       # installed: /usr/lib/zenos
                 os.path.join(_HERE, "..", "..", "formal", ".lake", "build", "bin", "zenos-decide"))  # repository
     if os.path.isfile(p) and os.access(p, os.X_OK)), None)


class Refused(Exception):
    pass


def ask(req):
    """run one decision; raises Refused when no trustworthy answer comes back"""
    if not PROGRAM:
        raise Refused("zenos-decide is not installed")
    try:
        r = subprocess.run([PROGRAM], input=json.dumps(req, ensure_ascii=True).encode(), capture_output=True,
                           timeout=10, env={})
        out = json.loads(r.stdout or b"{}")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise Refused("zenos-decide failed: %s" % e)
    if r.returncode != 0 or "error" in out:
        raise Refused("zenos-decide refused the request: %s" % out.get("error"))
    return out


def now():
    return math.ceil(time.time())          # whole seconds, rounded so that an expiry is never stretched


def open_file(user, clearance, level, file_hash, halted, roster, grant=None):
    """(allowed, by, reason). grant: dict with requester, holder, file_hash, level, kind, expires, digest_ok, approvals"""
    if grant is not None:
        grant = dict(grant, expires=int(math.floor(float(grant["expires"]))))
    try:
        a = ask({"op": "open", "user": user, "clearance": int(clearance), "level": int(level), "file_hash": file_hash,
                 "now": now(), "halted": bool(halted), "roster": list(roster), "grant": grant})
        return bool(a["allow"]), a.get("by"), a.get("reason")
    except (Refused, KeyError, TypeError, ValueError) as e:
        return False, None, str(e)


def approve(request, roster, who, act, sig_ok, code_ok):
    """'added' | 'declined' | 'refused:<reason>'"""
    try:
        a = ask({"op": "approve", "request": _request(request), "roster": list(roster), "who": who, "act": act,
                 "sig_ok": bool(sig_ok), "code_ok": bool(code_ok)})
        return a["result"] if a["result"] != "refused" else "refused:" + str(a.get("reason"))
    except (Refused, KeyError, TypeError, ValueError) as e:
        return "refused:" + str(e)


def release(halted, request, roster):
    """(release?, counted approvers)"""
    try:
        a = ask({"op": "release", "halted": bool(halted), "request": _request(request), "roster": list(roster)})
        return bool(a["release"]), list(a["approvers"])
    except (Refused, KeyError, TypeError, ValueError):
        return False, []


def release_required(roster, requester, level):
    try:
        return int(ask({"op": "release-required", "roster": list(roster), "requester": requester,
                        "level": int(level)})["required"])
    except (Refused, KeyError, TypeError, ValueError):
        return 1000                        # cannot be met: the PC stays stopped until the decision program is back


def required(level):
    return int(ask({"op": "required", "level": int(level)})["required"])


def _request(r):
    """the part of a release request the decision reads; each approval carries sig_ok, checked by the caller"""
    return {"id": str(r["id"]), "requester": str(r["requester"]), "level": int(r["level"]),
            "required": int(r["required"]), "status": str(r["status"]),
            "approvals": [{"approver": str(a["approver"]), "sig_ok": bool(a.get("sig_ok"))} for a in r["approvals"]]}

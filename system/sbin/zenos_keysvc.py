#!/usr/bin/env python3
"""ZENOS key service: the keys of sealed files live here, not on the PC.

Run it on a machine the PC users and the PC administrator do not control (a ministry server, next to the audit node),
behind TLS. A PC configured for it ("/etc/zenos/keysvc.json") seals new files with a key this service derives from a
master key for the level and the file's id, and gets that key back for one file and one request at a time. Before
each release the service checks, with the proven decision (formal/ZenosFormal/KeyService.lean):
  - the PC is enrolled here and signed the request with its identity key, and the request is recent and new;
  - the audit node heard from the PC within the silence limit, its last signed status shows every protecting service
    running and no stop (asked from the audit node, its answers signed with its key);
  - the user is assigned to this PC here (root on one PC cannot speak for the users of another);
  - not too many keys for this PC and user, and for this PC as a whole, within the rate window;
  - from --presence-from up, the user confirmed this very file on their own passkey (security key or phone);
  - the user's clearance as held here (not as the PC reports it), or a grant signed by officers enrolled here.
Every release and refusal goes into this service's own hash-chained log (releases.jsonl), at once.
--reconcile compares that log with the PCs' ledgers held by the audit node: a key released for a file the PC never
recorded opening means the PC's record was suppressed.

  zenos_keysvc.py --store DIR --audit-url URL --audit-pub KEY [--port 8444 --cert C --key K] [--presence-from 3]
  zenos_keysvc.py --store DIR --audit-store DIR ...       (the audit node's store, when both run as one account)
      [--notify-url http://127.0.0.1:PORT/api/send --notify-to OFFICER,OFFICER]   alerts through ZENOS Messages
  zenos_keysvc.py --store DIR --show-key                  the public key for the PCs' /etc/zenos/keysvc.json
  zenos_keysvc.py --store DIR --enroll MACHINE PUBKEY     (the key `zenos_auditship.py --show-key` prints)
  zenos_keysvc.py --store DIR --assign MACHINE USER       USER works on MACHINE (nobody else is served from it)
  zenos_keysvc.py --store DIR --clearance USER N
  zenos_keysvc.py --store DIR --approver NAME PUBKEY      an officer whose grant signatures count here
  zenos_keysvc.py --store DIR --messages USER NAME.12     USER's ZENOS Messages account: confirmation links go there
  zenos_keysvc.py --store DIR --origin URL --enrol-code USER [--send]   a one-time address (15 min) for USER's phone
                                                          to make its passkey on this service's own page
  zenos_keysvc.py --store DIR --passkey USER FILE.json    a passkey registered for USER (zwebauthn.register output)
  zenos_keysvc.py --store DIR --audit-store DIR --reconcile
"""
import base64, hashlib, json, os, re, secrets, ssl, sys, threading, time
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib", "zenos"))
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
sys.path.append(os.path.dirname(os.path.realpath(__file__)))     # zenos-grid package: the libraries sit beside this file
import zdecide, zident, zkeysvc, zledger, zwebauthn                          # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey   # noqa: E402
from cryptography.hazmat.primitives import serialization          # noqa: E402

NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PAGES = Path(os.environ.get("ZENOS_KEYSVC_PAGES",
                            os.path.join(os.path.dirname(os.path.realpath(__file__)), "keysvc-pages")))
FID = re.compile(r"^[0-9a-f]{32}$")
CHALLENGE_TTL = 120
MAX_CHALLENGES = 50          # open challenges per PC
SEALED_WINDOW = 600          # seconds after the key is issued within which the PC names the finished file


class StoreAudit:
    """the audit node's store on this machine (the key service and the audit node run as the same account)"""
    def __init__(self, store):
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import zenos_auditnode
        self.node = zenos_auditnode.Node.__new__(zenos_auditnode.Node)
        self.node.dir = Path(store)
        self.node.key = Ed25519PrivateKey.generate()               # only used to sign answers nobody checks here

    def health(self, machine):
        return self.node.health(machine)["health"]

    def unseals(self, machine):
        return {(u["fid"], u["actor"]) for u in self.node.unseals(machine)["unseals"]["unseals"]}


class NodeAudit:
    """an audit node reached over HTTPS; its answers must be signed with its key (as in the PCs' audit.json)"""
    def __init__(self, url, pub_b64, fetch=None):
        self.url, self.pub = url.rstrip("/"), Ed25519PublicKey.from_public_bytes(zkeysvc.unb64(pub_b64))
        self.fetch = fetch or self._get
        self.cache = {}

    def _get(self, path):
        import urllib.request
        from urllib.parse import urlparse
        u = urlparse(self.url)
        if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("the audit node must be reached over https")
        with urllib.request.urlopen(self.url + path, timeout=10,
                                    context=ssl.create_default_context() if u.scheme == "https" else None) as r:
            return json.loads(r.read())

    def _signed(self, path, field):
        a = self.fetch(path)
        self.pub.verify(zkeysvc.unb64(a["sig"]), zkeysvc.canon(a[field]))
        return a[field]

    def health(self, machine):
        c = self.cache.get(machine)
        if c and time.time() - c[0] < 2:
            return c[1]
        try:
            h = self._signed(f"/v1/health/{machine}", "health")
            if h.get("machine") != machine or abs(time.time() - float(h.get("t", 0))) > 30:
                return None
        except Exception:
            return None                                             # no trustworthy answer: no key
        self.cache[machine] = (time.time(), h)
        return h

    def unseals(self, machine):
        u = self._signed(f"/v1/unseals/{machine}", "unseals")
        if u.get("machine") != machine:
            raise ValueError("answer about another PC")
        return {(x["fid"], x["actor"]) for x in u["unseals"]}


class Service:
    def __init__(self, store, audit_store=None, silence=90, rate_max=30, rate_window=60, presence_from=6,
                 machine_rate_max=60, origin=None):
        self.dir = Path(store)
        for d in ("keys", "machines", "approvers", "passkeys", "files"):
            (self.dir / d).mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        os.chmod(self.dir / "keys", 0o700)
        self.audit = audit_store if hasattr(audit_store, "health") else (StoreAudit(audit_store) if audit_store else None)
        self.silence, self.rate_max, self.rate_window, self.presence_from = silence, rate_max, rate_window, presence_from
        self.machine_rate_max = machine_rate_max
        self.mlocks = {}
        # the address people's phones reach this service at: its pages are where passkeys are made and used,
        # so the phone shows the file as this service knows it, never as the PC describes it
        self.origin = (origin or "").rstrip("/") or None
        self.rp_id = urlparse(self.origin).hostname if self.origin else None
        (self.dir / "enrol").mkdir(exist_ok=True)
        self.key = Ed25519PrivateKey.from_private_bytes(self._secret(self.dir / "service.key"))
        self.lock = threading.Lock()
        self.nonces, self.rates, self.challenges = {}, {}, {}
        self.ledger = str(self.dir / "releases.jsonl")

    @staticmethod
    def _secret(p):
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(os.urandom(32))
        return p.read_bytes()

    def master(self, level):
        return self._secret(self.dir / "keys" / f"L{int(level)}.key")

    def pub_b64(self):
        return zkeysvc.b64(zkeysvc.raw_pub(self.key))

    # ---------- administration
    def enroll(self, machine, pub_b64):
        if not NAME.match(machine):
            raise ValueError("bad machine name")
        raw = zkeysvc.unb64(pub_b64)
        zident.check_pub(raw)                 # Ed25519 (key file) or P-256 (inside the TPM)
        (self.dir / "machines" / f"{machine}.pub").write_bytes(raw)
        self.alert("machine-enrolled", machine=machine, fingerprint=zkeysvc.fingerprint(raw))

    def assign(self, machine, user):
        """USER works on MACHINE: only then does the service act on that PC's requests for USER"""
        if not (NAME.match(machine) and NAME.match(user)):
            raise ValueError("a machine name and a user name")
        p = self.dir / "machines" / f"{machine}.users"
        users = set(p.read_text().split()) if p.exists() else set()
        p.write_text("\n".join(sorted(users | {user})) + "\n")
        self.log("user-assigned", machine, user=user)

    def assigned(self, machine, user):
        try:
            return user in (self.dir / "machines" / f"{machine}.users").read_text().split()
        except OSError:
            return False

    def machine_lock(self, machine):
        with self.lock:
            return self.mlocks.setdefault(machine, threading.Lock())

    def set_clearance(self, user, n):
        n = int(n)
        if not NAME.match(user) or not 1 <= n <= 5:
            raise ValueError("a user name and a level from 1 to 5")
        p = self.dir / "clearance"
        lines = [l for l in (p.read_text().splitlines() if p.exists() else []) if l.partition("=")[0].strip() != user]
        p.write_text("\n".join(lines + [f"{user} = {n}"]) + "\n")
        self.log("clearance-set", "admin", user=user, level=n)

    def clearance(self, user):
        try:
            for line in (self.dir / "clearance").read_text().splitlines():
                k, _, v = line.partition("=")
                if k.strip() == user:
                    return max(1, min(5, int(v.strip())))
        except (OSError, ValueError):
            pass
        return 1

    def add_approver(self, name, pub_b64):
        if not NAME.match(name):
            raise ValueError("bad officer name")
        raw = zkeysvc.unb64(pub_b64)
        Ed25519PublicKey.from_public_bytes(raw)
        (self.dir / "approvers" / f"{name}.pub").write_bytes(raw)
        self.log("approver-added", "admin", approver=name)

    def roster(self):
        return sorted(p.stem for p in (self.dir / "approvers").glob("*.pub"))

    def add_passkey(self, user, reg, notify=True):
        if not NAME.match(user):
            raise ValueError("bad user name")
        for k in ("cred_id", "public_key", "alg", "rp_id", "origin"):
            if k not in reg:
                raise ValueError("not a passkey registration: " + k)
        keys = self.passkeys(user)
        keys = [k for k in keys if k["cred_id"] != reg["cred_id"]] + [dict(reg, count=int(reg.get("count") or 0))]
        (self.dir / "passkeys" / f"{user}.json").write_text(json.dumps(keys))
        self.log("passkey-added", "admin", user=user, cred=reg["cred_id"][:16])
        if notify:
            self.alert("passkey-added", user=user, cred=reg["cred_id"][:16])
            self.send_to_person(user, "ZENOS key service: a new passkey was added for you. If this was not you, tell "
                                      "your administrator now.")

    def set_messages_account(self, user, account):
        """where this person's confirmations go: their ZENOS Messages account (on their own phone)"""
        if not NAME.match(user) or not re.match(r"^[a-z_][a-z0-9_]{2,29}\.\d{2,9}$", account):
            raise ValueError("a user name and a ZENOS Messages username (name.12)")
        (self.dir / "messages").mkdir(exist_ok=True)
        (self.dir / "messages" / user).write_text(account)
        self.log("messages-account-set", "admin", user=user, account=account)

    def messages_account(self, user):
        try:
            return (self.dir / "messages" / user).read_text().strip() or None
        except OSError:
            return None

    def send_to_person(self, user, text):
        """a message from this service's own Messages account to the person (False: no account or no sender)"""
        to = self.messages_account(user)
        if not to or self.notify is None or not self.notify.url:
            return False
        return self.notify.send_now(to, text)

    def passkeys(self, user):
        try:
            return json.loads((self.dir / "passkeys" / f"{user}.json").read_text())
        except (OSError, ValueError):
            return []

    # ---------- logs
    notify = None                                   # znotify.Notifier: alerts to the officers through ZENOS Messages

    def alert(self, event, **kw):
        with open(self.dir / "alerts.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **kw}, ensure_ascii=False) + "\n")
        if self.notify is not None:
            self.notify(event, **kw)

    def set_notify(self, conf):
        import znotify

        def failed(event, to, error):
            with open(self.dir / "alerts.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": "alert-delivery-failed",
                                    "alert": event, "to": to, "error": error}) + "\n")
        self.notify = znotify.Notifier(conf, failed) if conf else None

    def log(self, event, machine, **kw):
        zledger.append(self.ledger, event, kw.pop("user", "-"), machine, ts=time.time(), **kw)

    # ---------- the facts of one request
    def verify(self, body):
        """(req, enrolled, sig_ok, fresh)"""
        req = body.get("req") if isinstance(body, dict) else None
        if not isinstance(req, dict) or not NAME.match(str(req.get("machine", ""))):
            raise ValueError("malformed request")
        pk = self.dir / "machines" / f"{req['machine']}.pub"
        if not pk.exists():
            return req, False, False, False
        try:
            sig_ok = zident.verify(pk.read_bytes(), zkeysvc.unb64(body.get("sig", "")), zkeysvc.canon(req))
        except Exception:
            sig_ok = False
        now = time.time()
        fresh = False
        with self.lock:
            for n, t in list(self.nonces.items()):
                if now - t > 4 * zkeysvc.SKEW:
                    del self.nonces[n]
            nonce = str(req.get("nonce", ""))
            try:
                ok_t = abs(now - float(req.get("t"))) <= zkeysvc.SKEW
            except (TypeError, ValueError):
                ok_t = False
            if sig_ok and ok_t and len(nonce) >= 16 and (req["machine"], nonce) not in self.nonces:
                self.nonces[(req["machine"], nonce)] = now
                fresh = True
        return req, True, sig_ok, fresh

    def health(self, machine):
        """(last seen, every protecting service active, stopped) as the audit node last heard it"""
        if not self.audit:
            return 0, False, False
        h = self.audit.health(machine)
        if not h:
            return 0, False, False
        return float(h.get("last_seen") or 0), h.get("services_ok") is True, h.get("halted") is True

    def recent(self, key, now):
        with self.lock:
            log = [t for t in self.rates.get(key, []) if now - t <= self.rate_window]
            self.rates[key] = log
            return len(log)

    def note_release(self, key, now):
        with self.lock:
            self.rates.setdefault(key, []).append(now)

    def grant_facts(self, g):
        """the same checks as keyd, with the officers enrolled here"""
        if not isinstance(g, dict) or not isinstance(g.get("core"), dict):
            return None
        try:
            core = g["core"]
            digest = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).digest()
            approvals = []
            for a in g.get("approvals", []):
                name = os.path.basename(str(a.get("approver", "")))
                try:
                    Ed25519PublicKey.from_public_bytes((self.dir / "approvers" / f"{name}.pub").read_bytes()).verify(
                        base64.b64decode(a["sig"]), digest)
                    ok = True
                except Exception:
                    ok = False
                approvals.append({"approver": name, "sig_ok": ok})
            return {"requester": str(core.get("requester", "")), "holder": str(g.get("requester", "")),
                    "file_hash": str(core.get("file_hash", "")), "level": int(core.get("level", 0)),
                    "kind": core.get("kind"), "expires": zkeysvc.grant_expiry(g),
                    "digest_ok": base64.b64decode(g.get("digest", "")) == digest, "approvals": approvals}
        except Exception:
            return None

    def presence_facts(self, req):
        """the passkey facts for this request, or None when it carries no confirmation"""
        p = req.get("presence")
        if not isinstance(p, dict):
            return None
        if set(p) == {"challenge"}:                 # confirmed on this service's own page (/c/<challenge>)
            with self.lock:
                c = self.challenges.pop(str(p["challenge"]), None)   # one use, whatever the outcome
            bound = (c is not None and time.time() <= c["exp"] and c["machine"] == req["machine"]
                     and c["user"] == req.get("user") and c["fid"] == req.get("fid"))
            f = dict(c.get("confirmed") or {}) if bound else {}
            return {k: f.get(k) is True for k in ("registered", "sig_ok", "challenge_ok", "origin_ok", "user_verified",
                                                   "counter_ok")}
        # A signature handed in by the PC is not accepted: whoever controls the PC also controls its WebAuthn client,
        # which writes the origin and the challenge the authenticator signs, and the phone shows neither the file
        # nor the PC. Only a confirmation made on this service's own page, reached from the link sent to the
        # person's phone, counts.
        return {k: False for k in ("registered", "sig_ok", "challenge_ok", "origin_ok", "user_verified", "counter_ok")}

    # ---------- the person's own phone, on this service's pages
    def _by_token(self, token):
        """the open challenge whose page secret is `token` (the secret only ever goes to the person's phone)"""
        with self.lock:
            for ch, c in self.challenges.items():
                if secrets.compare_digest(c.get("token", ""), str(token)):
                    return ch, c
        return None, None

    def confirm_view(self, token):
        """what the confirmation page shows: the file as this service recorded it"""
        ch, c = self._by_token(token)
        if not c or time.time() > c["exp"]:
            return None
        info = self.fileinfo(c["fid"]) or {}
        return {"token": token, "user": c["user"], "machine": c["machine"], "file": info.get("name", ""),
                "level": int(info.get("level", 0)), "sealed_by": info.get("user"), "sealed_on": info.get("machine"),
                "expires": int(c["exp"]), "rp_id": self.rp_id,
                "allow": [k["cred_id"] for k in self.passkeys(c["user"]) if k.get("rp_id") == self.rp_id],
                "confirmed": bool(c.get("confirmed"))}

    def confirm(self, body):
        """a passkey signature made on /c/<token>, over the token itself (a secret the PC never sees); checked here,
        then kept with the challenge for the PC's open request (one try per challenge)"""
        try:
            token = str(body["token"])
            cdj = zwebauthn.unb64u(body["client_data_json"])
        except Exception:
            return 400, {"ok": False, "error": "malformed"}
        ch, c = self._by_token(token)
        with self.lock:
            if not c or time.time() > c["exp"] or c.get("tried"):
                return 410, {"ok": False, "error": "expired"}
            c["tried"] = True
        reg = next((k for k in self.passkeys(c["user"]) if k["cred_id"] == body.get("cred_id")), None)
        f = {"registered": reg is not None, "sig_ok": False, "challenge_ok": False, "origin_ok": False,
             "user_verified": False, "counter_ok": False}
        if reg is not None:
            try:
                facts = zwebauthn.check_assertion(reg, zwebauthn.unb64u(body["authenticator_data"]), cdj,
                                                  zwebauthn.unb64u(body["signature"]), zwebauthn.unb64u(token))
                f.update({k: facts[k] for k in ("sig_ok", "challenge_ok", "origin_ok", "user_verified", "counter_ok")})
                f["origin_ok"] = f["origin_ok"] and reg.get("origin") == self.origin
            except Exception:
                pass
        ok = all(f.values())
        if ok:
            keys = self.passkeys(c["user"])
            for k in keys:
                if k["cred_id"] == reg["cred_id"]:
                    k["count"] = facts["count"]
            (self.dir / "passkeys" / f"{c['user']}.json").write_text(json.dumps(keys))
            with self.lock:
                c["confirmed"] = f
        self.log("presence-confirmed" if ok else "presence-failed", c["machine"], user=c["user"], fid=c["fid"],
                 **({} if ok else {"facts": f}))
        if not ok:
            self.alert("presence-failed", machine=c["machine"], user=c["user"], fid=c["fid"])
        return (200 if ok else 403), {"ok": ok}

    def enrol_code(self, user, minutes=15):
        """a one-time address for USER to make a passkey for this service on their phone"""
        if not self.origin:
            raise ValueError("start the service with --origin (the address phones reach it at)")
        if not NAME.match(user):
            raise ValueError("bad user name")
        code = secrets.token_urlsafe(18)
        (self.dir / "enrol" / f"{hashlib.sha256(code.encode()).hexdigest()}.json").write_text(json.dumps(
            {"user": user, "challenge": zwebauthn.b64u(os.urandom(32)), "exp": time.time() + minutes * 60}))
        self.log("enrol-code", "admin", user=user)
        return f"{self.origin}/e/{code}"

    def _enrol_record(self, code):
        p = self.dir / "enrol" / f"{hashlib.sha256(str(code).encode()).hexdigest()}.json"
        try:
            e = json.loads(p.read_text())
        except (OSError, ValueError):
            return None, p
        return (e if time.time() <= e["exp"] else None), p

    def enrol_view(self, code):
        e, _ = self._enrol_record(code)
        return None if not e else {"user": e["user"], "challenge": e["challenge"], "rp_id": self.rp_id,
                                   "rp_name": "ZENOS key service", "expires": int(e["exp"])}

    def enrol(self, body):
        if not isinstance(body, dict):
            return 400, {"ok": False, "error": "malformed"}
        e, p = self._enrol_record(body.get("code"))
        if not e:
            return 410, {"ok": False, "error": "expired"}
        try:
            p.unlink()                                         # one use
        except OSError:
            return 410, {"ok": False, "error": "expired"}
        try:
            reg = zwebauthn.register(zwebauthn.unb64u(body["attestation_object"]),
                                     zwebauthn.unb64u(body["client_data_json"]), zwebauthn.unb64u(e["challenge"]),
                                     self.origin, self.rp_id)
        except Exception as x:
            self.log("passkey-refused", "admin", user=e["user"], reason=str(x)[:80])
            return 403, {"ok": False, "error": "passkey"}
        self.add_passkey(e["user"], reg)
        return 200, {"ok": True}

    def fileinfo(self, fid):
        try:
            return json.loads((self.dir / "files" / f"{fid}.json").read_text())
        except (OSError, ValueError):
            return None

    # ---------- the operations
    def answer(self, req, ans):
        ans = dict(ans)
        ans["sig"] = zkeysvc.b64(self.key.sign(zkeysvc.canon({"req": hashlib.sha256(zkeysvc.canon(req)).hexdigest(), **ans})))
        return ans

    def handle(self, op, body):
        try:
            req, enrolled, sig_ok, fresh = self.verify(body)
        except ValueError:
            return 400, self.answer({}, {"ok": False, "error": "malformed"})
        if req.get("op") != op:
            return 400, self.answer(req, {"ok": False, "error": "malformed"})
        machine, user = req["machine"], str(req.get("user", ""))
        try:
            level = int(req.get("level", 0))
        except (TypeError, ValueError):
            level = 0
        if not NAME.match(user) and op != "sealed":
            return 400, self.answer(req, {"ok": False, "error": "malformed"})
        if not enrolled or not sig_ok:          # nothing more is looked at for a request this PC did not sign
            return 403, self.answer(req, {"ok": False, "error": "machine" if not enrolled else "signature"})
        if op == "sealed":
            if not (enrolled and sig_ok and fresh):
                return 403, self.answer(req, {"ok": False, "error": "signature"})
            fid, fh = str(req.get("fid", "")), str(req.get("file_hash", ""))
            with self.machine_lock(machine):
                info = self.fileinfo(fid) if FID.match(fid) else None
                byhash = self.dir / "files" / "by-hash" / f"{fh}"
                # once, from the PC that sealed it, soon after the key was issued, for a digest no other file has:
                # a grant for one file can then never be pointed at another
                if (not info or info["machine"] != machine or info.get("file_hash") or not re.match(r"^[0-9a-f]{64}$", fh)
                        or time.time() - float(info.get("created", 0)) > SEALED_WINDOW or byhash.exists()):
                    return 409, self.answer(req, {"ok": False, "error": "not-open-for-hash"})
                byhash.parent.mkdir(exist_ok=True)
                byhash.write_text(fid)
                info["file_hash"] = fh
                (self.dir / "files" / f"{fid}.json").write_text(json.dumps(info))
            self.log("file-sealed", machine, user=info["user"], fid=fid, level=info["level"], file_hash=fh[:16])
            return 200, self.answer(req, {"ok": True})

        fid = str(req.get("fid", ""))
        info = None
        if op != "seal":
            info = self.fileinfo(fid) if FID.match(fid) else None
            # as with keys kept on the PC, a file opens only on the PC that sealed it
            if info is None or int(info["level"]) != level or info.get("machine") != machine:
                if enrolled and sig_ok and fresh:
                    self.log("key-refused", machine, user=user, op=op, fid=fid[:32], level=level, reason="unknown-file")
                return 404, self.answer(req, {"ok": False, "error": "unknown-file"})
        if op == "challenge":
            if not (enrolled and sig_ok and fresh) or not self.assigned(machine, user):
                return 403, self.answer(req, {"ok": False, "error": "signature" if not sig_ok else "not-assigned"})
            ch = zwebauthn.b64u(os.urandom(32))
            now = time.time()
            with self.lock:
                for k, c in list(self.challenges.items()):
                    if now > c["exp"]:
                        del self.challenges[k]
                if sum(1 for c in self.challenges.values() if c["machine"] == machine) >= MAX_CHALLENGES:
                    return 429, self.answer(req, {"ok": False, "error": "rate"})
                token = zwebauthn.b64u(os.urandom(32))
                self.challenges[ch] = {"machine": machine, "user": user, "fid": fid, "exp": now + CHALLENGE_TTL,
                                       "token": token}
            # the link (and the secret in it) goes straight to the person's own phone, never back to the PC
            sent = self.send_to_person(user, f"ZENOS key service: confirm a file you are opening on {machine}. "
                                             f"The page shows which file it is. {self.origin}/c/{token}") \
                if self.origin else False
            self.log("confirm-sent" if sent else "confirm-not-sent", machine, user=user, fid=fid)
            return 200, self.answer(req, {"ok": True, "challenge": ch, "sent": bool(sent)})
        if op not in ("seal", "open"):
            return 404, self.answer(req, {"ok": False, "error": "unknown op"})
        try:
            eph = zkeysvc.unb64(req["eph"])
            zkeysvc.X25519PublicKey.from_public_bytes(eph)
        except Exception:
            return 400, self.answer(req, {"ok": False, "error": "malformed"})
        presence = self.presence_facts(req) if op == "open" else None
        grant = self.grant_facts(req.get("grant")) if op == "open" else None
        # a grant names the finished file by its SHA-256, as the service recorded it at sealing (never as the PC says)
        fh = (info.get("file_hash") or ("unregistered:" + fid)) if op == "open" else ""
        # counting, deciding and recording happen as one step per PC, so parallel requests cannot all see room left
        with self.machine_lock(machine):
            now = time.time()
            last, services_ok, halted = self.health(machine)
            ok, by, why = zdecide.key_release(
                enrolled=enrolled, sig_ok=sig_ok, fresh=fresh, now_s=int(now), last_seen=int(last), silence=self.silence,
                services_ok=services_ok, pc_halted=halted, recent=self.recent((machine, user, op), now),
                rate_max=self.rate_max, machine_recent=self.recent((machine, op), now),
                machine_rate_max=self.machine_rate_max, assigned=self.assigned(machine, user),
                # issuing a new file key needs the same standing as opening one by clearance (no grant, no passkey)
                presence_from=self.presence_from if op == "open" else 6, presence=presence, user=user,
                clearance=self.clearance(user), level=level, file_hash=fh, roster=self.roster(), grant=grant)
            if ok and op == "seal" and by != "clearance":
                ok, why = False, "clearance"
            if not ok:
                self.log("key-refused", machine, user=user, op=op, fid=fid if op == "open" else None, level=level,
                         reason=why)
                if why in ("silent", "unhealthy", "halted"):
                    self.alert("key-refused-" + why, machine=machine, user=user, fid=fid if op == "open" else None)
                return 403, self.answer(req, {"ok": False, "error": why, "presence_needed": why == "presence"})
            if op == "seal":
                fid = secrets.token_hex(16)
                (self.dir / "files" / f"{fid}.json").write_text(json.dumps(
                    {"fid": fid, "level": level, "machine": machine, "user": user, "name": str(req.get("name", ""))[:200],
                     "created": int(now)}, ensure_ascii=False))
            w = zkeysvc.wrap(zkeysvc.file_key(self.master(level), fid, level), eph, req, fid, level)
            self.note_release((machine, user, op), now)
            self.note_release((machine, op), now)
            if op == "seal":
                self.log("key-issued", machine, user=user, fid=fid, level=level)
            else:
                self.log("key-release", machine, user=user, fid=fid, level=level, by=by, presence=presence is not None)
        return 200, self.answer(req, {"ok": True, "fid": fid, "level": level, "by": by, "wrapped": w})

    # ---------- the PCs' own records against this log
    def reconcile(self, grace=300):
        """keys released here more than `grace` seconds ago whose PC ledger (as the audit node holds it) has no
        matching unseal: the PC's record of the opening was suppressed or never sent"""
        findings = []
        try:
            rel = [json.loads(l) for l in Path(self.ledger).read_text(encoding="utf-8").splitlines() if l.strip()]
        except OSError:
            rel = []
        seen = set()
        if self.audit:
            for machine in {r.get("device") for r in rel if r.get("event") == "key-release"}:
                seen |= {(machine, fid, actor) for fid, actor in self.audit.unseals(machine)}
        done = set()
        try:
            done = {tuple(json.loads(l)["k"]) for l in (self.dir / "reconciled.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
        except OSError:
            pass
        now = time.time()
        for r in rel:
            if r.get("event") != "key-release" or now - float(r.get("ts", now)) < grace:
                continue
            k = (r["device"], r["fid"], r["actor"], r["hash"])
            if k in done:
                continue
            if (r["device"], r["fid"], r["actor"]) in seen:
                state = "recorded"
            else:
                state = "missing-on-pc"
                self.alert("release-not-in-pc-ledger", machine=r["device"], user=r["actor"], fid=r["fid"], t=r["t"])
            findings.append({"machine": r["device"], "user": r["actor"], "fid": r["fid"], "t": r["t"], "state": state})
            with open(self.dir / "reconciled.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"k": list(k), "state": state}) + "\n")
        return findings


def serve(svc, host, port, cert=None, key=None, reconcile_every=300):
    def rec():
        while True:
            time.sleep(reconcile_every)
            try:
                svc.reconcile()
            except Exception as e:
                svc.alert("reconcile-error", error=str(e)[:160])
    threading.Thread(target=rec, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def page(self, name, data):
            try:
                html = (PAGES / f"{name}.html").read_text(encoding="utf-8")
            except OSError:
                return self.reply(503, {"ok": False, "error": "page not installed"})
            body = html.replace("/*ZENOS_DATA*/null", json.dumps(data).replace("<", "\\u003c")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; img-src data:; connect-src 'self'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            m = re.match(r"^/v1/(seal|sealed|challenge|open|confirm|enrol)$", self.path)
            if not m:
                return self.reply(404, {"ok": False})
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > 1024 * 1024:
                return self.reply(413, {"ok": False, "error": "too large"})
            try:
                b = json.loads(self.rfile.read(n))
            except Exception:
                return self.reply(400, {"ok": False, "error": "not JSON"})
            if m.group(1) == "confirm":
                return self.reply(*svc.confirm(b))
            if m.group(1) == "enrol":
                return self.reply(*svc.enrol(b))
            self.reply(*svc.handle(m.group(1), b))

        def do_GET(self):
            if self.path == "/v1/service":
                return self.reply(200, {"ok": True, "pub": svc.pub_b64()})
            m = re.match(r"^/(c|e)/([A-Za-z0-9_-]{16,64})$", self.path)
            if m:
                v = svc.confirm_view(m.group(2)) if m.group(1) == "c" else svc.enrol_view(m.group(2))
                if v is None:
                    return self.reply(410, {"ok": False, "error": "expired"})
                if m.group(1) == "e":
                    v["code"] = m.group(2)
                return self.page("confirm" if m.group(1) == "c" else "enrol", v)
            self.reply(404, {"ok": False})

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer((host, port), H)
    if cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"key service on {host}:{port} ({'TLS' if cert else 'plain HTTP, local testing only'})", flush=True)
    srv.serve_forever()


def main():
    a = sys.argv[1:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if not opt("--store"):
        sys.exit(__doc__)
    audit = NodeAudit(opt("--audit-url"), opt("--audit-pub")) if opt("--audit-url") else opt("--audit-store")
    svc = Service(opt("--store"), audit, silence=int(opt("--silence-seconds", 90)),
                  rate_max=int(opt("--rate-max", 30)), rate_window=int(opt("--rate-window", 60)),
                  presence_from=int(opt("--presence-from", 6)), machine_rate_max=int(opt("--machine-rate-max", 60)),
                  origin=opt("--origin"))
    if "--show-key" in a:
        return print(svc.pub_b64())
    if opt("--notify-url"):
        svc.set_notify({"url": opt("--notify-url"), "to": [t for t in str(opt("--notify-to", "")).split(",") if t]})
    for flag, fn in (("--enroll", svc.enroll), ("--assign", svc.assign), ("--clearance", svc.set_clearance),
                     ("--approver", svc.add_approver)):
        if flag in a:
            i = a.index(flag)
            fn(a[i + 1], a[i + 2])
            return print("done")
    if "--enrol-code" in a:
        # give the address to the person in person or through their own Messages account, never through their PC
        u = a[a.index("--enrol-code") + 1]
        url = svc.enrol_code(u)
        print(url)
        if "--send" in a:
            print("sent to", svc.messages_account(u)) if svc.send_to_person(u, "ZENOS key service: set up your phone "
                  "(this link works once, for 15 minutes): " + url) else print("not sent: no Messages account or sender")
        return
    if "--messages" in a:
        i = a.index("--messages")
        svc.set_messages_account(a[i + 1], a[i + 2])
        return print("done")
    if "--passkey" in a:
        i = a.index("--passkey")
        svc.add_passkey(a[i + 1], json.loads(Path(a[i + 2]).read_text()))
        return print("done")
    if "--reconcile" in a:
        for f in svc.reconcile(grace=int(opt("--grace", 300))):
            print(json.dumps(f, ensure_ascii=False))
        return
    host = opt("--host", "0.0.0.0" if opt("--cert") else "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost") and not opt("--cert"):
        sys.exit("Listening beyond this machine needs TLS: give --cert and --key.")
    serve(svc, host, int(opt("--port", 8444)), opt("--cert"), opt("--key"))


if __name__ == "__main__":
    main()

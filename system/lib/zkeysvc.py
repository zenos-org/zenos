"""The ZENOS key service protocol: what the PC (keyd) and the key service (zenos_keysvc.py) send each other.

A sealed file made while a key service is configured ("fmt": "zks1") carries no key the PC can read. Its key is
derived on the key service from a master key for its level and the file's id, and travels to the PC wrapped for one
request only (a fresh X25519 key on each side, HKDF-SHA256, AES-256-GCM). Requests are signed with the PC's identity
key (the audit key, /etc/zenos/audit-device.key); answers are signed with the key service's own key, which the PC
knows from its configuration.

PC configuration: /etc/zenos/keysvc.json
  {"url": "https://keys.example.go.jp:8444", "pub": "<the key service's public key>",
   "machine": "pc-0042"}                    (optional; default: the audit machine name)
"""
import base64, hashlib, json, os, ssl, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlparse

import zident

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

CONF = Path(os.environ.get("ZENOS_KEYSVC_CONF", "/etc/zenos/keysvc.json"))
AUDIT_CONF = Path(os.environ.get("ZENOS_AUDIT_CONF", "/etc/zenos/audit.json"))
ID_KEY = Path(os.environ.get("ZENOS_AUDIT_KEY", "/etc/zenos/audit-device.key"))
FMT = "zks1"
SKEW = 60                     # seconds a request's time may differ from the key service's clock


def b64(b):
    return base64.b64encode(b).decode()


def unb64(s):
    return base64.b64decode(str(s), validate=True)


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def raw_pub(k):
    return k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def fingerprint(pub_raw):
    return hashlib.sha256(pub_raw).hexdigest()[:16]


def file_key(master, fid, level):
    """the key of one file: never stored, derived again on each release"""
    return HKDF(hashes.SHA256(), 32, None, b"zenos-file-key1|%s|%d" % (fid.encode(), int(level))).derive(master)


def _kek(shared, req_digest):
    return HKDF(hashes.SHA256(), 32, None, b"zenos-keysvc-wrap1|" + req_digest).derive(shared)


def wrap(dek, pc_eph_raw, req, fid, level):
    """key service side: the file key, readable only by the holder of the PC's one-time key for this request"""
    e = X25519PrivateKey.generate()
    kek = _kek(e.exchange(X25519PublicKey.from_public_bytes(pc_eph_raw)), hashlib.sha256(canon(req)).digest())
    n = os.urandom(12)
    ct = AESGCM(kek).encrypt(n, dek, b"%s|%d" % (fid.encode(), int(level)))
    return {"eph": b64(raw_pub(e)), "nonce": b64(n), "ct": b64(ct)}


def unwrap(w, pc_eph, req, fid, level):
    kek = _kek(pc_eph.exchange(X25519PublicKey.from_public_bytes(unb64(w["eph"]))), hashlib.sha256(canon(req)).digest())
    return AESGCM(kek).decrypt(unb64(w["nonce"]), unb64(w["ct"]), b"%s|%d" % (fid.encode(), int(level)))


GRANT_MAX = 24 * 3600


def grant_expiry(g):
    """A grant's own "expires" is outside what the officers signed, so it counts only up to GRANT_MAX after the
    request they signed was made ("created", inside the signed contents)."""
    from datetime import datetime
    created = datetime.strptime(str(g["core"]["created"]), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    return min(float(g["expires"]), created + GRANT_MAX)


# ---------------- PC side ----------------

class Unavailable(Exception):
    """no answer the PC can rely on (not configured, unreachable, a bad signature): the file stays closed"""


class Refused(Exception):
    def __init__(self, error, answer):
        super().__init__(error)
        self.error, self.answer = error, answer


def conf():
    """None when this PC uses no key service; a configuration that is present but unusable is an error, never a
    reason to seal with a key kept on the PC"""
    try:
        text = CONF.read_text()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Unavailable("the key service configuration cannot be read: %s" % e)
    try:
        c = json.loads(text)
        if not isinstance(c, dict) or not c.get("url") or not c.get("pub"):
            raise ValueError("url and pub are needed")
        Ed25519PublicKey.from_public_bytes(unb64(c["pub"]))
    except Exception as e:
        raise Unavailable("the key service configuration is not usable: %s" % e)
    if not c.get("machine"):
        try:
            c["machine"] = json.loads(AUDIT_CONF.read_text()).get("machine")
        except (OSError, ValueError):
            pass
    if not c.get("machine"):
        try:
            c["machine"] = "pc-" + Path("/etc/machine-id").read_text().strip()[:12]
        except OSError:
            c["machine"] = "pc-unknown"
    return c


def identity_key():
    """the PC's identity, shared with audit shipping: the TPM key when /etc/zenos/identity.json says so, otherwise
    the Ed25519 key file (zident.py)"""
    try:
        if zident.CONF.exists():
            return zident.load()
        return zident.FileIdentity(ID_KEY)
    except zident.Unavailable as e:
        raise Unavailable(str(e))


def _post(url, path, body, timeout=20):
    u = urlparse(url)
    if u.scheme != "https" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise Unavailable("the key service must be reached over https")
    req = urllib.request.Request(url.rstrip("/") + path, data=canon(body), headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl.create_default_context() if u.scheme == "https" else None) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except ValueError:
            raise Unavailable("the key service answered %d" % e.code)
    except (OSError, ValueError) as e:
        raise Unavailable("the key service is out of reach: %s" % e)


def call(op, c=None, key=None, **fields):
    """one signed request; returns (answer, the one-time key, the request) for an answer the service signed.
    Raises Refused for a signed refusal, Unavailable for anything else."""
    c = c or conf()
    if not c:
        raise Unavailable("no key service is configured")
    key = key or identity_key()
    eph = X25519PrivateKey.generate()
    req = {"op": op, "machine": c["machine"], "t": int(time.time()), "nonce": b64(os.urandom(16)),
           "eph": b64(raw_pub(eph)), **fields}
    ans = _post(c["url"], "/v1/" + op, {"req": req, "sig": b64(key.sign(canon(req)))})
    try:
        sig = ans.pop("sig")
        Ed25519PublicKey.from_public_bytes(unb64(c["pub"])).verify(unb64(sig), canon({"req": hashlib.sha256(canon(req)).hexdigest(), **ans}))
    except Exception:
        raise Unavailable("the key service's answer is not signed by the configured key service")
    if not ans.get("ok"):
        raise Refused(str(ans.get("error")), ans)
    return ans, eph, req


def new_file_key(user, level, name, c=None, key=None):
    """(fid, key) for a file about to be sealed"""
    ans, eph, req = call("seal", c, key, user=user, level=int(level), name=str(name)[:200])
    fid = str(ans["fid"])
    return fid, unwrap(ans["wrapped"], eph, req, fid, int(level))


def sealed(fid, file_hash, c=None, key=None):
    """tell the service the finished file's SHA-256 (grants name the file by it)"""
    return call("sealed", c, key, fid=fid, file_hash=file_hash)[0]


def open_key(user, fid, level, grant=None, presence=None, c=None, key=None):
    ans, eph, req = call("open", c, key, user=user, fid=fid, level=int(level), grant=grant, presence=presence)
    return unwrap(ans["wrapped"], eph, req, fid, int(level)), ans


def challenge(user, fid, level, c=None, key=None):
    return call("challenge", c, key, user=user, fid=fid, level=int(level))[0]

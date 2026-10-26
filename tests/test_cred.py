"""Phone sign-in: the vault service (zenos_credd) with a software passkey standing in for the phone.

The passkey makes real WebAuthn data (P-256 signatures over authenticator data and client data, PRF by HMAC), so the
service's checks and the proven decision (ZenosFormal/Cred.lean) run exactly as with a phone.
"""
import hashlib, hmac, importlib.util, json, os, secrets, struct, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "system", "lib"))
os.environ.setdefault("ZENOS_CRED_DIR", tempfile.mkdtemp(prefix="zcred-"))
from cryptography.hazmat.primitives import hashes, serialization                    # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec                             # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM                       # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF                             # noqa: E402
import zwebauthn as W                                                                # noqa: E402

spec = importlib.util.spec_from_file_location("zenos_credd", os.path.join(ROOT, "system", "sbin", "zenos_credd.py"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
C.log = lambda **kw: None

PHONE_HOST = "phone.zenos.example"
PHONE = "https://" + PHONE_HOST
SITE = "https://github.com"


def cbor(v):
    def head(mt, n):
        if n < 24:
            return bytes([mt << 5 | n])
        for ai, k in ((24, 1), (25, 2), (26, 4), (27, 8)):
            if n < 1 << (8 * k):
                return bytes([mt << 5 | ai]) + n.to_bytes(k, "big")
    if isinstance(v, bool):
        return b"\xf5" if v else b"\xf4"
    if isinstance(v, int):
        return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes):
        return head(2, len(v)) + v
    if isinstance(v, str):
        return head(3, len(v.encode())) + v.encode()
    if isinstance(v, list):
        return head(4, len(v)) + b"".join(cbor(x) for x in v)
    if isinstance(v, dict):
        return head(5, len(v)) + b"".join(cbor(k) + cbor(x) for k, x in v.items())
    raise TypeError(v)


class Passkey:
    """a phone's platform passkey, in software"""

    def __init__(self, rp_id=PHONE_HOST, origin=PHONE, uv=True, counts=True):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = secrets.token_bytes(16)
        self.rp_id, self.origin, self.uv, self.counts = rp_id, origin, uv, counts
        self.count, self.prf_secret = 0, secrets.token_bytes(32)

    def _ad(self, extra=b""):
        if self.counts:
            self.count += 1
        flags = W.FLAG_UP | (W.FLAG_UV if self.uv else 0) | (W.FLAG_AT if extra else 0)
        return hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.count) + extra

    def create(self, challenge):
        n = self.key.public_key().public_numbers()
        cose = {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")}
        ad = self._ad(b"\0" * 16 + struct.pack(">H", 16) + self.cred_id + cbor(cose))
        cd = json.dumps({"type": "webauthn.create", "challenge": challenge, "origin": self.origin}).encode()
        return {"attestation_object": W.b64u(cbor({"fmt": "none", "attStmt": {}, "authData": ad})),
                "client_data_json": W.b64u(cd)}

    def get(self, challenge, salt, origin=None):
        ad = self._ad()
        cd = json.dumps({"type": "webauthn.get", "challenge": challenge, "origin": origin or self.origin}).encode()
        sig = self.key.sign(ad + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        prf = hmac.new(self.prf_secret, W.unb64u(salt), hashlib.sha256).digest()
        return {"credential_id": W.b64u(self.cred_id), "authenticator_data": W.b64u(ad),
                "client_data_json": W.b64u(cd), "signature": W.b64u(sig)}, prf


def envelope(p, prf):
    """what the phone page does: the entry's key, encrypted to the request's one-time key"""
    mine = ec.generate_private_key(ec.SECP256R1())
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), W.unb64u(p["server_key"]))
    dig = W.unb64u(p["challenge"])
    k = HKDF(algorithm=hashes.SHA256(), length=32, salt=dig, info=b"zenos-cred-prf").derive(mine.exchange(ec.ECDH(), peer))
    iv = secrets.token_bytes(12)
    return {"phone_key": W.b64u(mine.public_key().public_bytes(serialization.Encoding.X962,
                                                                serialization.PublicFormat.UncompressedPoint)),
            "iv": W.b64u(iv), "ct": W.b64u(AESGCM(k).encrypt(iv, prf, dig))}


USER = "zuser"
BROWSER, MESSENGER = 4242, 777


def h(m, pid=BROWSER):
    """one request from process `pid` of the test person"""
    return C.dispatch(USER, m, pid)


def enroll(pk):
    code = "12345678"
    C.save(USER, "enroll.json", {"hash": hashlib.sha256(code.encode()).hexdigest(), "expires": C.time.time() + 600,
                                 "tries": 0})
    s = h({"op": "enroll-start", "code": code, "origin": pk.origin, "rp_id": pk.rp_id}, MESSENGER)
    assert s["ok"], s
    return h(dict({"op": "enroll-finish", "challenge": s["challenge"], "prf": True, "name": "test phone"},
                  **pk.create(s["challenge"])), MESSENGER)


def answer(pk, p, code=None, **over):
    a, prf = pk.get(p["challenge"], p["salt"], over.pop("origin", None))
    m = dict({"op": "answer", "id": p["id"], "code": p["code"] if code is None else code}, **a, **envelope(p, prf))
    m.update(over)
    return h(m, MESSENGER)


def one_pending():
    ps = h({"op": "pending"}, MESSENGER)["pending"]
    assert len(ps) >= 1
    return ps[-1]


class CredTest(unittest.TestCase):
    def setUp(self):
        for f in ("phones.json", "vault.json", "used.json", "enroll.json"):
            try:
                os.unlink(os.path.join(C.udir(USER), f))
            except OSError:
                pass
        C.REQ.clear(); C.ASKS.clear(); C.ENROLLING.clear()
        self.pk = Passkey()
        self.assertTrue(enroll(self.pk)["ok"])

    def ask(self, kind="fill", origin=SITE, account="tanaka", **kw):
        m = {"op": "ask", "kind": kind, "origin": origin, "account": account, "tls_ok": True}
        m.update(kw)
        return h(m)

    def save_pw(self, pw="s3cret-pass", account="tanaka"):
        r = self.ask("save", account=account, password=pw)
        self.assertTrue(r["ok"], r)
        p = one_pending()
        p["code"] = r["code"]
        self.assertEqual(answer(self.pk, p)["result"], "approved")
        self.assertTrue(h({"op": "wait", "id": r["id"]})["ok"])

    def fill(self, **over):
        r = self.ask()
        self.assertTrue(r["ok"], r)
        p = one_pending()
        p["code"] = r["code"]
        a = answer(self.pk, p, **over)
        return r, p, a, h({"op": "wait", "id": r["id"]})

    def test_save_then_fill(self):
        self.save_pw()
        vault = json.dumps(C.vault(USER))
        self.assertNotIn("s3cret-pass", vault)                      # at rest only ciphertext
        r, p, a, w = self.fill()
        self.assertEqual(a["result"], "approved")
        self.assertEqual(w, {"ok": True, "account": "tanaka", "password": "s3cret-pass"})
        self.assertIn(r["code"], p["codes"])
        self.assertEqual(len(set(p["codes"])), 3)

    def test_wrong_code_burns_the_request(self):
        self.save_pw()
        r = self.ask()
        p = one_pending()
        wrong = next(c for c in p["codes"] if c != r["code"])
        self.assertEqual(answer(self.pk, p, code=wrong)["error"], "code-mismatch")
        self.assertEqual(answer(self.pk, p, code=r["code"])["error"], "already-answered")   # one try
        self.assertEqual(h({"op": "wait", "id": r["id"]})["error"], "code-mismatch")

    def test_replay_onto_another_request(self):
        self.save_pw()
        r1 = self.ask()
        p1 = one_pending()
        a1, prf = self.pk.get(p1["challenge"], p1["salt"])
        h({"op": "cancel", "id": r1["id"]})
        r2 = self.ask()
        p2 = one_pending()
        m = dict({"op": "answer", "id": p2["id"], "code": r2["code"]}, **a1, **envelope(p2, prf))
        self.assertEqual(h(m, MESSENGER)["error"], "not-for-this-request")

    def test_signed_on_another_page(self):
        self.save_pw()
        r, p, a, w = self.fill(origin="https://evil.example")
        self.assertEqual(a["error"], "wrong-phone-page")
        self.assertFalse(w["ok"])

    def test_person_not_verified(self):
        self.save_pw()
        self.pk.uv = False
        r, p, a, w = self.fill()
        self.assertEqual(a["error"], "person-not-verified")

    def test_cloned_passkey(self):
        self.save_pw()
        self.pk.count -= 2                         # a copy of the key, behind the real one's counter
        r, p, a, w = self.fill()
        self.assertEqual(a["error"], "cloned-passkey")

    def test_unregistered_phone(self):
        self.save_pw()
        other = Passkey()
        r = self.ask()
        p = one_pending()
        self.assertEqual(answer(other, p, code=r["code"])["error"], "unknown-phone")

    def test_tampered_envelope(self):
        self.save_pw()
        r = self.ask()
        p = one_pending()
        self.assertEqual(answer(self.pk, p, code=r["code"], ct=W.b64u(b"x" * 48))["error"], "bad-key-envelope")

    def test_not_https_verified(self):
        self.save_pw()
        r = self.ask(tls_ok=False)
        p = one_pending()
        self.assertEqual(answer(self.pk, p, code=r["code"])["error"], "not-verified-https")

    def test_other_site_gets_nothing(self):
        self.save_pw()
        self.assertEqual(self.ask(origin="https://github.com.evil.example")["error"], "nothing-saved")
        self.assertEqual(self.ask(origin="http://github.com")["error"], "bad request")

    def test_only_the_asking_process_gets_the_password(self):
        self.save_pw()
        r = self.ask()
        self.assertEqual(h({"op": "wait", "id": r["id"]}, pid=9999)["error"], "unknown request")

    def test_decline(self):
        self.save_pw()
        r = self.ask()
        p = one_pending()
        self.assertEqual(h({"op": "answer", "id": p["id"], "decline": True}, MESSENGER)["result"], "declined")
        self.assertEqual(h({"op": "wait", "id": r["id"]})["error"], "declined-on-phone")

    def test_prompt_flood_is_bounded(self):
        self.save_pw()
        C.ASKS.clear()
        oks = [self.ask()["ok"] for _ in range(6)]
        self.assertEqual(oks, [True, True, True, False, False, False])
        self.assertEqual(self.ask()["error"], "too-many-requests")

    def test_enrolment_code_one_use(self):
        s = h({"op": "enroll-start", "code": "12345678", "origin": PHONE, "rp_id": PHONE_HOST}, MESSENGER)
        self.assertFalse(s["ok"])
        self.assertEqual(len(C.phones(USER)), 1)

    def test_enrol_needs_verified_person(self):
        pk = Passkey(uv=False)
        self.assertFalse(enroll(pk)["ok"])

    def test_expired(self):
        self.save_pw()
        r = self.ask()
        p = one_pending()
        real = C.now_ms
        C.now_ms = lambda: real() + C.TTL_MS + 5000     # answered after the time limit
        try:
            self.assertEqual(answer(self.pk, p, code=r["code"])["error"], "expired")
        finally:
            C.now_ms = real


if __name__ == "__main__":
    unittest.main()

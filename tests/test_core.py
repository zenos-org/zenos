"""Core tests: sealed files, request digests (Python = browser), officer enrollment and the guard's approval checks.
Run: python3 -m unittest discover -s tests   (no root, no network; everything happens in a temporary home)"""
import base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="zenos-test-"))
os.environ["HOME"] = str(TMP)                      # zenos.py takes its key store from the home directory
sys.path[0:0] = [str(REPO / "system" / "lib"), str(REPO / "core" / "bin"), str(REPO / "system" / "sbin")]
import zenos                                        # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey   # noqa: E402
from cryptography.hazmat.primitives import serialization                          # noqa: E402


def raw_pub(k):
    return k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class Sealing(unittest.TestCase):
    def test_roundtrip(self):
        blob = zenos.seal("予算案 2027".encode(), 4, "budget")
        h, hb, sig, ct = zenos.parse(blob)
        self.assertEqual(h["level"], 4)
        zenos.verify(hb, sig, ct)
        self.assertEqual(zenos.decrypt_ct(h, hb, ct).decode(), "予算案 2027")

    def test_level_cannot_be_changed(self):
        h, hb, sig, ct = zenos.parse(zenos.seal(b"x", 4, "n"))
        forged = hb.replace(b'"level": 4', b'"level": 1')
        self.assertNotEqual(forged, hb)
        with self.assertRaises(Exception):
            zenos.verify(forged, sig, ct)

    def test_ciphertext_cannot_be_changed(self):
        h, hb, sig, ct = zenos.parse(zenos.seal(b"secret", 3, "n"))
        bad = bytes([ct[0] ^ 1]) + ct[1:]
        with self.assertRaises(Exception):
            zenos.verify(hb, sig, bad)

    def test_not_a_zenos_file(self):
        with self.assertRaises(ValueError):
            zenos.parse(b"%PDF-1.7")


CORE = {"id": "20261019-140203-ab12", "kind": "release", "requester": "officer", "level": 4,
        "reason": "many protected files were opened at once", "created": "2026-10-19T14:02:03+0900",
        "scope": {"halt": "20261019-140203", "rule": "bulk-read",
                  "files": ["Test plan 1.zen", '予算 "案" · 2027\\x.zen', "tab\there", "😀 emoji"]}}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class BrowserDigest(unittest.TestCase):
    """the officer's browser must hash exactly what the guard hashes, or every signature fails"""
    def test_same_digest(self):
        ui = (REPO / "messenger" / "ui.html").read_text(encoding="utf-8")
        pyj = re.search(r"^const pyj=.*?;(?=\s*//)", ui, re.M).group(0)
        js = pyj + "\nconst c=JSON.parse(require('fs').readFileSync(0,'utf8'));" \
                   "process.stdout.write(require('crypto').createHash('sha256').update(pyj(c)).digest('hex'));"
        out = subprocess.run(["node", "-e", js], input=json.dumps(CORE), capture_output=True, text=True, check=True).stdout
        self.assertEqual(out, zenos.request_digest(CORE).hex())


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import zenos_guardd as G
        cls.G = G
        d = TMP / "guard"
        G.PUB, G.REQ, G.LOG, G.LEDGER = d / "approvers", d / "requests", d / "guard.jsonl", str(d / "ledger.jsonl")
        G.USER = "officer"
        G.print = lambda *a, **k: None
        cls.keys = {n: Ed25519PrivateKey.generate() for n in ("sato", "tanaka", "suzuki")}
        for n, k in cls.keys.items():
            G.enroll(n, base64.b64encode(raw_pub(k)).decode())

    def test_enroll_refuses_bad_input(self):
        with self.assertRaises(SystemExit):
            self.G.enroll("sato", "not-a-key")
        with self.assertRaises(SystemExit):
            self.G.enroll("../etc/passwd", base64.b64encode(b"\0" * 32).decode())
        self.assertEqual(self.G.roster(), ["sato", "suzuki", "tanaka"])

    def _req(self):
        return self.G.new_release(4, "bulk-read", ["/home/officer/Desktop/Red · L4/a.zen"], "h1")

    def _sig(self, who, r, decline=False):
        d = zenos.request_digest(r)
        return base64.b64encode(self.keys[who].sign(b"decline:" + d if decline else d)).decode()

    def test_release_needs_valid_signatures_and_code(self):
        G, r = self.G, self._req()
        self.assertEqual(r["required"], 3)
        ans = lambda **m: G.handle({"request": r["id"], **m})
        self.assertFalse(ans(op="approve", approver="sato", code=r["code"], sig=base64.b64encode(b"x" * 64).decode())["ok"])
        self.assertFalse(ans(op="approve", approver="mallory", code=r["code"], sig=self._sig("sato", r))["ok"])
        self.assertFalse(ans(op="approve", approver="tanaka", code=r["code"], sig=self._sig("sato", r))["ok"])
        wrong = "0000" if r["code"] != "0000" else "1111"
        self.assertFalse(ans(op="approve", approver="sato", code=wrong, sig=self._sig("sato", r))["ok"])
        self.assertTrue(ans(op="approve", approver="sato", code=r["code"], sig=self._sig("sato", r))["ok"])
        self.assertFalse(ans(op="approve", approver="sato", code=r["code"], sig=self._sig("sato", r))["ok"])   # twice
        self.assertTrue(ans(op="approve", approver="tanaka", code=r["code"], sig=self._sig("tanaka", r))["ok"])
        self.assertTrue(ans(op="approve", approver="suzuki", code=r["code"], sig=self._sig("suzuki", r))["ok"])
        stored = json.loads((G.REQ / f"{r['id']}.json").read_text())
        self.assertEqual(G.verified(stored), {"sato", "tanaka", "suzuki"})

    def test_decline_needs_a_decline_signature(self):
        G, r = self.G, self._req()
        approve_sig = self._sig("suzuki", r)
        self.assertFalse(G.handle({"op": "decline", "request": r["id"], "approver": "suzuki", "sig": approve_sig})["ok"])
        self.assertTrue(G.handle({"op": "decline", "request": r["id"], "approver": "suzuki", "sig": self._sig("suzuki", r, True)})["ok"])
        self.assertEqual(json.loads((G.REQ / f"{r['id']}.json").read_text())["status"], "declined")

    def test_tampered_request_breaks_signatures(self):
        G, r = self.G, self._req()
        sig = self._sig("sato", r)
        p = G.REQ / f"{r['id']}.json"
        t = json.loads(p.read_text())
        t["scope"]["files"] = ["something else.zen"]
        p.write_text(json.dumps(t))
        self.assertFalse(G.handle({"op": "approve", "request": r["id"], "approver": "sato", "code": r["code"], "sig": sig})["ok"])


class AccessRequests(unittest.TestCase):
    """opening a file above your level: officers sign on their own devices; only enrolled keys count"""
    @classmethod
    def setUpClass(cls):
        cls.pubdir = TMP / "etc-approvers"
        cls.pubdir.mkdir()
        zenos.APPROVER_PUB = cls.pubdir
        cls.keys = {n: Ed25519PrivateKey.generate() for n in ("sato", "tanaka")}
        for n, k in cls.keys.items():
            (cls.pubdir / f"{n}.pub").write_bytes(raw_pub(k))
        zenos.notify = lambda *a, **k: None
        cls.file = TMP / "secret.zen"
        cls.file.write_bytes(zenos.seal(b"top", 4, "secret.docx"))

    def new_request(self):
        zenos.REQ.mkdir(parents=True, exist_ok=True)
        r = {"id": "r-%s" % os.urandom(3).hex(), "requester": os.environ.get("USER", "zenos"), "file": str(self.file),
             "name": "secret.docx", "file_hash": zenos.file_hash(self.file), "level": 4, "label": zenos.LABEL[4],
             "reason": "budget review", "created": "2026-10-19T10:00:00+0900", "required": 2, "code": "4821",
             "status": "pending", "approvals": []}
        (zenos.REQ / f"{r['id']}.json").write_text(json.dumps(r))
        return r

    def sig(self, who, r, decline=False):
        d = zenos.request_digest(r)
        return base64.b64encode(self.keys[who].sign(b"decline:" + d if decline else d)).decode()

    def test_two_officer_devices_grant_access(self):
        r = self.new_request()
        self.assertFalse(zenos.signed_answer(r["id"], "sato", "approve", self.sig("sato", r), "0000")[0])        # wrong code
        self.assertFalse(zenos.signed_answer(r["id"], "tanaka", "approve", self.sig("sato", r), "4821")[0])      # someone else's signature
        self.assertFalse(zenos.signed_answer(r["id"], "mallory", "approve", self.sig("sato", r), "4821")[0])     # not enrolled
        self.assertTrue(zenos.signed_answer(r["id"], "sato", "approve", self.sig("sato", r), "4821")[0])
        self.assertIsNone(zenos.valid_grant(self.file))
        self.assertTrue(zenos.signed_answer(r["id"], "tanaka", "approve", self.sig("tanaka", r), "4821")[0])
        self.assertIsNotNone(zenos.valid_grant(self.file))

    def test_decline_is_signed(self):
        r = self.new_request()
        self.assertFalse(zenos.signed_answer(r["id"], "sato", "decline", self.sig("sato", r))[0])               # an approval is not a decline
        self.assertTrue(zenos.signed_answer(r["id"], "sato", "decline", self.sig("sato", r, True))[0])
        self.assertEqual(json.loads((zenos.REQ / f"{r['id']}.json").read_text())["status"], "declined")

    def test_user_cannot_mint_approvers(self):
        """with enrolled officers, a key the user made in their own store is worthless"""
        for g in zenos.GRANTS.glob("*.json"):
            g.unlink()
        r = self.new_request()
        forged = []
        for name in ("mallory", "eve"):
            zenos.approver_key(name)                                            # user-made keys, in the user's store
            forged.append({"approver": name, "t": "now", "sig": base64.b64encode(zenos.approver_key(name).sign(zenos.request_digest(r))).decode()})
        core = {k: r[k] for k in ("id", "requester", "file", "file_hash", "level", "reason", "created")}
        g = {"request": r["id"], "requester": r["requester"], "file_hash": r["file_hash"], "level": 4, "expires": 4e9,
             "digest": base64.b64encode(hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).digest()).decode(),
             "approvals": forged, "core": core}
        zenos.GRANTS.mkdir(parents=True, exist_ok=True)
        (zenos.GRANTS / f"{r['file_hash']}.json").write_text(json.dumps(g))
        self.assertIsNone(zenos.valid_grant(self.file))


class AuditShipping(unittest.TestCase):
    """a PC that rewrites its own ledger is caught by the audit node holding the earlier copy"""
    @classmethod
    def setUpClass(cls):
        d = TMP / "audit"
        os.environ.update(ZENOS_AUDIT_CONF=str(d / "audit.json"), ZENOS_AUDIT_KEY=str(d / "device.key"),
                          ZENOS_AUDIT_STATE=str(d / "state.json"), ZENOS_AUDIT_LOG=str(d / "ship.log"))
        import importlib, zledger, zenos_auditnode, zenos_auditship
        cls.L, cls.N, cls.S = zledger, zenos_auditnode, importlib.reload(zenos_auditship)
        cls.S.print = lambda *a, **k: None
        cls.node = cls.N.Node(d / "node")
        cls.ledger = str(d / "pc" / "access-ledger.jsonl")
        cls.key = cls.S.device_key()
        pub = base64.b64encode(raw_pub(cls.key)).decode()
        cls.node.enroll("pc-test", pub)
        (d / "audit.json").write_text(json.dumps({"machine": "pc-test", "ledgers": {"guard": cls.ledger},
                                                  "nodes": [{"name": "n", "url": "http://127.0.0.1:1", "pub": cls.node.pub_b64()}]}))
        cls.S.post = lambda url, body: cls.node.accept(json.loads(json.dumps(body)))   # the node, without the network

    def ship(self):
        self.S.ship_once(self.S.conf(), self.key, self.state)

    def test_ship_then_rewrite_is_refused(self):
        self.state = {}
        for i in range(5):
            self.L.append(self.ledger, "halt" if i == 2 else "open", "officer", "pc", file=f"f{i}.zen")
        self.ship()
        self.assertEqual(len(self.node.held("pc-test", "guard")), 5)
        for i in range(3):
            self.L.append(self.ledger, "open", "officer", "pc", file=f"g{i}.zen")
        self.ship()
        self.assertEqual(len(self.node.held("pc-test", "guard")), 8)
        # the user rewrites history on the PC: drops the halt and rebuilds a perfectly valid local chain
        with open(self.ledger, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f]
        os.unlink(self.ledger)
        for r in recs:
            if r["event"] != "halt":
                self.L.append(self.ledger, r["event"], r["actor"], r["device"], file=r["file"])
        self.assertTrue(self.L.verify(self.ledger)[0])               # locally it looks intact
        self.state = {}
        self.ship()
        self.assertEqual(len(self.node.held("pc-test", "guard")), 8)   # the node kept the original
        alerts = (self.node.dir / "alerts.jsonl").read_text()
        self.assertIn("history-rewritten", alerts)

    def test_silent_machine_is_reported(self):
        self.state = {}
        self.ship()                                                  # heartbeat even with nothing new
        self.node.check_silence(-1)
        self.assertIn("machine-silent", (self.node.dir / "alerts.jsonl").read_text())
        self.ship()
        self.assertIn("machine-back", (self.node.dir / "alerts.jsonl").read_text())

    def test_forged_batch_is_refused(self):
        b = {"machine": "pc-test", "chain": "other", "from": 0, "records": [], "sig": base64.b64encode(b"x" * 64).decode()}
        self.assertEqual(self.node.accept(b)[0], 403)
        b["machine"] = "pc-unknown"
        self.assertEqual(self.node.accept(b)[0], 403)


if __name__ == "__main__":
    unittest.main()

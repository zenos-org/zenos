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


if __name__ == "__main__":
    unittest.main()

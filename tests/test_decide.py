"""The proven decision program (formal/, zenos-decide) as the services call it (system/lib/zdecide.py).

The proofs say what the decision functions guarantee; these tests check that the program built from them answers
as the services expect, that the services' own tables agree with it, and that anything unexpected is a refusal.
Build it first: cd formal && lake build.
"""
import importlib, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/lib"))
import zdecide, zformat

ROSTER = ["sato", "suzuki", "tanaka"]


def grant(**kw):
    g = {"requester": "tanaka", "holder": "tanaka", "file_hash": "f1", "level": 4, "kind": None, "expires": 4e9,
         "digest_ok": True, "approvals": [{"approver": "sato", "sig_ok": True}, {"approver": "suzuki", "sig_ok": True}]}
    g.update(kw)
    return g


def open_(**kw):
    a = {"user": "tanaka", "clearance": 2, "level": 4, "file_hash": "f1", "halted": False, "roster": ROSTER,
         "grant": grant()}
    a.update(kw)
    return zdecide.open_file(**a)


class Decide(unittest.TestCase):
    def setUp(self):
        if not zdecide.PROGRAM:
            self.fail("zenos-decide is not built (cd formal && lake build)")

    def test_clearance_and_grant(self):
        self.assertEqual(open_(clearance=4, grant=None)[:2], (True, "clearance"))
        self.assertEqual(open_()[:2], (True, "grant"))

    def test_stopped_pc_opens_nothing(self):
        self.assertEqual(open_(clearance=5, halted=True), (False, None, "halted"))

    def test_requester_and_duplicates_do_not_count(self):
        self.assertFalse(open_(grant=grant(approvals=[{"approver": "sato", "sig_ok": True},
                                                      {"approver": "tanaka", "sig_ok": True}]))[0])
        self.assertFalse(open_(grant=grant(approvals=[{"approver": "sato", "sig_ok": True}] * 3))[0])
        self.assertFalse(open_(grant=grant(approvals=[{"approver": "sato", "sig_ok": True},
                                                      {"approver": "suzuki", "sig_ok": False}]))[0])
        self.assertFalse(open_(roster=["sato"])[0])                           # suzuki not enrolled

    def test_grant_is_bound(self):
        for bad in (dict(file_hash="f2"), dict(requester="sato"), dict(holder="sato"), dict(level=3),
                    dict(kind="plan"), dict(expires=1000), dict(digest_ok=False)):
            self.assertFalse(open_(grant=grant(**bad))[0], bad)

    def test_tables_agree(self):
        for level in range(1, 6):
            self.assertEqual(zdecide.required(level), zformat.REQUIRED[level])
        self.assertEqual(zdecide.release_required(ROSTER, "tanaka", 4), 2)
        self.assertEqual(zdecide.release_required(["tanaka"], "tanaka", 4), 1)   # no other officer: cannot be met
        self.assertEqual(zdecide.release_required(ROSTER, "tanaka", 1), 2)

    def test_answers_and_release(self):
        r = {"id": "r1", "requester": "tanaka", "level": 4, "required": 2, "status": "pending", "approvals": []}
        self.assertEqual(zdecide.approve(r, ROSTER, "tanaka", "approve", True, True), "refused:requester")
        self.assertEqual(zdecide.approve(r, ROSTER, "sato", "approve", True, False), "refused:code")
        self.assertEqual(zdecide.approve(r, ROSTER, "sato", "approve", False, True), "refused:signature")
        self.assertEqual(zdecide.approve(r, ROSTER, "kato", "approve", True, True), "refused:not enrolled")
        self.assertEqual(zdecide.approve(r, ROSTER, "sato", "decline", True, False), "declined")
        self.assertEqual(zdecide.approve(r, ROSTER, "sato", "approve", True, True), "added")
        r["approvals"] = [{"approver": "sato", "sig_ok": True}]
        self.assertEqual(zdecide.approve(r, ROSTER, "sato", "approve", True, True), "refused:already")
        self.assertEqual(zdecide.release(True, r, ROSTER), (False, ["sato"]))
        r["approvals"].append({"approver": "tanaka", "sig_ok": True})
        self.assertFalse(zdecide.release(True, r, ROSTER)[0])
        r["approvals"].append({"approver": "suzuki", "sig_ok": True})
        self.assertEqual(zdecide.release(True, r, ROSTER), (True, ["sato", "suzuki"]))
        self.assertFalse(zdecide.release(False, r, ROSTER)[0])
        self.assertFalse(zdecide.release(True, dict(r, status="declined"), ROSTER)[0])

    def test_unusual_names_pass_through_intact(self):
        names = ["佐藤 \"x\"", "a\\b", "line\nbreak"]
        r = {"id": "r1", "requester": "u", "level": 2, "required": 2, "status": "pending",
             "approvals": [{"approver": n, "sig_ok": True} for n in names]}
        self.assertEqual(zdecide.release(True, r, names), (True, sorted(names, key=names.index)))

    def test_no_program_is_a_refusal(self):
        os.environ["ZENOS_DECIDE"] = "/nonexistent/zenos-decide"
        try:
            m = importlib.reload(zdecide)
            self.assertEqual(m.open_file("tanaka", 5, 1, "f", False, ROSTER)[0], False)
            self.assertEqual(m.release(True, {"id": "r", "requester": "u", "level": 1, "required": 1,
                                              "status": "pending", "approvals": []}, ROSTER), (False, []))
            self.assertEqual(m.release_required(ROSTER, "u", 3), 1000)
        finally:
            del os.environ["ZENOS_DECIDE"]
            importlib.reload(zdecide)


class KeydGrant(unittest.TestCase):
    """keyd checks the signatures and the digest, then the decision counts: the requester's own approval never does"""

    def test_self_approved_grant_does_not_open(self):
        import base64, hashlib, json, tempfile
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        with tempfile.TemporaryDirectory() as d:
            keys = {}
            for n in ("sato", "tanaka"):
                keys[n] = Ed25519PrivateKey.generate()
                with open(os.path.join(d, n + ".pub"), "wb") as f:
                    f.write(keys[n].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
            os.environ["ZENOS_APPROVERS"] = d
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/sbin"))
            try:
                import zenos_keyd as K
                K = importlib.reload(K)
                core = {"id": "r1", "requester": "tanaka", "file": "x", "file_hash": "f1", "level": 4,
                        "reason": "r", "created": "t"}
                digest = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).digest()
                sig = lambda n: base64.b64encode(keys[n].sign(digest)).decode()
                g = {"requester": "tanaka", "expires": 4e9, "digest": base64.b64encode(digest).decode(), "core": core,
                     "approvals": [{"approver": "sato", "sig": sig("sato")}, {"approver": "tanaka", "sig": sig("tanaka")}]}
                facts = K.grant_facts(g)
                self.assertTrue(facts["digest_ok"])
                self.assertEqual([a["sig_ok"] for a in facts["approvals"]], [True, True])
                self.assertEqual(K.roster(), ["sato", "tanaka"])
                # L4 needs two officers; sato and the requester herself signed: refused
                self.assertFalse(zdecide.open_file("tanaka", 1, 4, "f1", False, K.roster(), facts)[0])
                # one officer is enough for L3
                self.assertTrue(zdecide.open_file("tanaka", 1, 3, "f1", False, K.roster(), dict(facts, level=3))[0])
                # a forged signature does not verify
                g["approvals"][0]["sig"] = sig("tanaka")
                self.assertFalse(K.grant_facts(g)["approvals"][0]["sig_ok"])
            finally:
                del os.environ["ZENOS_APPROVERS"]


class KeydStop(unittest.TestCase):
    """keyd itself: a file it sealed opens by clearance, and nothing opens while the PC is stopped"""

    def test_nothing_opens_while_stopped(self):
        import base64, json, tempfile
        with tempfile.TemporaryDirectory() as d:
            env = {"ZENOS_KEYD_KEYS": d + "/keys", "ZENOS_CLEARANCE": d + "/clearance", "ZENOS_APPROVERS": d + "/appr",
                   "ZENOS_HALT": d + "/halt.json", "ZENOS_KEYD_LOG": d + "/keyd.jsonl",
                   "ZENOS_KEYD_LEDGER": d + "/ledger.jsonl"}
            os.environ.update(env)
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/sbin"))
            try:
                import zenos_keyd as K
                K = importlib.reload(K)
                K.ensure_keys()
                uid = os.getuid()
                blob = K.handle({"op": "seal", "level": 1, "name": "memo", "data": base64.b64encode(b"hello").decode()}, uid)["blob"]
                out = K.handle({"op": "open", "blob": blob}, uid)
                self.assertTrue(out["ok"], out)
                self.assertEqual(base64.b64decode(out["data"]), b"hello")
                with open(d + "/halt.json", "w") as f:
                    json.dump({"status": "halted", "id": "h1"}, f)
                out = K.handle({"op": "open", "blob": blob}, uid)
                self.assertEqual((out["ok"], out["error"]), (False, "halted"))
                with open(d + "/halt.json", "w") as f:
                    f.write("{not json")                       # an unreadable stop file counts as stopped
                self.assertFalse(K.handle({"op": "open", "blob": blob}, uid)["ok"])
                with open(d + "/halt.json", "w") as f:
                    json.dump({"status": "released", "id": "h1"}, f)
                self.assertTrue(K.handle({"op": "open", "blob": blob}, uid)["ok"])
            finally:
                for k in env:
                    del os.environ[k]


if __name__ == "__main__":
    unittest.main()

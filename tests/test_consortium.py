"""Consortium of audit nodes: copies are compared across parties and a forked history is caught."""
import base64, hashlib, json, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "system" / "lib"))
sys.path.insert(0, str(ROOT / "system" / "sbin"))
import zledger              # noqa: E402
import zenos_auditnode as an  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402


def pc_key():
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    return k, pub


def records(path, events):
    for e in events:
        zledger.append(str(path), e, "officer", "pc-1")
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def batch(key, recs, frm=0):
    b = {"machine": "pc-1", "chain": "guard", "from": frm, "records": recs[frm:]}
    b["sig"] = base64.b64encode(key.sign(an.batch_digest(b))).decode()
    return b


class Consortium(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.a, self.b, self.c = (an.Node(t / n) for n in ("ministry", "agency", "auditor"))
        self.key, pub = pc_key()
        for n in (self.a, self.b, self.c):
            n.enroll("pc-1", pub)
        self.nodes = {"https://a": self.a, "https://b": self.b, "https://c": self.c}

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, url, machine, chain, at):
        return {"ok": True, **self.nodes[url].receipt_at(machine, chain, at)}

    def peers(self, *urls):
        return [{"name": u[-1], "url": u, "pub": self.nodes[u].pub_b64()} for u in urls]

    def test_same_history_everywhere_agrees(self):
        recs = records(Path(self.tmp.name) / "l.jsonl", ["open", "approve", "print"])
        for n in (self.a, self.b, self.c):
            self.assertEqual(n.accept(batch(self.key, recs))[0], 200)
        found = an.cross_check(self.a, self.peers("https://b", "https://c"), self.fetch)
        self.assertTrue(found and all(f["state"] == "agree" and f["common"] == 3 for f in found), found)

    def test_a_peer_that_is_behind_still_agrees(self):
        recs = records(Path(self.tmp.name) / "l.jsonl", ["open", "approve", "print"])
        self.a.accept(batch(self.key, recs))
        self.b.accept(batch(self.key, recs[:2]))
        for node, peer in ((self.a, "https://b"), (self.b, "https://a")):
            f = an.cross_check(node, self.peers(peer), self.fetch)
            self.assertEqual([x["state"] for x in f], ["agree"])
            self.assertEqual(f[0]["common"], 2)

    def test_pc_sending_two_histories_is_a_fork_on_both_sides(self):
        t = Path(self.tmp.name)
        honest = records(t / "honest.jsonl", ["open secret.zen", "print secret.zen"])
        hidden = records(t / "hidden.jsonl", ["open secret.zen", "open notes.zen"])   # rewritten second record
        self.assertEqual(self.a.accept(batch(self.key, honest))[0], 200)
        self.assertEqual(self.b.accept(batch(self.key, hidden))[0], 200)            # each node alone sees a valid chain
        fa = an.cross_check(self.a, self.peers("https://b"), self.fetch)
        fb = an.cross_check(self.b, self.peers("https://a"), self.fetch)
        self.assertEqual(fa[0]["state"], "fork")
        self.assertEqual(fb[0]["state"], "fork")
        evidence = [json.loads(l) for l in (self.a.dir / "forks.jsonl").read_text().splitlines()]
        self.assertEqual(evidence[0]["at"], 2)
        # both signed statements are kept: each party's own signature over what it held
        theirs = an.verify_receipt(self.b.pub_b64(), evidence[0]["theirs"])
        ours = an.verify_receipt(self.a.pub_b64(), evidence[0]["ours"])
        self.assertNotEqual(theirs["last"], ours["last"])
        alerts = [json.loads(l)["event"] for l in (self.a.dir / "alerts.jsonl").read_text().splitlines()]
        self.assertIn("consortium-fork", alerts)
        # checked again (every few minutes in service): still a fork, but recorded and alerted only once
        self.assertEqual(an.cross_check(self.a, self.peers("https://b"), self.fetch)[0]["state"], "fork")
        fresh = an.Node(self.a.dir)                              # and not again after a restart
        an.cross_check(fresh, self.peers("https://b"), self.fetch)
        alerts = [json.loads(l)["event"] for l in (self.a.dir / "alerts.jsonl").read_text().splitlines()]
        self.assertEqual(alerts.count("consortium-fork"), 1)
        self.assertEqual(len((self.a.dir / "forks.jsonl").read_text().splitlines()), 1)

    def test_altered_copy_on_one_node_is_caught_by_the_others(self):
        recs = records(Path(self.tmp.name) / "l.jsonl", ["open", "approve", "print"])
        for n in (self.a, self.b, self.c):
            n.accept(batch(self.key, recs))
        p = self.c.chain_path("pc-1", "guard")
        lines = p.read_text().splitlines()
        r = json.loads(lines[1]); r["event"] = "nothing happened"
        body = {k: v for k, v in r.items() if k != "hash"}
        r["hash"] = hashlib.sha256(r["prev"].encode() + zledger._canon(body)).hexdigest()
        lines[1] = json.dumps(r)
        p.write_text("\n".join(lines[:2]) + "\n")               # the auditor's copy is rewritten and cut short
        found = an.cross_check(self.a, self.peers("https://b", "https://c"), self.fetch)
        self.assertEqual({f["peer"]: f["state"] for f in found}, {"b": "agree", "c": "fork"})

    def test_a_forged_answer_is_not_accepted(self):
        recs = records(Path(self.tmp.name) / "l.jsonl", ["open"])
        self.a.accept(batch(self.key, recs))
        self.b.accept(batch(self.key, recs))
        impostor = self.peers("https://b")
        impostor[0]["pub"] = self.c.pub_b64()                   # the answer is signed by b, not the key we trust
        f = an.cross_check(self.a, impostor, self.fetch)
        self.assertEqual(f[0]["state"], "unreachable")


if __name__ == "__main__":
    unittest.main()

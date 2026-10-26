"""Where content may go, the ledger check, the pre-send check and the network sentinel's counter, as the services call
them (system/lib/zdecide.py). The proofs are in formal/ZenosFormal (Flow, Ledger, Egress). Build first:
cd formal && lake build."""
import hashlib, json, os, re, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../system/lib"))
import zdecide, zledger

HERE = os.path.dirname(__file__)


def read(p):
    with open(p) as f:
        return f.read()


class Flow(unittest.TestCase):
    def test_no_write_down(self):
        for src in range(0, 6):
            for dst in range(0, 6):
                for sink in ("folder", "window"):
                    self.assertEqual(zdecide.flow(src, sink, dst), src <= 1 or src <= dst, (src, sink, dst))

    def test_places_outside_the_levels(self):
        self.assertTrue(zdecide.flow(2, "clipboard"))
        self.assertFalse(zdecide.flow(3, "clipboard"))
        self.assertTrue(zdecide.flow(3, "printer", print_max=3))
        self.assertFalse(zdecide.flow(4, "printer", print_max=3))
        self.assertTrue(zdecide.flow(4, "printer", print_max=9))
        self.assertFalse(zdecide.flow(5, "printer", print_max=9))      # never, whatever the configuration
        self.assertFalse(zdecide.flow(5, "printer", print_max=5))

    def test_launcher_ai_table_matches_the_decision(self):
        qml = read(os.path.join(HERE, "../desktop/plasmoids/jp.zenos.launcher/contents/ui/main.qml"))
        table = json.loads(re.search(r"aiAllowed:\s*(\[\[.*?\]\])", qml).group(1).replace("'", '"'))
        sink = {"externalai": "external-ai", "govai": "gov-ai", "ministryai": "ministry-ai"}
        for level, shown in enumerate(table, start=1):
            for app, s in sink.items():
                self.assertEqual(app in shown, zdecide.flow(level, s), (level, app))

    def test_unknown_place_is_refused(self):
        self.assertFalse(zdecide.flow(1, "somewhere"))


class Ledger(unittest.TestCase):
    def test_intact_edited_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            for i in range(5):
                zledger.append(p, "open", "tanaka", "dev", n=i)
            self.assertEqual(zledger.verify(p), (True, 4, "intact"))
            lines = read(p).splitlines()
            edited = json.loads(lines[2]); edited["n"] = 99
            with open(p, "w") as f:
                f.write("\n".join(lines[:2] + [json.dumps(edited)] + lines[3:]) + "\n")
            self.assertEqual(zledger.verify(p)[:2], (False, 2))
            with open(p, "w") as f:
                f.write("\n".join(lines[:2] + lines[3:]) + "\n")
            ok, i, why = zledger.verify(p)
            self.assertEqual((ok, i), (False, 2))
            self.assertIn("prev-link", why)
            with open(p, "w") as f:
                f.write("\n".join(lines[:2] + ["{not json"] + lines[3:]) + "\n")
            self.assertEqual(zledger.verify(p)[:2], (False, 2))

    def test_audit_node_accepts_only_a_continuation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.jsonl")
            for i in range(3):
                zledger.append(p, "open", "tanaka", "dev", n=i)
            recs = [json.loads(l) for l in read(p).splitlines()]
            head = recs[1]["hash"]
            self.assertEqual(zdecide.chain(head, zledger.facts(recs[2:]))[:2], (True, None))
            self.assertFalse(zdecide.chain(head, zledger.facts(recs[1:]))[0])      # does not continue the held head
            self.assertEqual(zdecide.chain(zledger.GENESIS, zledger.facts(recs))[3], recs[-1]["hash"])


class Send(unittest.TestCase):
    def test_only_sealed_goes_out(self):
        self.assertEqual(zdecide.send(False, True, 10, 100, True), (False, "plaintext-or-unsealed"))
        self.assertEqual(zdecide.send(True, False, 10, 100, True), (False, "invalid-or-tampered"))
        self.assertEqual(zdecide.send(True, True, 101, 100, False), (False, "too-large-needs-approval"))
        self.assertEqual(zdecide.send(True, True, 101, 100, True), (True, "sealed-ok"))
        self.assertEqual(zdecide.send(True, True, 100, 100, False), (True, "sealed-ok"))


class Egress(unittest.TestCase):
    def test_window_threshold_and_cut(self):
        e = zdecide.EgressStream(3000, 1000)
        try:
            self.assertFalse(e.send("1 a", "a", False, 0, 600))
            self.assertTrue(e.send("1 a", "a", False, 2000, 600))          # 1200 bytes within 3 s
            self.assertFalse(e.send("1 a", "a", False, 2100, 5000))        # already cut: no second cut
            self.assertFalse(e.send("2 b", "b", False, 0, 600))
            self.assertFalse(e.send("2 b", "b", False, 4000, 600))         # 4 s apart: the first one fell out
            self.assertFalse(e.send("3 c", "c", True, 0, 10 ** 9))         # approved network
        finally:
            e.close()

    def test_no_program_cuts(self):
        e = zdecide.EgressStream(3000, 1000)
        e.args[0] = "/nonexistent/zenos-decide"
        self.assertTrue(e.send("1 a", "a", False, 0, 1))


if __name__ == "__main__":
    unittest.main()

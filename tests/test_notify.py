"""Alerts reach the officers through ZENOS Messages (a stand-in Messages client on 127.0.0.1 here)."""
import json, socket, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[0:0] = [str(REPO / "system" / "lib"), str(REPO / "system" / "sbin")]
import znotify                                                     # noqa: E402

SENT = []


class FakeMessages(BaseHTTPRequestHandler):
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok = b["to"] != "unknown.99"
        if ok:
            SENT.append(b)
        out = json.dumps({"ok": True} if ok else {"error": "no such account"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class Alerts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeMessages)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}/api/send"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    def setUp(self):
        SENT.clear()

    def test_silent_pc_reaches_the_officers(self):
        import zenos_auditnode
        node = zenos_auditnode.Node(Path(tempfile.mkdtemp()) / "audit")
        node.set_notify({"url": self.url, "to": ["sato.01", "tanaka.02"]})
        (node.dir / "machines" / "pc-7.seen").write_text(str(time.time() - 120))
        t = time.time()
        node.check_silence(90)
        node.notify.drain()
        self.assertEqual(sorted(m["to"] for m in SENT), ["sato.01", "tanaka.02"])
        self.assertIn("pc-7 stopped reporting 90 s ago", SENT[0]["text"])
        self.assertLess(time.time() - t, 5)
        self.assertIn("machine-silent", (node.dir / "alerts.jsonl").read_text())

    def test_key_service_refusal_and_failed_delivery_are_recorded(self):
        import zenos_keysvc
        svc = zenos_keysvc.Service(Path(tempfile.mkdtemp()) / "keys")
        svc.set_notify({"url": self.url, "to": ["sato.01", "unknown.99"]})
        svc.alert("key-refused-unhealthy", machine="pc-3", user="tanaka", fid="f" * 32)
        svc.notify.drain(15)
        time.sleep(7)                                          # the three tries for the unknown account
        self.assertEqual([m["to"] for m in SENT], ["sato.01"])
        self.assertIn("pc-3 asked for a key for tanaka while a protecting service was down", SENT[0]["text"])
        self.assertIn("alert-delivery-failed", (svc.dir / "alerts.jsonl").read_text())

    def test_only_a_local_messages_client(self):
        with self.assertRaises(ValueError):
            znotify.Notifier({"url": "https://relay.example/api/send", "to": ["x"]})

    def test_not_configured_sends_nothing(self):
        n = znotify.Notifier(None)
        self.assertFalse(n("machine-silent", machine="pc"))


if __name__ == "__main__":
    unittest.main()

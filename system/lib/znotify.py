"""Alerts to the officers through ZENOS Messages.

The audit node and the key service run on servers. Each server has its own ZENOS Messages account (a Messages
client running on that server, reached only on 127.0.0.1); an alert is a message from that account to the officers
named in the configuration, end-to-end encrypted like any other message. Alerts are sent in the background: a slow
or missing Messages client never holds up the audit node or a key decision. Every alert is written to alerts.jsonl
first, whether or not it is delivered; a failed delivery is written there too.

Configuration (audit node: "notify" in its config file; key service: --notify-url / --notify-to):
  {"url": "http://127.0.0.1:8790/api/send", "to": ["sato.01", "tanaka.02"], "level": 1}
"""
import json, queue, threading, time, urllib.request
from urllib.parse import urlparse

TEXT = {
    "machine-silent": "{machine} stopped reporting {seconds} s ago. Its audit shipping is off or cut from the network.",
    "machine-back": "{machine} is reporting again.",
    "service-down": "{machine}: {service} is {state}.",
    "history-rewritten": "{machine}: its {chain} ledger was rewritten at record {index}. The audit node kept its copy.",
    "broken-chain": "{machine}: a broken {chain} ledger was refused at record {index}.",
    "bad-signature": "{machine}: a batch with a bad signature was refused.",
    "bad-status-signature": "{machine}: a status with a bad signature was refused.",
    "consortium-fork": "{machine}: audit node {peer} holds a different {chain} ledger at record {at}.",
    "kernel-fix-not-applied-24h": "{machine} has not restarted into its kernel fix for a day (running {running}).",
    "release-not-in-pc-ledger": "{machine}: the key service released the key of file {fid} to {user}, but the PC's ledger has no record of opening it.",
    "key-refused-silent": "{machine} asked for a key for {user} while it was not reporting. Refused.",
    "key-refused-unhealthy": "{machine} asked for a key for {user} while a protecting service was down. Refused.",
    "key-refused-halted": "{machine} asked for a key for {user} while stopped after an anomaly. Refused.",
}


class Notifier:
    def __init__(self, conf, record_failure=None):
        conf = conf or {}
        self.url, self.to = conf.get("url"), [str(t) for t in conf.get("to") or []]
        self.level = int(conf.get("level", 1))
        self.events = set(conf.get("events") or TEXT)
        self.record_failure = record_failure
        self.q = queue.Queue(maxsize=1000)
        if self.url:
            u = urlparse(self.url)
            if u.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("the Messages client for alerts runs on this server (127.0.0.1)")
            threading.Thread(target=self._run, daemon=True).start()

    def enabled(self):
        return bool(self.url and self.to)

    def __call__(self, event, **kw):
        if not self.enabled() or event not in self.events:
            return False
        try:
            text = "ZENOS alert · " + TEXT.get(event, event).format_map(_Default(kw))
        except Exception:
            text = "ZENOS alert · " + event
        try:
            self.q.put_nowait((event, text))
            return True
        except queue.Full:
            return False

    def _send(self, to, text):
        r = urllib.request.Request(self.url, method="POST", headers={"Content-Type": "application/json"},
                                   data=json.dumps({"to": to, "text": text, "level": self.level}).encode())
        with urllib.request.urlopen(r, timeout=15) as a:
            ans = json.loads(a.read() or b"{}")
        if not ans.get("ok"):
            raise RuntimeError(str(ans.get("error") or "not sent"))

    def _run(self):
        while True:
            event, text = self.q.get()
            for to in self.to:
                for attempt in range(3):
                    try:
                        self._send(to, text)
                        break
                    except Exception as e:
                        if attempt == 2 and self.record_failure:
                            self.record_failure(event, to, str(e)[:160])
                        time.sleep(2 * (attempt + 1))

    def drain(self, timeout=10):
        """for tests: wait until the queue is empty"""
        end = time.time() + timeout
        while not self.q.empty() and time.time() < end:
            time.sleep(0.05)
        time.sleep(0.2)


class _Default(dict):
    def __missing__(self, k):
        return "?"

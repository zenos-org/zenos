"""End to end: the phone page (messenger/zcred.js) in Chromium with a virtual platform passkey (PRF, user verification),
against the vault service. Run: python3 tests/e2e_cred_phone.py  (needs Playwright with Chromium)."""
import importlib.util, json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "system", "lib"))
os.environ["ZENOS_CRED_DIR"] = tempfile.mkdtemp(prefix="zcred-e2e-")
spec = importlib.util.spec_from_file_location("zenos_credd", os.path.join(ROOT, "system", "sbin", "zenos_credd.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
import zwebauthn as W
from playwright.sync_api import sync_playwright

USER, BROWSER, MESSENGER = "zuser", 4242, 777
PAGE = """<!doctype html><meta charset=utf-8><style>:root{--side:#17181D;--line:#25262D;--bg:#0E0F13;--t-strong:#fff;--t-head:#ddd;--t-mute:#999;--t-sub:#aaa;--t-body:#ccc;--tile:#333;--acc:#3B82F6;--chipline:#444}</style>
<body><div id=box></div><script>
const $=id=>document.getElementById(id);const api=(p,o)=>fetch("/api/"+p,o).then(r=>r.json());
const post=(p,b)=>api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
const esc=s=>(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let me={remote:true,id:"zuser"};</script><script src="/zcred.js"></script><script>zcred.settings($("box"));</script></body>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE.encode(), "text/html")
        if self.path == "/zcred.js":
            return self.send(200, open(os.path.join(ROOT, "messenger", "zcred.js"), "rb").read(), "text/javascript")
        if self.path == "/api/cred/pending":
            return self.send(200, C.dispatch(USER, {"op": "pending"}, MESSENGER))
        self.send(404, {})

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        origin = "http://localhost:%d" % self.server.server_port
        if self.path == "/api/cred/enroll/start":          # the test page is http://localhost (credd wants HTTPS)
            ch = os.urandom(32)
            C.ENROLLING[W.b64u(ch)] = {"user": USER, "origin": origin, "rp_id": "localhost", "expires": time.time() + 300}
            return self.send(200, {"ok": True, "challenge": W.b64u(ch), "rp_id": "localhost", "user": USER,
                                   "user_handle": W.b64u(b"zuser-handle")})
        if self.path == "/api/cred/enroll/finish":
            r = C.dispatch(USER, dict(b, op="enroll-finish"), MESSENGER)
            return self.send(200, r if r.get("ok") else {"error": r.get("error")})
        if self.path == "/api/cred/answer":
            r = C.dispatch(USER, dict(b, op="answer"), MESSENGER)
            return self.send(200, r if r.get("ok") else {"error": r.get("error")})
        self.send(404, {})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://localhost:%d/" % srv.server_port
    ok = True
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page()
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("WebAuthn.enable")
        cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
            "protocol": "ctap2", "ctap2Version": "ctap2_1", "transport": "internal", "hasResidentKey": True,
            "hasUserVerification": True, "isUserVerified": True, "hasPrf": True, "automaticPresenceSimulation": True}})
        pg.on("console", lambda m: print("page:", m.text))
        pg.goto(url)
        pg.fill("#zcenc", "00000000"); pg.click("#zcenb")
        pg.wait_for_selector("#zcenm .ok, #zcenm .ng", timeout=15000)
        print("enrol:", pg.inner_text("#zcenm")); ok &= bool(C.phones(USER))

        def ask_and_pick(kind, pick_right=True, **kw):
            r = C.dispatch(USER, dict({"op": "ask", "kind": kind, "origin": "https://github.com", "account": "tanaka",
                                       "tls_ok": True}, **kw), BROWSER)
            assert r["ok"], r
            res = {}
            t = threading.Thread(target=lambda: res.update(C.dispatch(USER, {"op": "wait", "id": r["id"]}, BROWSER)))
            t.start()
            pg.wait_for_selector("#zcred [data-code]", timeout=10000)
            codes = [int(x) for x in pg.eval_on_selector_all("#zcred [data-code]", "e=>e.map(b=>b.dataset.code)")]
            c = r["code"] if pick_right else next(x for x in codes if x != r["code"])
            pg.click('#zcred [data-code="%d"]' % c)
            pg.wait_for_selector("#zcred .zm", timeout=15000)
            phone = pg.inner_text("#zcred .zm")
            pg.click("#zcclose")
            t.join(20)
            return phone, res

        phone, res = ask_and_pick("save", password="correct horse")
        print("save:", phone, res); ok &= res.get("ok") is True and "correct horse" not in json.dumps(C.vault(USER))
        phone, res = ask_and_pick("fill")
        print("fill:", phone, {k: v for k, v in res.items()}); ok &= res.get("password") == "correct horse"
        phone, res = ask_and_pick("fill", pick_right=False)
        print("wrong code:", phone, res); ok &= res.get("error") == "code-mismatch" and "password" not in res
        br.close()
    print("E2E", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

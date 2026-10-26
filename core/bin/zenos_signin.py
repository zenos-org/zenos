"""Sign-in with the phone, in the ZENOS Browser.

When a page asks for a password, the browser offers to sign in with the person's phone; when a password is typed
into a page, it offers to save it, protected by the phone. Both go through the vault service (zenos_credd), which
asks the phone; the person checks the site and picks on the phone the code shown here.

The page's origin is taken from the browser itself (the address of the top-level page and its TLS state), never from
the page. The script that finds password fields runs in an isolated script world, so the page's own scripts can neither
see it nor talk to the browser through it. A password from the phone is filled only into the page that asked: same
tab, same load, same origin, still over verified TLS.
"""
import json, os, socket, threading
from urllib.parse import urlparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib, Gdk

try:
    import zdistrust
except ImportError:              # the browser refuses distrusted pages anyway; this is the second check
    zdistrust = None

SOCK = os.environ.get("ZENOS_CREDD_SOCK", "/run/zenos/credd.sock")
WORLD = "zenos-signin"

PAGE_JS = r"""(() => {
  if (location.protocol !== "https:" || window.top !== window) return;
  const post = (m) => { try { m.origin = location.origin; window.webkit.messageHandlers.zsignin.postMessage(JSON.stringify(m)); } catch (e) {} };
  const shown = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const pws = () => [...document.querySelectorAll("input[type=password]")].filter(shown);
  const userOf = (p) => {
    const scope = p.form || document;
    const before = [...scope.querySelectorAll("input")].filter((e) => shown(e) && e !== p &&
      !/^(password|hidden|submit|button|checkbox|radio|file|image|reset)$/i.test(e.type) &&
      (e.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING));
    return before.pop() || document.querySelector("input[autocomplete~=username],input[type=email]");
  };
  let found = false;
  const look = () => { if (!found && pws().length) { found = true; post({ t: "found" }); } };
  new MutationObserver(look).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["type", "style", "class"] });
  look();
  let last = "";
  const sent = () => {
    const p = pws().find((x) => x.value);
    if (!p || p.dataset.zenosFilled === "1") return;
    const u = userOf(p), key = (u ? u.value : "") + "\u0000" + p.value;
    if (key === last) return;
    last = key;
    post({ t: "typed", account: u ? u.value : "", password: p.value });
  };
  document.addEventListener("submit", sent, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target && e.target.type === "password") sent(); }, true);
  document.addEventListener("click", (e) => { const b = e.target && e.target.closest && e.target.closest("button,input[type=submit],[role=button]"); if (b) sent(); }, true);
  window.__zenosFill = (account, password) => {
    const p = pws()[0];
    if (!p) return false;
    const set = (el, v) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const u = userOf(p);
    if (u && account && !u.value) set(u, account);
    set(p, password);
    p.dataset.zenosFilled = "1";
    return true;
  };
})();"""

CSS = b"""
#zsignin{background:#1C1C21;border-bottom:1px solid #2C2C33;padding:8px 14px}
#zsignin label{color:#E5E5EA;font:13px Inter,sans-serif}
#zsignin .zcode{color:#FFFFFF;font:600 18px Inter,sans-serif;background:#2C2C33;border-radius:8px;padding:2px 12px}
#zsignin .zmute{color:#98989D}
#zsignin .zng{color:#FF8A80}
#zsignin button{background:#2C2C33;color:#E5E5EA;border:0;border-radius:7px;padding:4px 14px;box-shadow:none;background-image:none}
#zsignin button.zgo{background:#0A84FF;color:#FFFFFF}
"""

ERRORS = {
    "no-phone": "No phone is set up for sign-in.",
    "nothing-saved": "Nothing is saved for this site.",
    "too-many-requests": "Too many requests in a minute. Try again shortly.",
    "declined-on-phone": "Declined on your phone.",
    "code-mismatch": "The code picked on the phone was not the one shown here. Nothing was filled.",
    "expired": "The request expired.",
    "not-verified-https": "This page's connection could not be verified.",
    "already-answered": "This request was already answered.",
    "bad-signature": "The phone's signature did not verify.",
    "not-for-this-request": "The phone's approval was not for this request.",
    "wrong-phone-page": "The approval did not come from your phone's ZENOS page.",
    "person-not-verified": "The phone did not verify you (fingerprint, face or PIN).",
    "cloned-passkey": "The phone's key looks copied. Sign-in with it is refused; tell your administrator.",
    "unknown-phone": "That phone is not registered for sign-in.",
    "wrong-phone-key": "This password was saved with another phone.",
    "cancelled": "Cancelled.",
}


def credd(msg, timeout=10):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(SOCK)
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf or b"{}")
    except (OSError, ValueError):
        return {"ok": False, "error": "The sign-in service is not running."}


def origin_of(uri):
    try:
        u = urlparse(uri or "")
    except ValueError:
        return None
    if u.scheme != "https" or not u.hostname:
        return None
    host = u.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    return "https://" + host + ("" if u.port in (None, 443) else ":%d" % u.port)


def tls_verified(v):
    try:
        ok, cert, errors = v.get_tls_info()
    except Exception:
        return False
    if not ok or cert is None or int(errors) != 0:
        return False
    try:
        return not (zdistrust and zdistrust.blocked_gio(cert))
    except Exception:
        return False


class SignIn:
    def __init__(self, win):
        self.win = win
        self.ucm = WebKit2.UserContentManager()
        self.ucm.register_script_message_handler_in_world("zsignin", WORLD)
        self.ucm.connect("script-message-received::zsignin", self.on_msg)
        self.ucm.add_script(WebKit2.UserScript.new_for_world(
            PAGE_JS, WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserScriptInjectionTime.END, WORLD, None, None))
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.box.set_name("zsignin")
        self.widget = Gtk.Revealer()
        self.widget.add(self.box)
        self.widget.set_reveal_child(False)
        self.offer = None              # (view, generation, origin, kind) the bar is showing
        self.never = set()
        self.busy = None

    # ---------- per view
    def view_created(self, v):
        v._zgen = 0
        v.connect("load-changed", self.on_load)

    def on_load(self, v, ev):
        if ev == WebKit2.LoadEvent.COMMITTED:
            v._zgen = getattr(v, "_zgen", 0) + 1        # a new page: anything offered for the old one is void
            if self.offer and self.offer[0] is v and not self.busy:
                self.hide()

    def on_switch(self, v):
        if self.offer and self.offer[0] is not v and not self.busy:
            self.hide()

    def same_page(self, v, gen, origin):
        return (getattr(v, "_zgen", -1) == gen and origin_of(v.get_uri()) == origin and tls_verified(v)
                and v is self.win.cur)

    # ---------- messages from the isolated script world
    def on_msg(self, ucm, js_result):
        try:
            msg = json.loads(js_result.get_js_value().to_string())
        except Exception:
            return
        v = self.win.cur
        o = origin_of(v.get_uri()) if v is not None else None
        if not o or msg.get("origin") != o or not tls_verified(v) or o in self.never or self.busy:
            return                          # only the tab in front, over verified HTTPS, speaking for its own origin
        gen = v._zgen
        if msg.get("t") == "found":
            threading.Thread(target=self._offer_fill, args=(v, gen, o), daemon=True).start()
        elif msg.get("t") == "typed" and msg.get("password"):
            threading.Thread(target=self._offer_save, args=(v, gen, o, str(msg.get("account") or ""),
                                                            str(msg["password"])), daemon=True).start()

    def _offer_fill(self, v, gen, o):
        a = credd({"op": "accounts", "origin": o})
        if a.get("ok") and a.get("phone") and a.get("accounts"):
            GLib.idle_add(self.show_fill, v, gen, o, a["accounts"])

    def _offer_save(self, v, gen, o, account, password):
        a = credd({"op": "accounts", "origin": o})
        if a.get("ok") and a.get("phone"):
            GLib.idle_add(self.show_save, v, gen, o, account, password, account in a.get("accounts", []))

    # ---------- the bar
    def clear(self):
        for c in self.box.get_children():
            self.box.remove(c)

    def label(self, text, cls=None, expand=False):
        l = Gtk.Label(label=text)
        l.set_xalign(0)
        l.set_line_wrap(True)
        if cls:
            l.get_style_context().add_class(cls)
        self.box.pack_start(l, expand, expand, 0)
        return l

    def button(self, text, cb, go=False):
        b = Gtk.Button(label=text)
        if go:
            b.get_style_context().add_class("zgo")
        b.connect("clicked", lambda *_: cb())
        self.box.pack_end(b, False, False, 0)
        return b

    def show(self):
        self.box.show_all()
        self.widget.set_reveal_child(True)

    def hide(self):
        self.offer = None
        self.widget.set_reveal_child(False)
        return False

    def show_fill(self, v, gen, o, accounts):
        if not self.same_page(v, gen, o) or self.busy:
            return False
        self.offer = (v, gen, o, "fill")
        self.clear()
        host = o[8:]
        self.label("Sign in to %s with your phone" % host, expand=True)
        combo = None
        if len(accounts) > 1:
            combo = Gtk.ComboBoxText()
            for x in accounts:
                combo.append_text(x)
            combo.set_active(0)
            self.box.pack_start(combo, False, False, 0)
        else:
            self.label(accounts[0], "zmute")
        self.button("Not now", self.hide)
        self.button("Sign in", lambda: self.start(v, gen, o, "fill",
                                                   combo.get_active_text() if combo else accounts[0], None), go=True)
        self.show()
        return False

    def show_save(self, v, gen, o, account, password, exists):
        if not self.same_page(v, gen, o) or self.busy:
            return False
        self.offer = (v, gen, o, "save")
        self.clear()
        what = "Update the saved password" if exists else "Save this password"
        self.label("%s for %s%s? It can then only be opened with your phone." %
                   (what, o[8:], " (%s)" % account if account else ""), expand=True)
        self.button("Never for this site", lambda: (self.never.add(o), self.hide()))
        self.button("Not now", self.hide)
        self.button("Save", lambda: self.start(v, gen, o, "save", account or o[8:], password), go=True)
        self.show()
        return False

    def start(self, v, gen, o, kind, account, password):
        if not self.same_page(v, gen, o):
            return self.hide()
        r = credd({"op": "ask", "kind": kind, "origin": o, "account": account, "password": password,
                   "tls_ok": tls_verified(v)})
        password = None
        if not r.get("ok"):
            return self.message(ERRORS.get(r.get("error"), r.get("error") or "Sign-in failed."), True)
        self.busy = r["id"]
        self.clear()
        self.label("Approve on your phone. Pick this number:", expand=False)
        self.label(" %02d " % r["code"], "zcode")
        self.label("Check that your phone shows %s." % o[8:], "zmute", expand=True)
        self.button("Cancel", lambda: credd({"op": "cancel", "id": r["id"]}))
        self.show()
        threading.Thread(target=self._wait, args=(v, gen, o, kind, r["id"]), daemon=True).start()
        return False

    def _wait(self, v, gen, o, kind, rid):
        res = credd({"op": "wait", "id": rid}, timeout=150)
        GLib.idle_add(self._done, v, gen, o, kind, res)

    def _done(self, v, gen, o, kind, res):
        self.busy = None
        if not res.get("ok"):
            return self.message(ERRORS.get(res.get("error"), res.get("error") or "Sign-in failed."), True)
        if kind == "save":
            return self.message("Saved. It opens only with your phone.")
        if not self.same_page(v, gen, o):           # the page changed while the phone was asked: fill nothing
            return self.message("The page changed before your phone answered. Nothing was filled.", True)
        script = "window.__zenosFill(%s, %s)" % (json.dumps(res.get("account") or ""), json.dumps(res["password"]))
        res = None
        v.evaluate_javascript(script, -1, WORLD, None, None, None)
        script = None
        return self.message("Signed in with your phone.")

    def message(self, text, bad=False):
        self.clear()
        self.label(text, "zng" if bad else None, expand=True)
        self.button("Close", self.hide)
        self.show()
        if not bad:
            GLib.timeout_add_seconds(4, self.hide)
        return False

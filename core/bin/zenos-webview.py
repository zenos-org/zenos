#!/usr/bin/env python3
"""Window for the ZENOS office apps (Docs, Sheets, Slides).

zenos-webview.py URL TITLE [FILE]
With FILE and ZENOS_SEALED_LEVEL set (zenos.py opening a sealed file), the window is in sealed mode: FILE is the
plaintext working copy in RAM (/dev/shm); it is loaded into the app, Save writes back to it only, nothing else may be
saved or opened from this window, and the web storage is ephemeral. zenos.py seals the file again when it closes."""
import base64, json, mimetypes, os, sys, gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, GLib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zenos_picker

url = sys.argv[1] if len(sys.argv) > 1 else 'about:blank'
title = sys.argv[2] if len(sys.argv) > 2 else 'ZENOS App'
work = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else ''
sealed = int(os.environ.get('ZENOS_SEALED_LEVEL', '0') or 0)
if sealed and not (work and work.startswith('/dev/shm/') and os.path.isfile(work)):
    sealed = 0                                   # sealed mode only ever works on a RAM copy
name = os.path.basename(work) if work else ''

win = Gtk.Window()
win.set_title(f'{title} · L{sealed} · {name}' if sealed else (f'{title} · {name}' if work else title))
win.set_default_size(1360, 860)

if sealed:   # nothing of a sealed file may stay behind in caches or web storage on disk
    view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_with_website_data_manager(WebKit2.WebsiteDataManager.new_ephemeral()))
else:
    view = WebKit2.WebView()
st = view.get_settings()
st.set_enable_developer_extras(not sealed)
# from L3 up, nothing is copied out of a sealed file (a copy would land in an unsealed, lower-level place);
# pasting in stays possible
NO_COPY = sealed >= 3
st.set_javascript_can_access_clipboard(not NO_COPY)
if NO_COPY:
    # Copy and paste between sealed windows of the same level: what is copied goes to the key agent (RAM, per user),
    # never to the X11 clipboard; it pastes into windows of the same level or higher. Copying out to anything else
    # stays impossible. Pasting in from ordinary programs works as before.
    ucm = view.get_user_content_manager()
    ucm.add_script(WebKit2.UserScript.new(r"""(() => {
const post = (h, m) => { try { window.webkit.messageHandlers[h].postMessage(m); } catch (x) {} };
const plain = t => /^(text(\/plain)?|Text)$/i.test(t);
const keep = t => { window.__zclip = t; post('zclip', t); };
window.__zclip = null;
for (const t of ['copy', 'cut']) {
  window.addEventListener(t, e => {
    e.__zt = null;
    const dt = e.clipboardData;
    if (dt) try { Object.defineProperty(dt, 'setData', { configurable: true, value: (type, v) => { if (plain(type) || e.__zt === null) e.__zt = String(v); } }); } catch (x) {}
  }, true);
  window.addEventListener(t, e => {
    const handled = e.defaultPrevented;
    e.preventDefault();
    let text = e.__zt;
    if (text == null && !handled && window.getSelection) text = String(window.getSelection());
    if (text) keep(text);
    if (t === 'cut' && !handled && text) document.execCommand('delete');
  }, false);
}
document.addEventListener('dragstart', e => { e.preventDefault(); e.stopImmediatePropagation(); post('znocopy', 'drag'); }, true);
window.addEventListener('paste', e => {
  const z = window.__zclip;
  if (z == null) return;
  e.__zp = z;
  const dt = e.clipboardData;
  const item = { kind: 'string', type: 'text/plain', getAsString: cb => cb && cb(z), getAsFile: () => null };
  if (dt) try {
    Object.defineProperty(dt, 'getData', { configurable: true, value: type => plain(type) ? z : '' });
    Object.defineProperty(dt, 'types', { configurable: true, get: () => ['text/plain'] });
    Object.defineProperty(dt, 'items', { configurable: true, get: () => Object.assign([item], { add() {}, remove() {}, clear() {} }) });
    Object.defineProperty(dt, 'files', { configurable: true, get: () => [] });
  } catch (x) {}
}, true);
window.addEventListener('paste', e => {
  if (e.__zp == null || e.defaultPrevented) return;
  e.preventDefault();
  document.execCommand('insertText', false, e.__zp);
}, false);
if (navigator.clipboard) try {
  const readText = navigator.clipboard.readText && navigator.clipboard.readText.bind(navigator.clipboard);
  const read = navigator.clipboard.read && navigator.clipboard.read.bind(navigator.clipboard);
  Object.defineProperty(navigator.clipboard, 'writeText', { value: t => { keep(String(t)); return Promise.resolve(); } });
  // apps that copy with ClipboardItems (rich text + plain text): the plain text goes to the level clipboard
  Object.defineProperty(navigator.clipboard, 'write', { value: async items => {
    for (const it of items || []) if (it && it.types && it.types.includes('text/plain')) { keep(await (await it.getType('text/plain')).text()); return; }
    post('znocopy', 'api');
    throw new DOMException('Copying out of this sealed file is not allowed.', 'NotAllowedError'); } });
  Object.defineProperty(navigator.clipboard, 'readText', { value: () => window.__zclip != null ? Promise.resolve(window.__zclip) : (readText ? readText() : Promise.resolve('')) });
  Object.defineProperty(navigator.clipboard, 'read', { value: () => window.__zclip != null && typeof ClipboardItem === 'function'
    ? Promise.resolve([new ClipboardItem({ 'text/plain': new Blob([window.__zclip], { type: 'text/plain' }) })])
    : (read ? read() : Promise.resolve([])) });
} catch (x) {}
})();""", WebKit2.UserContentInjectedFrames.ALL_FRAMES, WebKit2.UserScriptInjectionTime.START, None, None))
    _told = [0]

    def on_nocopy(*_a):
        import time
        if time.time() - _told[0] > 5:
            _told[0] = time.time()
            GLib.idle_add(tell, f'"{name}" is L{sealed}. It can only be copied into other L{sealed} (or higher) files.')
    ucm.connect('script-message-received::znocopy', on_nocopy)
    ucm.register_script_message_handler('znocopy')

    import threading, time as _time
    _sys_clip_t = [0.0]          # last time another program put something on the clipboard

    def _keyd(msg):
        try:
            import zenos
            return zenos.keyd(msg) if zenos.use_keyd() else {}
        except Exception:
            return {}

    def on_zclip(_ucm, res):
        try:
            text = res.get_js_value().to_string()
        except AttributeError:
            text = res.to_string()
        threading.Thread(target=_keyd, args=({"op": "clip-put", "level": sealed, "text": text},), daemon=True).start()
    ucm.connect('script-message-received::zclip', on_zclip)
    ucm.register_script_message_handler('zclip')

    def _set_zclip(text):
        view.evaluate_javascript("window.__zclip = %s;" % json.dumps(text), -1, None, None, None, None, None)
        return False

    def on_focus(*_a):          # a copy made in another L{sealed}+ window becomes pasteable here
        def work():
            r = _keyd({"op": "clip-get", "level": sealed})
            if r.get("text") is not None and float(r.get("t", 0)) > _sys_clip_t[0]:
                GLib.idle_add(_set_zclip, r["text"])
        threading.Thread(target=work, daemon=True).start()
        return False
    win.connect('focus-in-event', on_focus)
    # also when the page has loaded and, while this window is the active one, every two seconds (a window that was
    # already focused gets no focus event, and a page load forgets what was handed to it)
    view.connect('load-changed', lambda _v, ev: ev == WebKit2.LoadEvent.FINISHED and on_focus())
    GLib.timeout_add(2000, lambda: (win.is_active() and on_focus(), True)[1])

    from gi.repository import Gdk
    _clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

    def _ours(ev):              # X11 reports another program's selection owner as a FOREIGN window
        return ev.owner is not None and ev.owner.get_window_type() != Gdk.WindowType.FOREIGN

    def on_clipboard(clip, ev):
        if not _ours(ev):       # another program copied: a paste here takes that from now on
            _sys_clip_t[0] = _time.time()
            GLib.idle_add(_set_zclip, None)
        elif clip.wait_for_text():   # safety net: this window never leaves anything on the X11 clipboard
            clip.set_text('', 0)
    _clip.connect('owner-change', on_clipboard)

    # X11 also hands out the selected text itself (the PRIMARY selection, pasted with a middle click in any
    # program). Whenever this window takes PRIMARY, it is emptied again.
    _prim = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)

    def on_primary(clip, ev):
        if _ours(ev) and clip.wait_for_text():
            clip.set_text('', 0)
    _prim.connect('owner-change', on_primary)


# printing a sealed file: every page carries the level, the user and the time; above the policy's ceiling
# (default L3, /etc/zenos/policy.conf "print_max_level = N") printing is refused. Each attempt is recorded.
def _policy(key, default):
    try:
        for line in open('/etc/zenos/policy.conf'):
            k, _, v = line.partition('=')
            if k.strip() == key:
                return v.strip()
    except OSError:
        pass
    return default


PRINT_MAX = int(_policy('print_max_level', '3') or 3)
if sealed:
    import getpass, time as _t
    _mark = f"L{sealed} · {name} · printed by {getpass.getuser()} · {_t.strftime('%Y-%m-%d %H:%M')}"
    view.get_user_content_manager().add_style_sheet(WebKit2.UserStyleSheet.new(
        "@media print { body::after { content: %s; position: fixed; left: 0; right: 0; top: 0; padding: 4px 8px;"
        " font: 600 9pt sans-serif; color: #b00020; background: #fff; border-bottom: 1px solid #b00020; z-index: 2147483647; } }"
        % json.dumps(_mark), WebKit2.UserContentInjectedFrames.TOP_FRAME, WebKit2.UserStyleLevel.USER, None, None))


def _audit_print(allowed):
    try:
        import zenos
        zenos.audit("print" if allowed else "print-refused", file=name, level=sealed)
    except Exception:
        pass


def on_print(wv, op):
    if not sealed:
        return False
    if sealed > PRINT_MAX:
        _audit_print(False)
        GLib.idle_add(tell, f'"{name}" is L{sealed}. Files above L{PRINT_MAX} cannot be printed from this PC.')
        return True                                  # handled: nothing is printed
    _audit_print(True)
    return False


view.connect('print', on_print)


def tell(text):
    d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.INFO,
                          buttons=Gtk.ButtonsType.OK, text=text)
    d.run()
    d.destroy()


# --- native Open dialog for <input type=file> ---
def on_file_chooser(wv, request):
    if sealed:
        request.cancel()
        GLib.idle_add(tell, f'This window edits the sealed file "{name}" (L{sealed}).\nOpen other files from a new window.')
        return True
    try:
        multi = request.get_select_multiple()
    except Exception:
        multi = False
    paths = zenos_picker.open_files(win, 'Open', os.path.expanduser('~/Documents'), multiple=multi)
    if paths:
        request.select_files(paths)
    else:
        request.cancel()
    return True


view.connect('run-file-chooser', on_file_chooser)


# --- native Save dialog for downloads (Save) ---
def on_decide_destination(download, suggested):
    if sealed:
        if os.path.splitext(suggested or '')[1].lower() != os.path.splitext(work)[1].lower():
            download.cancel()
            GLib.idle_add(tell, f'"{name}" is L{sealed}. A copy in another format cannot be saved from here.')
            return True
        download.set_allow_overwrite(True)
        download.set_destination(GLib.filename_to_uri(work, None))
        download.connect('finished', lambda d: win.set_title(f'{title} · L{sealed} · {name} — saved, sealed again when you close'))
        return True
    path = zenos_picker.save_file(win, 'Save', suggested or 'ZENOS.xlsx', os.path.expanduser('~/Documents'))
    if path:
        download.set_allow_overwrite(True)   # the picker already asked before replacing
        download.set_destination(GLib.filename_to_uri(path, None))
    else:
        download.cancel()
    return True


def on_download_started(context, download):
    download.connect('decide-destination', on_decide_destination)


view.get_context().connect('download-started', on_download_started)

# --- a file given on the command line is handed to the app's own Open (its #fileinput) ---
LOAD_JS = """
const bin = atob(b64), u = new Uint8Array(bin.length);
for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
let inp = null;
for (let i = 0; i < 100 && !(inp = document.getElementById('fileinput')); i++) await new Promise(r => setTimeout(r, 100));
if (!inp) return 'no file input';
await new Promise(r => setTimeout(r, 600));                     // let the editor finish starting
const dt = new DataTransfer();
dt.items.add(new File([u], name, { type: mime }));
inp.files = dt.files;
inp.dispatchEvent(new Event('change', { bubbles: true }));
return 'loaded';
"""
_loaded = [False]


def on_load(wv, ev):
    if ev != WebKit2.LoadEvent.FINISHED or not work or _loaded[0]:
        return
    _loaded[0] = True
    with open(work, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    args = GLib.Variant('a{sv}', {'b64': GLib.Variant('s', b64), 'name': GLib.Variant('s', name),
                                  'mime': GLib.Variant('s', mimetypes.guess_type(name)[0] or 'application/octet-stream')})
    def done(v, r):
        try:
            v.call_async_javascript_function_finish(r)
        except GLib.Error:
            pass                                  # the result value itself is not needed
    wv.call_async_javascript_function(LOAD_JS, -1, args, None, None, None, done)


view.connect('load-changed', on_load)

view.load_uri(url)
win.add(view)
win.connect('destroy', Gtk.main_quit)
win.show_all()
Gtk.main()

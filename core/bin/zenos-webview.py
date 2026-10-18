#!/usr/bin/env python3
"""Window for the ZENOS office apps (Docs, Sheets, Slides).

zenos-webview.py URL TITLE [FILE]
With FILE and ZENOS_SEALED_LEVEL set (zenos.py opening a sealed file), the window is in sealed mode: FILE is the
plaintext working copy in RAM (/dev/shm); it is loaded into the app, Save writes back to it only, nothing else may be
saved or opened from this window, and the web storage is ephemeral. zenos.py seals the file again when it closes."""
import base64, mimetypes, os, sys, gi
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
st.set_javascript_can_access_clipboard(True)


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
    wv.call_async_javascript_function(LOAD_JS, -1, args, None, None, None, lambda v, r: v.call_async_javascript_function_finish(r))


view.connect('load-changed', on_load)

view.load_uri(url)
win.add(view)
win.connect('destroy', Gtk.main_quit)
win.show_all()
Gtk.main()

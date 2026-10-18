#!/usr/bin/env python3
import os, sys, gi
gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import Gtk, WebKit2, GLib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zenos_picker

url = sys.argv[1] if len(sys.argv) > 1 else 'about:blank'
title = sys.argv[2] if len(sys.argv) > 2 else 'ZENOS App'

win = Gtk.Window()
win.set_title(title)
win.set_default_size(1360, 860)

view = WebKit2.WebView()
st = view.get_settings()
st.set_enable_developer_extras(True)
st.set_javascript_can_access_clipboard(True)


# --- native Open dialog for <input type=file> ---
def on_file_chooser(wv, request):
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


# --- native Save dialog for downloads (保存) ---
def on_decide_destination(download, suggested):
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

view.load_uri(url)
win.add(view)
win.connect('destroy', Gtk.main_quit)
win.show_all()
Gtk.main()

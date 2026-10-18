#!/usr/bin/env python3
"""Read-only viewer for a sealed text file of L3 and above: no selection, no copy, no drag, no middle-click paste.
zenos_textview.py TITLE FILE      (FILE is the plaintext copy in RAM; zenos.py deletes it when the window closes)"""
import os, sys
os.environ.pop("WAYLAND_DISPLAY", None)
os.environ["GDK_BACKEND"] = "x11"
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

title, path = sys.argv[1], sys.argv[2]
with open(path, "rb") as f:
    text = f.read().decode("utf-8", errors="replace")

win = Gtk.Window(title=title)
win.set_default_size(820, 560)
sw = Gtk.ScrolledWindow()
tv = Gtk.TextView()
tv.set_editable(False)
tv.set_cursor_visible(False)
tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
tv.set_left_margin(16); tv.set_right_margin(16); tv.set_top_margin(12); tv.set_bottom_margin(12)
tv.override_font(Pango.FontDescription("Monospace 11"))
buf = tv.get_buffer()
buf.set_text(text)


def no_selection(b, it, mark):
    # a selection would also land in X11's PRIMARY buffer (middle-click paste), so none is kept
    if mark.get_name() in ("insert", "selection_bound") and b.get_has_selection():
        b.place_cursor(b.get_iter_at_mark(b.get_insert()))


buf.connect("mark-set", no_selection)
for sig in ("copy-clipboard", "cut-clipboard"):
    tv.connect(sig, lambda w, s=sig: w.stop_emission_by_name(s))
tv.connect("populate-popup", lambda w, menu: [menu.remove(c) for c in menu.get_children()])
tv.drag_source_unset()
tv.connect("drag-begin", lambda w, ctx: w.stop_emission_by_name("drag-begin"))
sw.add(tv)
win.add(sw)
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

#!/usr/bin/env python3
# ZENOS Shell - full-screen desktop (wallpaper + glass menu bar + glass dock), WebKitGTK.
import os, gi, subprocess
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, WebKit2, Gdk

HOME = os.path.expanduser("~")
SHELL = os.path.join(HOME, ".local/share/zenos/shell/shell.html")
BIN = os.path.join(HOME, ".local/share/zenos/bin")

APP_CMDS = {
    "browser": ["bash", os.path.join(BIN, "zenos-browser.sh")],
    "sheets":      ["bash", os.path.join(BIN, "zenos-sheets.sh")],
    "spreadsheet": ["bash", os.path.join(BIN, "zenos-sheets.sh")],
    "docs":        ["bash", os.path.join(BIN, "zenos-docs.sh")],
    "word":        ["bash", os.path.join(BIN, "zenos-docs.sh")],
    "slides":      ["bash", os.path.join(BIN, "zenos-slides.sh")],
    "presentation":["bash", os.path.join(BIN, "zenos-slides.sh")],
    "powerpoint":  ["bash", os.path.join(BIN, "zenos-slides.sh")],
    "office":    ["bash", os.path.join(BIN, "zenos-office.sh")],
    "documents": ["bash", os.path.join(BIN, "zenos-office.sh")],
    "calc":      ["bash", os.path.join(BIN, "zenos-office.sh"), "--calc"],
    "writer":    ["bash", os.path.join(BIN, "zenos-office.sh"), "--writer"],
    "impress":   ["bash", os.path.join(BIN, "zenos-office.sh"), "--impress"],
}


class Shell(Gtk.Window):
    def __init__(self):
        super().__init__(title="ZENOS Shell")
        try:
            self.set_wmclass("zenos-shell", "ZENOS Shell")
        except Exception:
            pass
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        try:
            scr = Gdk.Screen.get_default()
            self.set_default_size(scr.get_width(), scr.get_height())
        except Exception:
            self.set_default_size(1600, 900)
        self.move(0, 0)
        self.web = WebKit2.WebView()
        self.web.connect("decide-policy", self.on_decide)
        self.add(self.web)
        self.web.load_uri("file://" + SHELL)
        self.fullscreen()

    def on_decide(self, web, decision, dtype):
        if dtype == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri() or ""
            if uri.startswith("zenosapp://"):
                app = uri.split("://", 1)[1].strip("/")
                decision.ignore()
                self.launch(app)
                return True
        return False

    def launch(self, app):
        cmd = APP_CMDS.get(app)
        if cmd:
            env = dict(os.environ)
            env["GDK_BACKEND"] = "x11"
            env.pop("WAYLAND_DISPLAY", None)
            try:
                subprocess.Popen(cmd, env=env)
            except Exception:
                pass


def main():
    w = Shell()
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()

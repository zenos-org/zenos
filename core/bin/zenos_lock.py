#!/usr/bin/env python3
"""ZENOS stop screen (PoC). Covers the whole desktop while the PC is stopped after an anomaly.
It cannot be closed from here: it disappears only when the officers approve the emergency release."""
import json, os, sys, time
import tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zenos

BG, CARD, LINE, RED, TXT, SUB = "#0D1117", "#161B26", "#2A3142", "#EF4444", "#F3F4F6", "#9CA3AF"
F = "Inter"


def load():
    try:
        return json.loads(zenos.HALT.read_text())
    except Exception:
        return None


def renew_if_declined(h):
    """If the officers declined the release, the stop stays and a new release request is sent."""
    try:
        r = json.loads((zenos.REQ / f"{h['request']}.json").read_text())
    except Exception:
        return h
    if r["status"] == "declined":
        n = zenos.new_request("release", h["level"], h["required"], h["rule_text"], scope=r["scope"])
        h.update(request=n["id"], code=n["code"])
        zenos.HALT.write_text(json.dumps(h, ensure_ascii=False, indent=1))
        zenos.audit("release-request-renewed", halt=h["id"], request=n["id"])
    return h


root = tk.Tk()
root.title("ZENOS · Stopped")
W, H = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{W}x{H}+0+0")
root.overrideredirect(True)
root.attributes("-topmost", True)
root.configure(bg=BG)
root.protocol("WM_DELETE_WINDOW", lambda: None)
for k in ("<Escape>", "<Alt-F4>", "<Control-w>", "<Control-q>"):
    root.bind(k, lambda e: "break")

wrap = tk.Frame(root, bg=BG)
wrap.place(relx=.5, rely=.5, anchor="center")
badge = tk.Label(wrap, text="  ●  ANOMALY DETECTED  ", font=(F, 11, "bold"), fg=RED, bg="#2A1215")
badge.pack(pady=(0, 18))
title = tk.Label(wrap, text="ZENOS stopped this operation", font=(F, 30, "bold"), fg=TXT, bg=BG)
title.pack()
reason = tk.Label(wrap, text="", font=(F, 14), fg=SUB, bg=BG)
reason.pack(pady=(8, 26))

card = tk.Frame(wrap, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=28, pady=22)
card.pack()
rows = {}
for key, lab in (("t", "Detected"), ("rule", "Rule"), ("level", "Level"), ("files", "Files"),
                 ("frozen", "Stopped processes"), ("quar", "Quarantined"), ("request", "Release request")):
    fr = tk.Frame(card, bg=CARD)
    fr.pack(fill="x", pady=3)
    tk.Label(fr, text=lab, width=18, anchor="w", font=(F, 11), fg=SUB, bg=CARD).pack(side="left")
    rows[key] = tk.Label(fr, text="", anchor="w", justify="left", wraplength=640, font=(F, 11), fg=TXT, bg=CARD)
    rows[key].pack(side="left", fill="x")

rel = tk.Frame(wrap, bg=BG)
rel.pack(pady=(28, 0))
tk.Label(rel, text="Emergency release", font=(F, 12, "bold"), fg=TXT, bg=BG).pack()
need = tk.Label(rel, text="", font=(F, 11), fg=SUB, bg=BG)
need.pack(pady=(4, 10))
tk.Label(rel, text="Match code", font=(F, 10), fg=SUB, bg=BG).pack()
code = tk.Label(rel, text="", font=(F, 34, "bold"), fg=TXT, bg=BG)
code.pack()
foot = tk.Label(wrap, text="If this operation was planned, file it in advance next time and ZENOS will not stop it.\n"
                "Everything shown here is recorded in the audit log.", font=(F, 10), fg="#6B7280", bg=BG)
foot.pack(pady=(26, 0))


def refresh():
    h = load()
    if not h or h.get("status") != "halted":
        title.config(text="Released")
        badge.config(text="  ●  RELEASED BY THE OFFICERS  ", fg="#22C55E", bg="#0F2418")
        reason.config(text="Approved with officer devices. The stopped operation was cancelled; quarantined files stay in quarantine.")
        root.after(2500, root.destroy)
        return
    if not zenos.GUARDD:          # development layout: no root guard, the lock renews a declined release itself
        h = renew_if_declined(h)
    try:
        r = json.loads(zenos.request_path(h["request"]).read_text())
        got = len(r["approvals"])
    except Exception:
        got = 0
    reason.config(text=h["rule_text"][:1].upper() + h["rule_text"][1:] + ".")
    rows["t"].config(text=h["t"][:19].replace("T", " "))
    rows["level"].config(text=f"L{h['level']} · {zenos.LABEL[h['level']]}")
    rows["files"].config(text=(", ".join(h["files"]) or "none") + f"   ({len(h['files'])} total)")
    rows["frozen"].config(text=", ".join(f"{p['comm']} ({p['pid']})" for p in h["pids"]) or "none were still running")
    rows["quar"].config(text=", ".join(h["quarantined"]) or "nothing left the PC")
    rows["rule"].config(text=f"{h.get('rule','?')} — {h['rule_text']}")
    rows["request"].config(text=h.get("request", "?"))
    need.config(text=f"{h['required']} responsible officers must approve with their devices  ·  {got} of {h['required']} so far")
    code.config(text=h["code"])
    root.lift()
    root.after(1000, refresh)


root.after(50, refresh)
def hold():
    try:
        root.focus_force()
        root.grab_set_global()
    except tk.TclError:
        root.after(500, hold)


root.after(200, hold)
root.mainloop()

#!/usr/bin/env python3
"""ZENOS red-alert siren (PoC): full-screen flashing overlay + looping klaxon until acknowledged.

A red alert is meant to be impossible to ignore: the klaxon repeats and the screen flashes until a person
clicks ACKNOWLEDGE (in production, an officer action). State lives in redalert.json; clearing it also stops
the siren. Singleton via a pid file, so repeated red alerts keep one siren and refresh its message.
"""
import json, os, subprocess, sys, threading, time
import tkinter as tk

Z = os.path.expanduser("~/.local/share/zenos")
STATE = os.path.join(Z, "redalert.json")
PID = os.path.join(Z, "redalert.pid")
WAV = "/usr/local/lib/zenos/alarm.wav"
PULSE = os.environ.get("PULSE_SERVER", "unix:/mnt/wslg/PulseServer")
_stop = threading.Event()


def _siren_loop():
    env = {**os.environ, "PULSE_SERVER": PULSE}
    while not _stop.is_set():
        try:
            subprocess.run(["paplay", WAV], env=env, timeout=15)
        except Exception:
            time.sleep(1)


def _reason():
    try:
        return json.load(open(STATE)).get("text", "")
    except Exception:
        return ""


def main():
    open(PID, "w").write(str(os.getpid()))
    root = tk.Tk()
    root.title("ZENOS · RED ALERT")
    W, H = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+0+0")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#B00000")
    big = tk.Label(root, text="⚠  RED ALERT", fg="#FFFFFF", bg="#B00000",
                   font=("Inter", 120, "bold"))
    big.place(relx=0.5, rely=0.34, anchor="center")
    sub = tk.Label(root, text=_reason(), fg="#FFE5E5", bg="#B00000", font=("Inter", 30))
    sub.place(relx=0.5, rely=0.52, anchor="center")

    def ack():
        _stop.set()
        try:
            json.dump({"acknowledged": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, open(STATE + ".ack", "w"))
            os.remove(STATE)
        except Exception:
            pass
        try:
            os.remove(PID)
        except Exception:
            pass
        root.destroy()

    btn = tk.Button(root, text="ACKNOWLEDGE  (officer)", command=ack,
                    font=("Inter", 28, "bold"), bg="#FFFFFF", fg="#B00000",
                    activebackground="#FFD5D5", padx=40, pady=18, bd=0)
    btn.place(relx=0.5, rely=0.72, anchor="center")

    state = {"on": True}

    def flash():
        state["on"] = not state["on"]
        bg = "#FF2A2A" if state["on"] else "#4A0000"
        root.configure(bg=bg); big.configure(bg=bg); sub.configure(bg=bg, text=_reason())
        big.configure(fg="#FFFFFF" if state["on"] else "#FF8080")
        root.after(350, flash)

    def watch():
        # if the alert file is cleared elsewhere, stop too
        if not os.path.exists(STATE):
            ack()
            return
        root.after(500, watch)

    threading.Thread(target=_siren_loop, daemon=True).start()
    root.after(350, flash)
    root.after(500, watch)
    root.mainloop()
    _stop.set()


if __name__ == "__main__":
    main()

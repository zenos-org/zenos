"""Where ZENOS lives on this machine (shared by root services and the library).

Installed system: programs in /usr/share/zenos, this library in /usr/lib/zenos, services in /usr/sbin,
per-user data in ~/.local/share/zenos. Development layout: programs and data both in ~/.local/share/zenos,
library in /usr/local/lib/zenos. /etc/zenos/zenos.conf (KEY=value) can name the desktop user (ZENOS_USER)
and the program directory (ZENOS_ROOT)."""
import os, pwd

LIB = os.path.dirname(os.path.abspath(__file__))
SBIN = os.path.normpath(os.path.join(LIB, "..", "..", "sbin"))
CONF = "/etc/zenos/zenos.conf"


def _conf():
    out = {}
    try:
        for line in open(CONF):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def user():
    """the desktop user whose data the services protect"""
    c = _conf().get("ZENOS_USER")
    if c:
        return c
    if os.geteuid() != 0:
        return pwd.getpwuid(os.geteuid()).pw_name
    for p in pwd.getpwall():
        if p.pw_uid >= 1000 and os.path.isdir(os.path.join(p.pw_dir, ".local/share/zenos")):
            return p.pw_name
    return "zenos"


def home(u=None):
    try:
        return pwd.getpwnam(u or user()).pw_dir
    except KeyError:
        return "/home/" + (u or user())


def data(u=None):
    return os.path.join(home(u), ".local/share/zenos")


def root():
    c = _conf().get("ZENOS_ROOT")
    if c:
        return c
    return "/usr/share/zenos" if os.path.isdir("/usr/share/zenos/bin") else data()


def pulse_env(env=None):
    """sound for root services: the desktop user's PulseAudio/PipeWire socket, or whatever the session set"""
    env = dict(os.environ if env is None else env)
    if env.get("PULSE_SERVER"):
        return env
    try:
        uid = pwd.getpwnam(user()).pw_uid
        sock = "/run/user/%d/pulse/native" % uid
        if os.path.exists(sock):
            env["PULSE_SERVER"] = "unix:" + sock
        elif os.path.exists("/mnt/wslg/PulseServer"):      # development under WSL
            env["PULSE_SERVER"] = "unix:/mnt/wslg/PulseServer"
    except KeyError:
        pass
    return env

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
    # the person at the screen: owner of the running desktop session
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open("/proc/%s/comm" % d) as f:
                    if f.read().strip() in ("plasmashell", "kwin_x11", "kwin_wayland"):
                        uid = os.stat("/proc/" + d).st_uid
                        if uid >= 1000:
                            return pwd.getpwuid(uid).pw_name
            except OSError:
                continue
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
    """the user's ZENOS data folder. When a root service needs it before the user has logged in, it is
    created owned by the user (a root-owned folder would lock the user out of their own data)."""
    d = os.path.join(home(u), ".local/share/zenos")
    if os.geteuid() == 0:
        try:
            _ensure_user_dir(d, u or user())
        except Exception:
            pass
    return d


def _ensure_user_dir(d, u):
    p = pwd.getpwnam(u)
    if not os.path.isdir(p.pw_dir) or not d.startswith(p.pw_dir.rstrip("/") + "/"):
        return
    parts = os.path.relpath(d, p.pw_dir).split(os.sep)
    cur = p.pw_dir
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            return                     # never follow a link a user planted
        if not os.path.exists(cur):
            os.mkdir(cur, 0o700 if part == "zenos" else 0o755)
            os.chown(cur, p.pw_uid, p.pw_gid)
        elif part == "zenos" and os.stat(cur).st_uid == 0:
            os.chown(cur, p.pw_uid, p.pw_gid)   # repair a folder an older version created as root


def give_to_user(path, u=None):
    """a file a root service wrote into the user's data folder stays usable by the user's own programs"""
    if os.geteuid() != 0:
        return
    try:
        p = pwd.getpwnam(u or user())
        if os.path.exists(path) and not os.path.islink(path):
            os.chown(path, p.pw_uid, p.pw_gid)
    except Exception:
        pass


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

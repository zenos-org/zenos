#!/usr/bin/env python3
"""ZENOS key agent (root): holds the level keys and does every seal and unseal for the desktop users.

Without it the level keys sit in each user's home, so anyone could decrypt any level with a few lines of Python.
Here the keys belong to root (/var/lib/zenos/keys). A user gets plaintext only for files at or below their clearance
(set by the administrator in /etc/zenos/clearance), or for one exact file with a grant their officers signed
(verified here against the enrolled keys in /etc/zenos/approvers). Every unseal is written to the root ledger,
which zenos-auditship sends off the machine.

  zenos_keyd.py                      run the agent (systemd: zenos-keyd.service)
  zenos_keyd.py --clearance USER N   set a user's clearance (1-5)
Protocol: one JSON line per connection on /run/zenos/keyd.sock; the caller is identified by SO_PEERCRED.
"""
import base64, hashlib, json, os, pwd, re, socket, struct, sys, threading, time
from pathlib import Path

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "zenos")))
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")))
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
try:
    import zledger
except Exception:
    zledger = None
try:
    import zfrag
except Exception:
    zfrag = None

KEYS = Path(os.environ.get("ZENOS_KEYD_KEYS", "/var/lib/zenos/keys"))
CLEARANCE = Path(os.environ.get("ZENOS_CLEARANCE", "/etc/zenos/clearance"))
APPROVERS = Path(os.environ.get("ZENOS_APPROVERS", "/etc/zenos/approvers"))
SOCK = os.environ.get("ZENOS_KEYD_SOCK", "/run/zenos/keyd.sock")
LOG = Path(os.environ.get("ZENOS_KEYD_LOG", "/var/log/zenos/keyd.jsonl"))
LEDGER = os.environ.get("ZENOS_KEYD_LEDGER", "/var/log/zenos/access-ledger.jsonl")
MAGIC = b"ZENOS1\n"
LABEL = {1: "Public", 2: "Confidentiality 2", 3: "Confidentiality 3",
         4: "Important Economic Security Information", 5: "Specially Designated Secret"}
REQUIRED = {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}          # = zenos.REQUIRED
GRANT_CORE = ("id", "requester", "file", "file_hash", "level", "reason", "created")
MAX = 64 * 1024 * 1024


def log(**kw):
    kw = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **kw}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if zledger is not None:
        try:
            zledger.append(LEDGER, kw.get("event", "keyd"), kw.get("user", "keyd"), "keyd",
                           **{k: v for k, v in kw.items() if k not in ("t", "event", "user")})
        except Exception:
            pass


def ensure_keys():
    KEYS.mkdir(parents=True, exist_ok=True)
    os.chmod(KEYS, 0o700)
    for n in range(1, 6):
        p = KEYS / f"L{n}.key"
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(AESGCM.generate_key(bit_length=256))
    sk = KEYS / "device_ed25519"
    if not sk.exists():
        k = Ed25519PrivateKey.generate()
        fd = os.open(sk, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        (KEYS / "device_ed25519.pub").write_bytes(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    (KEYS / "frag").mkdir(exist_ok=True)
    os.chmod(KEYS / "frag", 0o700)


def clearance(user):
    try:
        for line in CLEARANCE.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == user:
                return max(1, min(5, int(v.strip())))
    except (OSError, ValueError):
        pass
    return 1                                    # not cleared: public files only, the rest goes through approval


def set_clearance(user, n):
    pwd.getpwnam(user)
    n = int(n)
    if not 1 <= n <= 5:
        sys.exit("The clearance is a level from 1 to 5.")
    lines = []
    try:
        lines = [l for l in CLEARANCE.read_text().splitlines() if l.partition("=")[0].strip() != user]
    except OSError:
        pass
    lines.append(f"{user} = {n}")
    CLEARANCE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLEARANCE.with_name(".clearance.tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, CLEARANCE)
    log(event="clearance-set", user=user, level=n, by="root")
    print(f"{user}: clearance L{n}")


def device_pub():
    return (KEYS / "device_ed25519.pub").read_bytes()


def seal(data, level, name, author):
    base = {"zenos": 1, "level": level, "label": LABEL[level], "name": name,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "author": author}
    if zfrag is not None:
        header = {**base, "alg": "AES-256-GCM-fragmented", "fmt": "zfrag2"}
        hb = json.dumps(header, ensure_ascii=False, sort_keys=True).encode()
        ct = zfrag.seal(data, level, name, str(KEYS / "frag"))
    else:
        header = {**base, "alg": "AES-256-GCM", "nonce": base64.b64encode(os.urandom(12)).decode()}
        hb = json.dumps(header, ensure_ascii=False, sort_keys=True).encode()
        ct = AESGCM((KEYS / f"L{level}.key").read_bytes()).encrypt(base64.b64decode(header["nonce"]), data, hb)
    sk = Ed25519PrivateKey.from_private_bytes((KEYS / "device_ed25519").read_bytes())
    sig = sk.sign(hb + hashlib.sha256(ct).digest())
    return MAGIC + hb + b"\n" + base64.b64encode(sig) + b"\n" + ct


def parse_verify(blob):
    if not blob.startswith(MAGIC):
        raise ValueError("not a ZENOS file")
    hb, rest = blob[len(MAGIC):].split(b"\n", 1)
    sig, ct = rest.split(b"\n", 1)
    Ed25519PublicKey.from_public_bytes(device_pub()).verify(base64.b64decode(sig), hb + hashlib.sha256(ct).digest())
    return json.loads(hb), hb, ct


def unseal(h, hb, ct):
    if h.get("fmt") == "zfrag2":
        return zfrag.open_full(ct, str(KEYS / "frag"))
    return AESGCM((KEYS / f"L{h['level']}.key").read_bytes()).decrypt(base64.b64decode(h["nonce"]), ct, hb)


def grant_ok(g, user, blob, level):
    """a grant the user's officers signed for exactly this file, still valid"""
    try:
        core = g["core"]
        digest = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).digest()
        if (base64.b64decode(g["digest"]) != digest or core.get("requester") != user or g.get("requester") != user
                or core.get("file_hash") != hashlib.sha256(blob).hexdigest() or int(core.get("level", 0)) < level
                or time.time() > float(g["expires"])):
            return False
        ok = set()
        for a in g.get("approvals", []):
            name = os.path.basename(str(a.get("approver", "")))
            try:
                Ed25519PublicKey.from_public_bytes((APPROVERS / f"{name}.pub").read_bytes()).verify(base64.b64decode(a["sig"]), digest)
                ok.add(name)
            except Exception:
                pass
        return len(ok) >= REQUIRED[level]
    except Exception:
        return False


def handle(msg, uid):
    user = pwd.getpwuid(uid).pw_name
    op = msg.get("op")
    if op == "whoami":
        return {"ok": True, "user": user, "clearance": clearance(user), "device": base64.b64encode(device_pub()).decode()}
    if op == "seal":
        level = int(msg.get("level", 0))
        if level not in LABEL:
            return {"ok": False, "error": "bad level"}
        data = base64.b64decode(msg.get("data", ""))
        name = re.sub(r'[/\\\n\r\t]', "", str(msg.get("name", "")))[:200] or "Untitled"
        blob = seal(data, level, name, user)
        log(event="seal", user=user, level=level, name=name, sha256=hashlib.sha256(blob).hexdigest()[:16])
        return {"ok": True, "blob": base64.b64encode(blob).decode()}
    if op in ("verify", "open"):
        blob = base64.b64decode(msg.get("blob", ""))
        try:
            h, hb, ct = parse_verify(blob)
        except Exception:
            return {"ok": False, "error": "signature", "message": "This file failed the signature check."}
        if op == "verify":
            return {"ok": True, "header": h}
        level, cl = int(h["level"]), clearance(user)
        how = "clearance" if level <= cl else ("grant" if grant_ok(msg.get("grant") or {}, user, blob, level) else None)
        fh = hashlib.sha256(blob).hexdigest()
        if not how:
            log(event="unseal-refused", user=user, level=level, clearance=cl, name=h.get("name"), sha256=fh[:16])
            return {"ok": False, "error": "level", "message": f"This file is L{level}; your clearance is L{cl}."}
        data = unseal(h, hb, ct)
        log(event="unseal", user=user, level=level, by=how, name=h.get("name"), sha256=fh[:16])
        return {"ok": True, "header": h, "data": base64.b64encode(data).decode()}
    if op == "clip-put":       # copy inside sealed L3+ windows: held here in RAM, never on the X11 clipboard
        level = int(msg.get("level", 0))
        text = str(msg.get("text", ""))
        if level not in LABEL or len(text) > CLIP_MAX:
            return {"ok": False, "error": "bad clip"}
        with CLIP_LOCK:
            CLIPS[uid] = {"level": level, "text": text, "t": time.time()}
        log(event="clip-put", user=user, level=level, chars=len(text))
        return {"ok": True}
    if op == "clip-get":       # paste: only into a window of the same level or higher, for a while
        level = int(msg.get("level", 0))
        with CLIP_LOCK:
            c = CLIPS.get(uid)
            if c and time.time() - c["t"] > CLIP_TTL:
                CLIPS.pop(uid, None)
                c = None
        if not c or c["level"] > level:
            return {"ok": True, "text": None}
        return {"ok": True, "text": c["text"], "level": c["level"], "t": c["t"]}
    return {"ok": False, "error": "unknown op"}


CLIPS, CLIP_LOCK = {}, threading.Lock()
CLIP_MAX = 2_000_000
CLIP_TTL = 30 * 60


def client(c):
    try:
        cred = c.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", cred)
        c.settimeout(30)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = c.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX * 4 // 3 + 4096:
                raise ValueError("too large")
        out = handle(json.loads(buf or b"{}"), uid)
    except Exception as e:
        out = {"ok": False, "error": "bad request"}
    try:
        c.sendall((json.dumps(out) + "\n").encode())
    except OSError:
        pass
    c.close()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--clearance":
        return set_clearance(sys.argv[2], sys.argv[3])
    ensure_keys()
    os.makedirs(os.path.dirname(SOCK), exist_ok=True)
    try:
        os.unlink(SOCK)
    except OSError:
        pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o666)                 # anyone may ask; the answer depends on who asks (SO_PEERCRED)
    s.listen(16)
    log(event="keyd-start", keys=str(KEYS))
    while True:
        c, _ = s.accept()
        threading.Thread(target=client, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()

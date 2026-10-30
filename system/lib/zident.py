"""The key a PC identifies itself with (audit batches, key service requests), and checking such signatures.

Two kinds:
  - "file": an Ed25519 key in a root-only file (/etc/zenos/audit-device.key). Whoever takes root can copy it and
    act as the PC from anywhere.
  - "tpm": an ECDSA P-256 key made inside the PC's TPM and never leaving it (fixedTPM), usable only while the
    selected PCRs hold the values they had when it was made (for PCR 7: the same Secure Boot state). Root on the
    running PC can still ask the TPM to sign, but cannot take the key to another machine, and a PC started with
    another boot chain cannot use it at all.

/etc/zenos/identity.json: {"kind": "tpm", "handle": "0x81010042", "pcrs": "7"}   (absent: "file")
  zident.py --setup-tpm [--pcrs 7] [--handle 0x81010042]   make the TPM key and switch to it (root)
  zident.py --show                                         the public key to enroll (audit node, key service)
  zident.py --ensure                                       first start: make one (TPM if present, else the file)
"""
import base64, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

CONF = Path(os.environ.get("ZENOS_IDENTITY_CONF", "/etc/zenos/identity.json"))
FILE_KEY = Path(os.environ.get("ZENOS_AUDIT_KEY", "/etc/zenos/audit-device.key"))
DEFAULT_HANDLE = "0x81010042"


class Unavailable(Exception):
    pass


def verify(pub, sig, msg):
    """pub: 32 raw bytes (Ed25519) or a DER SubjectPublicKeyInfo (P-256). True only for a good signature."""
    try:
        if len(pub) == 32:
            Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
            return True
        k = serialization.load_der_public_key(pub)
        if not isinstance(k, ec.EllipticCurvePublicKey) or not isinstance(k.curve, ec.SECP256R1):
            return False
        k.verify(sig, msg, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def check_pub(raw):
    """raises ValueError unless `raw` is a public key a PC may identify itself with"""
    if len(raw) == 32:
        Ed25519PublicKey.from_public_bytes(raw)
        return
    k = serialization.load_der_public_key(raw)
    if not isinstance(k, ec.EllipticCurvePublicKey) or not isinstance(k.curve, ec.SECP256R1):
        raise ValueError("a PC key is Ed25519 or P-256")


class FileIdentity:
    kind = "file"

    def __init__(self, path=None):
        self.path = Path(path or FILE_KEY)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(Ed25519PrivateKey.generate().private_bytes(
                    serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
        self.k = Ed25519PrivateKey.from_private_bytes(self.path.read_bytes())

    def sign(self, msg):
        return self.k.sign(msg)

    def pub(self):
        return self.k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def public_key(self):
        return self.k.public_key()


def _tpm(*args, cwd=None):
    r = subprocess.run(list(args), capture_output=True, timeout=30, cwd=cwd)
    if r.returncode != 0:
        raise Unavailable("%s: %s" % (args[0], r.stderr.decode(errors="replace").strip()[-200:]))
    return r.stdout


def _flush():
    subprocess.run(["tpm2_flushcontext", "-t"], capture_output=True, timeout=30)   # no resource manager (swtpm)


class TpmIdentity:
    kind = "tpm"

    def __init__(self, handle=DEFAULT_HANDLE, pcrs="7"):
        if not shutil.which("tpm2_sign"):
            raise Unavailable("tpm2-tools is not installed")
        self.handle, self.pcrs = handle, str(pcrs or "")
        self._pub = None

    def sign(self, msg):
        with tempfile.TemporaryDirectory(prefix="zenos-tpm-") as d:
            Path(d, "m").write_bytes(msg)
            auth = []
            try:
                if self.pcrs:
                    _tpm("tpm2_startauthsession", "--policy-session", "-S", "s.ctx", cwd=d)
                    _tpm("tpm2_policypcr", "-S", "s.ctx", "-l", "sha256:" + self.pcrs, "-Q", cwd=d)
                    auth = ["-p", "session:s.ctx"]
                _tpm("tpm2_sign", "-c", self.handle, *auth, "-g", "sha256", "-s", "ecdsa", "-f", "plain", "-o", "sig", "m",
                     cwd=d)
                return Path(d, "sig").read_bytes()
            finally:
                if self.pcrs and Path(d, "s.ctx").exists():
                    subprocess.run(["tpm2_flushcontext", "s.ctx"], capture_output=True, cwd=d, timeout=30)
                _flush()

    def pub(self):
        if self._pub is None:
            with tempfile.TemporaryDirectory(prefix="zenos-tpm-") as d:
                _tpm("tpm2_readpublic", "-c", self.handle, "-f", "der", "-o", "pub.der", "-Q", cwd=d)
                self._pub = Path(d, "pub.der").read_bytes()
                _flush()
        return self._pub


TpmIdentity.public_key = lambda self: serialization.load_der_public_key(self.pub())


def load():
    """the identity this PC uses now. A TPM identity that is configured but cannot be used is an error, never a
    reason to fall back to the file key."""
    try:
        c = json.loads(CONF.read_text())
    except FileNotFoundError:
        return FileIdentity()
    except (OSError, ValueError) as e:
        raise Unavailable("the identity configuration is not usable: %s" % e)
    if c.get("kind") == "tpm":
        return TpmIdentity(c.get("handle", DEFAULT_HANDLE), c.get("pcrs", "7"))
    if c.get("kind") in (None, "file"):
        return FileIdentity(c.get("path"))
    raise Unavailable("unknown identity kind %r" % c.get("kind"))


def setup_tpm(handle=DEFAULT_HANDLE, pcrs="7"):
    """make a P-256 signing key inside the TPM (it never leaves it), bound to the PCRs, keep it at `handle`,
    and switch this PC to it. The audit nodes and the key service must enroll the new public key."""
    with tempfile.TemporaryDirectory(prefix="zenos-tpm-") as d:
        _flush()
        _tpm("tpm2_createprimary", "-C", "o", "-g", "sha256", "-G", "ecc", "-c", "p.ctx", "-Q", cwd=d)
        attrs = "fixedtpm|fixedparent|sensitivedataorigin|sign"
        pol = []
        if pcrs:
            _tpm("tpm2_createpolicy", "--policy-pcr", "-l", "sha256:" + str(pcrs), "-L", "pol.dat", "-Q", cwd=d)
            pol, attrs = ["-L", "pol.dat"], attrs + "|adminwithpolicy"
        else:
            attrs += "|userwithauth"
        _tpm("tpm2_create", "-C", "p.ctx", "-G", "ecc256:ecdsa-sha256", *pol, "-a", attrs, "-u", "k.pub", "-r", "k.priv",
             "-Q", cwd=d)
        _flush()
        _tpm("tpm2_load", "-C", "p.ctx", "-u", "k.pub", "-r", "k.priv", "-c", "k.ctx", "-Q", cwd=d)
        subprocess.run(["tpm2_evictcontrol", "-C", "o", "-c", handle], capture_output=True, cwd=d, timeout=30)  # an old one
        _tpm("tpm2_evictcontrol", "-C", "o", "-c", "k.ctx", handle, "-Q", cwd=d)
        _flush()
    t = TpmIdentity(handle, pcrs)
    probe = os.urandom(32)
    if not verify(t.pub(), t.sign(probe), probe):
        raise Unavailable("the TPM key does not sign correctly")
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_name(CONF.name + ".tmp")
    tmp.write_text(json.dumps({"kind": "tpm", "handle": handle, "pcrs": str(pcrs or "")}) + "\n")
    os.replace(tmp, CONF)
    return t


def main():
    a = sys.argv[1:]
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    if "--setup-tpm" in a:
        t = setup_tpm(opt("--handle", DEFAULT_HANDLE), opt("--pcrs", "7"))
        print("This PC now identifies itself with a key inside its TPM. Enroll it again on the audit nodes and the key service:")
        print(base64.b64encode(t.pub()).decode())
        return
    if "--ensure" in a:            # first start (zenos-identity.service): the TPM when there is one, else the file
        if CONF.exists() or FILE_KEY.exists():
            return
        if os.path.exists("/dev/tpmrm0") and shutil.which("tpm2_sign"):
            try:
                setup_tpm(opt("--handle", DEFAULT_HANDLE), opt("--pcrs", "7"))
                return print("identity: a key inside the TPM")
            except Unavailable as e:
                print("identity: the TPM could not be used (%s); using a key file" % e)
        FileIdentity()
        return print("identity: a key file")
    if "--show" in a:
        i = load()
        print(i.kind, base64.b64encode(i.pub()).decode())
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()

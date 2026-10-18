#!/usr/bin/env python3
"""ZENOS per-fragment encryption (PoC).

A file is split into N fragments. Each fragment gets ITS OWN random 256-bit key.
The ciphertext fragments + manifest can live on the machine; the per-fragment keys do NOT.
They are issued one at a time from a separate key store (stand-in for device-held / off-machine
issuance). Consequences this demonstrates:
  - Whole ciphertext stolen, no keys  -> nothing opens.
  - One fragment + its one key leaked  -> only that fragment's bytes, never the rest.
  - Any fragment tampered             -> AES-GCM auth fails (integrity).
  - Fragment reordered/swapped         -> AAD binds (file_id, index, level), so it fails.
"""
import base64, hashlib, json, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FRAG = 64 * 1024  # fragment size in bytes


def _b(x):
    return base64.b64encode(x).decode()


def _ub(s):
    return base64.b64decode(s)


def seal(data: bytes, level: int, name: str, keystore: str):
    """Split, encrypt each fragment under its own key. Returns the .zenf blob; writes keys to keystore."""
    os.makedirs(keystore, exist_ok=True)
    os.chmod(keystore, 0o700)
    file_id = _b(os.urandom(12))
    frags, manifest = [], []
    n = max(1, (len(data) + FRAG - 1) // FRAG)
    for i in range(n):
        chunk = data[i * FRAG:(i + 1) * FRAG]
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        aad = json.dumps({"file_id": file_id, "index": i, "level": level}, sort_keys=True).encode()
        ct = AESGCM(key).encrypt(nonce, chunk, aad)
        key_id = hashlib.sha256((file_id + ":" + str(i)).encode()).hexdigest()[:16]
        kp = os.path.join(keystore, key_id + ".key")        # off-data key store, created owner-only
        fd = os.open(kp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        os.chmod(kp, 0o600)
        frags.append(ct)
        manifest.append({"index": i, "key_id": key_id, "nonce": _b(nonce),
                         "len": len(chunk), "ct_sha256": hashlib.sha256(ct).hexdigest()})
    head = {"zenf": 1, "name": name, "level": level, "file_id": file_id,
            "frag_size": FRAG, "count": n, "manifest": manifest}
    blob = {"header": head, "fragments": [_b(c) for c in frags]}
    return json.dumps(blob).encode()


def _open_fragment(head, ct_b64, m, keystore):
    key_path = os.path.join(keystore, m["key_id"] + ".key")
    if not os.path.exists(key_path):
        raise KeyError("no key issued for fragment %d" % m["index"])
    with open(key_path, "rb") as f:
        key = f.read()
    aad = json.dumps({"file_id": head["file_id"], "index": m["index"], "level": head["level"]},
                     sort_keys=True).encode()
    return AESGCM(key).decrypt(_ub(m["nonce"]), _ub(ct_b64), aad)


def open_full(blob: bytes, keystore: str) -> bytes:
    """Reassemble the whole file. Needs EVERY fragment key."""
    b = json.loads(blob)
    head = b["header"]
    out = b""
    for m in head["manifest"]:
        out += _open_fragment(head, b["fragments"][m["index"]], m, keystore)
    return out


def open_one(blob: bytes, index: int, keystore: str) -> bytes:
    """Open a single fragment only (what a one-key leak yields)."""
    b = json.loads(blob)
    head = b["header"]
    m = head["manifest"][index]
    return _open_fragment(head, b["fragments"][index], m, keystore)

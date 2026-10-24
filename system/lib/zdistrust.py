"""Certificate keys ZENOS refuses, whatever root vouches for them.

When a certificate authority's private key is stolen, removing its root from the trust store is not enough: the same
key may also be cross-signed by another, still-trusted root. ZENOS therefore keeps its own list of compromised keys
(distrust.json, matched on the SHA-256 of the public key) and its TLS clients refuse any chain that contains one.

  zdistrust.blocked(der_certificates) -> name of the compromised key, or None
"""
import hashlib, json, os

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIST = os.environ.get("ZENOS_DISTRUST", os.path.join(_HERE, "distrust.json"))
_BAD = None


def _load():
    global _BAD
    if _BAD is None:
        _BAD = {}
        try:
            for e in json.load(open(_LIST)).get("entries", []):
                for k in e.get("keys", []):
                    _BAD[k["spki_sha256"].upper()] = f'{k.get("name", "?")} ({e.get("incident", "")})'
        except (OSError, ValueError):
            pass
    return _BAD


def spki_sha256(der):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    pub = x509.load_der_x509_certificate(der).public_key()
    return hashlib.sha256(pub.public_bytes(serialization.Encoding.DER,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest().upper()


def blocked(ders):
    bad = _load()
    for der in ders:
        try:
            h = spki_sha256(bytes(der))
        except Exception:
            continue
        if h in bad:
            return bad[h]
    return None


def blocked_gio(cert):
    """the same check for a Gio.TlsCertificate chain (WebKit's get_tls_info)"""
    ders, seen = [], 0
    while cert is not None and seen < 10:
        ba = cert.get_property("certificate")
        if ba is not None:
            ders.append(bytes(ba.data if hasattr(ba, "data") else ba))
        cert, seen = cert.get_issuer(), seen + 1
    return blocked(ders)

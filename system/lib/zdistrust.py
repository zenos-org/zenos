"""Certificates and keys ZENOS refuses, whatever root vouches for them.

When a certificate authority's private key is stolen, removing its root from the trust store is not enough: the same
key may also be cross-signed by another, still-trusted root, and OpenSSL/GnuTLS do not check revocation by default.
ZENOS therefore keeps its own refusal list and its TLS clients refuse any chain that contains an entry:
  distrust.json                         shipped with ZENOS (keys matched on the SHA-256 of the public key)
  /var/lib/zenos/distrust.learned.json  kept current by the trust agent (zenos_trustwatch) from Mozilla's
                                        signed OneCRL list: keys (SPKI SHA-256) and certificates (issuer + serial)

  zdistrust.blocked(der_certificates) -> why the chain is refused, or None
"""
import base64, hashlib, json, os

_HERE = os.path.dirname(os.path.abspath(__file__))
LISTS = [os.environ.get("ZENOS_DISTRUST") or os.path.join(_HERE, "distrust.json"),
         os.environ.get("ZENOS_DISTRUST_LEARNED") or "/var/lib/zenos/distrust.learned.json"]
_cache = {"stamp": None, "spki": {}, "isn": {}}


def _stamp():
    out = []
    for p in LISTS:
        try:
            out.append(os.stat(p).st_mtime_ns)
        except OSError:
            out.append(None)
    return out


def tables():
    """(spki_hex -> why, 'issuerB64:serialB64' -> why), reloaded when a list file changes"""
    st = _stamp()
    if st != _cache["stamp"]:
        spki, isn = {}, {}
        for p in LISTS:
            try:
                with open(p) as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            for e in d.get("entries", []):
                for k in e.get("keys", []):
                    spki[k["spki_sha256"].upper()] = "%s (%s)" % (k.get("name", "?"), e.get("incident", ""))
            for h, why in d.get("spki", {}).items():
                spki.setdefault(h.upper(), why)
            isn.update(d.get("issuer_serial", {}))
        _cache.update(stamp=st, spki=spki, isn=isn)
    return _cache["spki"], _cache["isn"]


def _tlv(b, i):
    """(tag, content_start, end) of the DER element at b[i]"""
    tag, n = b[i], b[i + 1]
    j = i + 2
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(b[j:j + k], "big")
        j += k
    return tag, j, j + n


def issuer_serial(der):
    """the OneCRL key of a certificate: base64(issuer Name DER) + ':' + base64(serial INTEGER content)"""
    _, c, _ = _tlv(der, 0)               # Certificate
    _, i, _ = _tlv(der, c)               # tbsCertificate
    tag, s, e = _tlv(der, i)
    if tag == 0xA0:                      # [0] version
        tag, s, e = _tlv(der, e)
    serial = der[s:e]
    _, s2, e2 = _tlv(der, e)             # signature algorithm
    _, s3, e3 = _tlv(der, e2)            # issuer Name
    return base64.b64encode(der[e2:e3]).decode() + ":" + base64.b64encode(serial).decode()


def spki_sha256(der):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    pub = x509.load_der_x509_certificate(der).public_key()
    return hashlib.sha256(pub.public_bytes(serialization.Encoding.DER,
                                           serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest().upper()


def why(der):
    spki, isn = tables()
    der = bytes(der)
    try:
        w = spki.get(spki_sha256(der))
        if w:
            return w
    except Exception:
        pass
    try:
        return isn.get(issuer_serial(der))
    except Exception:
        return None


def blocked(ders):
    for der in ders:
        w = why(der)
        if w:
            return w
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

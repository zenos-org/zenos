// Refuse TLS chains that contain a certificate or key ZENOS distrusts (see zdistrust.py for the lists), even when
// a root Node still trusts vouches for it. Node bundles its own root list, so fixing the OS trust store does not
// cover it. ZENOS loads this into every Node program (NODE_OPTIONS=--require=/usr/lib/zenos/zdistrust.js).
"use strict";
const KEY = Symbol.for("zenos.distrust");
if (!global[KEY]) {
  const tls = require("tls");
  const fs = require("fs");
  const path = require("path");
  const crypto = require("crypto");
  const LISTS = [process.env.ZENOS_DISTRUST || path.join(__dirname, "distrust.json"),
    process.env.ZENOS_DISTRUST_LEARNED || "/var/lib/zenos/distrust.learned.json"];
  let stamp = null, SPKI = new Map(), ISN = new Map();

  const tables = () => {
    const st = LISTS.map((p) => { try { return fs.statSync(p).mtimeMs; } catch (_) { return null; } }).join();
    if (st !== stamp) {
      const s = new Map(), n = new Map();
      for (const p of LISTS) {
        let d;
        try { d = JSON.parse(fs.readFileSync(p, "utf8")); } catch (_) { continue; }
        for (const e of d.entries || []) for (const k of e.keys || []) s.set(k.spki_sha256.toUpperCase(), `${k.name} (${e.incident})`);
        for (const [h, w] of Object.entries(d.spki || {})) if (!s.has(h.toUpperCase())) s.set(h.toUpperCase(), w);
        for (const [k, w] of Object.entries(d.issuer_serial || {})) n.set(k, w);
      }
      stamp = st; SPKI = s; ISN = n;
    }
    return [SPKI, ISN];
  };

  const tlv = (b, i) => {
    let n = b[i + 1], j = i + 2;
    if (n & 0x80) { const k = n & 0x7f; n = 0; for (let q = 0; q < k; q++) n = n * 256 + b[j + q]; j += k; }
    return [b[i], j, j + n];
  };
  // OneCRL key: base64(issuer Name DER) + ':' + base64(serial INTEGER content)
  const issuerSerial = (der) => {
    const [, c] = tlv(der, 0);
    const [, i] = tlv(der, c);
    let [tag, s, e] = tlv(der, i);
    if (tag === 0xa0) [tag, s, e] = tlv(der, e);
    const serial = der.subarray(s, e);
    const [, , e2] = tlv(der, e);
    const [, , e3] = tlv(der, e2);
    return der.subarray(e2, e3).toString("base64") + ":" + serial.toString("base64");
  };
  // SPKI from the certificate itself: Node's cert.pubkey is SPKI only for RSA (for EC keys it is the bare point)
  const spki = (cert) => {
    const der = new crypto.X509Certificate(cert.raw).publicKey.export({ type: "spki", format: "der" });
    return crypto.createHash("sha256").update(der).digest("hex").toUpperCase();
  };
  const blocked = (cert) => {
    const [s, n] = tables();
    const seen = new Set();
    for (let c = cert; c && c.raw && !seen.has(c); c = c.issuerCertificate) {
      seen.add(c);
      let w = null;
      try { w = s.get(spki(c)); } catch (_) {}
      if (!w) try { w = n.get(issuerSerial(c.raw)); } catch (_) {}
      if (w) return w;
    }
    return null;
  };

  const orig = tls.checkServerIdentity;
  tls.checkServerIdentity = function (host, cert) {
    const w = blocked(cert);
    if (w) {
      const err = new Error(`ZENOS: certificate for ${host} chains to a distrusted CA: ${w}`);
      err.code = "ZENOS_DISTRUSTED_CA";
      return err;
    }
    return orig(host, cert);
  };
  global[KEY] = { blocked, spki, issuerSerial, size: () => tables()[0].size + tables()[1].size };
}
module.exports = global[KEY];

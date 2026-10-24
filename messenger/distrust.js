// Refuse TLS chains that contain a compromised CA key (system/lib/distrust.json), even when a root Node still
// trusts has cross-signed that key. Node bundles its own root store, so the OS trust store fix does not cover it.
"use strict";
const tls = require("tls");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const LIST = process.env.ZENOS_DISTRUST || [path.join(__dirname, "../system/lib/distrust.json"), "/usr/lib/zenos/distrust.json"]
  .find((p) => fs.existsSync(p));
const BAD = new Map();
try {
  for (const e of JSON.parse(fs.readFileSync(LIST, "utf8")).entries || [])
    for (const k of e.keys || []) BAD.set(k.spki_sha256.toUpperCase(), `${k.name} (${e.incident})`);
} catch (_) {}

// SPKI from the certificate itself: Node's cert.pubkey is SPKI only for RSA (for EC keys it is the bare point)
function spki(cert) {
  const der = new crypto.X509Certificate(cert.raw).publicKey.export({ type: "spki", format: "der" });
  return crypto.createHash("sha256").update(der).digest("hex").toUpperCase();
}

function blocked(cert) {
  const seen = new Set();
  for (let c = cert; c && c.raw && !seen.has(c); c = c.issuerCertificate) {
    seen.add(c);
    const n = BAD.get(spki(c));
    if (n) return n;
  }
  return null;
}

const orig = tls.checkServerIdentity;
tls.checkServerIdentity = function (host, cert) {
  const n = blocked(cert);
  if (n) {
    const err = new Error(`ZENOS: certificate for ${host} chains to a compromised CA key: ${n}`);
    err.code = "ZENOS_DISTRUSTED_CA";
    return err;
  }
  return orig(host, cert);
};

module.exports = { blocked, spki, size: BAD.size };

// Node side: every compromised certificate is refused, ordinary chains are not.
"use strict";
const D = require("../messenger/distrust");
const fs = require("fs"), path = require("path"), crypto = require("crypto"), assert = require("assert");
const pems = fs.readFileSync(path.join(__dirname, "fixtures/emudhra-compromised.pem"), "utf8")
  .split("-----END CERTIFICATE-----").filter((p) => p.includes("BEGIN")).map((p) => p.trim() + "\n-----END CERTIFICATE-----\n");
assert.strictEqual(pems.length, 16);
for (const p of pems) {
  const x = new crypto.X509Certificate(p);
  assert.ok(/eMudhra/.test(D.blocked({ raw: x.raw }) || ""), x.subject);
}
const ok = new crypto.X509Certificate(require("tls").rootCertificates[0]);
assert.strictEqual(D.blocked({ raw: ok.raw }), null);
console.log("distrust ok:", D.size, "keys,", pems.length, "certificates refused");

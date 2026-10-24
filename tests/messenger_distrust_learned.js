// learned OneCRL entries (issuer + serial) are enforced, and picked up without a restart
"use strict";
const fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto"), assert = require("assert");
const tmp = path.join(os.tmpdir(), "zenos-learned-" + process.pid + ".json");
process.env.ZENOS_DISTRUST_LEARNED = tmp;
const D = require("../system/lib/zdistrust");
const x = new crypto.X509Certificate(require("tls").rootCertificates[3]);
assert.strictEqual(D.blocked({ raw: x.raw }), null);
fs.writeFileSync(tmp, JSON.stringify({ issuer_serial: { [D.issuerSerial(x.raw)]: "test entry" } }));
assert.strictEqual(D.blocked({ raw: x.raw }), "test entry");
fs.unlinkSync(tmp);
console.log("learned ok");

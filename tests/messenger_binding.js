// Messenger device binding: the first key registered for an account wins; a new device takes the account over only
// by verifying the number already registered to it; unsigned, foreign-key and replayed requests are refused.
//   node tests/messenger_binding.js      (needs messenger/node_modules: cd messenger && npm ci)
const path = require("path"), os = require("os"), { spawn } = require("child_process");
const MSG = path.join(__dirname, "..", "messenger");
const S = (() => { try { return require(require.resolve("@signalapp/libsignal-client", { paths: [MSG] })); } catch { return require("@signalapp/libsignal-client"); } })();
const crypto = require("crypto"), fs = require("fs");
const HOME = fs.mkdtempSync(path.join(os.tmpdir(), "zbind-")), PORT = 18300 + Math.floor(Math.random() * 500);
const R = `http://127.0.0.1:${PORT}`, OUT = path.join(HOME, ".local/share/zenos/msg/relay/sms-outbox.log");
const relay = spawn(process.execPath, [path.join(MSG, "relay.js")], { env: { ...process.env, HOME, ZENOS_RELAY_PORT: String(PORT) }, stdio: "ignore" });
const ready = async () => { for (let i = 0; i < 50; i++) { try { await fetch(R + "/trust"); return; } catch { await new Promise((r) => setTimeout(r, 100)); } } throw new Error("relay did not start"); };
const finish = (code) => { relay.kill(); fs.rmSync(HOME, { recursive: true, force: true }); process.exit(code); };
const sha = (x) => crypto.createHash("sha256").update(String(x)).digest("hex");
const b64 = (u) => Buffer.from(u).toString("base64");
async function rq(key, acc, method, p, obj) {
  const raw = obj ? JSON.stringify(obj) : ""; const h = { "Content-Type": "application/json" };
  if (key) { const ts = String(Date.now()); h["X-Zenos-Auth"] = `${acc} ${ts} ${b64(key.privateKey.sign(Buffer.from(`${method} ${p} ${ts} ${sha(raw)}`)))}`; }
  const r = await fetch(R + p, { method, headers: h, body: raw || undefined }); return [r.status, await r.json()];
}
const lastCode = () => fs.readFileSync(OUT, "utf8").trim().split("\n").pop().match(/code: (\d{6})/)[1];
let fail = 0; const check = (name, cond, got) => { console.log((cond ? "ok   " : "FAIL ") + name, cond ? "" : JSON.stringify(got)); if (!cond) fail++; };
(async () => {
  await ready();
  const A = S.IdentityKeyPair.generate(), B = S.IdentityKeyPair.generate(), acc = "acme", phone = "+15555550142";
  const bundle = (k, name) => ({ name, identity: b64(k.publicKey.serialize()) });
  let r = await rq(null, acc, "POST", `/keys/${acc}`, bundle(A, "Acme A")); check("first device registers", r[0] === 200, r);
  r = await rq(null, acc, "POST", `/keys/${acc}`, bundle(B, "evil")); check("second key refused", r[0] === 409, r);
  r = await rq(A, acc, "POST", "/register/start", { phone, id: acc }); check("device A starts number", r[0] === 200, r);
  r = await rq(A, acc, "POST", "/register/verify", { phone, id: acc, code: lastCode() }); check("device A verifies number", r[1].ok && !r[1].rebind, r);
  r = await rq(null, acc, "POST", "/register/start", { phone: "+15555550199", id: acc }); check("other number refused for unsigned", r[0] === 403, r);
  r = await rq(B, acc, "POST", "/register/start", { phone, id: acc }); check("new device: code to the account's number", r[0] === 200, r);
  r = await rq(B, acc, "POST", "/register/verify", { phone, id: acc, code: lastCode() }); check("new device verified -> rebind", r[1].ok && r[1].rebind, r);
  r = await rq(B, acc, "POST", `/keys/${acc}`, bundle(B, "Acme B")); check("new device publishes its key", r[0] === 200, r);
  r = await rq(A, acc, "GET", `/phone/${acc}`); check("old device now refused", r[0] === 403, r);
  r = await rq(B, acc, "GET", `/phone/${acc}`); check("new device accepted", r[0] === 200 && r[1].phone === phone, r);
  const ts = String(Date.now()), sig = b64(B.privateKey.sign(Buffer.from(`GET /phone/${acc} ${ts} ${sha("")}`)));
  const once = async () => (await fetch(R + `/phone/${acc}`, { headers: { "X-Zenos-Auth": `${acc} ${ts} ${sig}` } })).status;
  const s1 = await once(), s2 = await once(); check("replayed request refused", s1 === 200 && s2 === 403, [s1, s2]);
  r = await rq(null, acc, "POST", `/keys/${acc}`, bundle(A, "back")); check("old key cannot come back", r[0] === 409, r);
  console.log(fail ? `${fail} FAILED` : "ALL OK"); finish(fail ? 1 : 0);
})().catch((e) => { console.error(e); finish(2); });

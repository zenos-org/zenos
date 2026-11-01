// Two ZENOS Messages clients at two organizations (client.js, unchanged UI): a message to "account@organization"
// goes through both relays and comes back as a reply, end to end (Signal protocol, sealed sender).
//   node tests/messenger_federation_clients.js   (needs messenger/node_modules and zenos-decide built)
const path = require("path"), os = require("os"), fs = require("fs"), crypto = require("crypto"), { spawn } = require("child_process");
const MSG = path.join(__dirname, "..", "messenger");
const F = require(path.join(MSG, "federation.js"));
const b64 = (u) => Buffer.from(u).toString("base64");
const ADMIN = crypto.randomBytes(12).toString("hex"), base = 19400 + Math.floor(Math.random() * 300);
const procs = [], homes = [];
const home = () => { const h = fs.mkdtempSync(path.join(os.tmpdir(), "zfedc-")); homes.push(h); return h; };
const run = (args, env) => { const p = spawn(process.execPath, args, { env: { ...process.env, ...env }, stdio: "ignore" }); procs.push(p); return p; };
const finish = (code) => { for (const p of procs) p.kill(); for (const h of homes) fs.rmSync(h, { recursive: true, force: true }); process.exit(code); };
let fail = 0; const check = (n, c, g) => { console.log((c ? "ok   " : "FAIL ") + n, c ? "" : JSON.stringify(g)); if (!c) fail++; };
const j = async (url, method = "GET", obj, h = {}) => { const r = await fetch(url, { method, headers: { "Content-Type": "application/json", ...h }, body: obj ? JSON.stringify(obj) : undefined }); return r.json(); };
const wait = async (f, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await f(); if (v) return v; } catch {} await new Promise((z) => setTimeout(z, 250)); } return null; };
(async () => {
  const A = { url: `http://127.0.0.1:${base}`, HOME: home() }, B = { url: `http://127.0.0.1:${base + 1}`, HOME: home() };
  run([path.join(MSG, "relay.js")], { HOME: A.HOME, ZENOS_RELAY_PORT: String(base), ZENOS_RELAY_ADMIN: ADMIN });
  run([path.join(MSG, "relay.js")], { HOME: B.HOME, ZENOS_RELAY_PORT: String(base + 1), ZENOS_RELAY_ADMIN: ADMIN });
  for (const r of [A, B]) r.key = (await wait(() => j(r.url + "/.well-known/zenos-relay"))).key;
  const au = { ministry: crypto.generateKeyPairSync("ed25519"), prefecture: crypto.generateKeyPairSync("ed25519") };
  const raw = (kp) => b64(kp.publicKey.export({ format: "der", type: "spki" }).subarray(12));
  const entry = (org, url, key, max_level) => { const e = { org, url, key, max_level, publish_only: false };
    e.sigs = Object.keys(au).map((w) => ({ by: w, sig: b64(crypto.sign(null, Buffer.from(F.entryText(e)), au[w].privateKey)) })); return e; };
  const members = { k: 2, authorities: Object.keys(au).map((id) => ({ id, key: raw(au[id]) })),
    entries: [entry("ministry.example", A.url, A.key, 5), entry("city.example", B.url, B.key, 3)] };
  await j(A.url + "/fed/config", "POST", { org: "ministry.example", url: A.url, members }, { "X-Zenos-Admin": ADMIN });
  await j(B.url + "/fed/config", "POST", { org: "city.example", url: B.url, members }, { "X-Zenos-Admin": ADMIN });
  const za = `http://127.0.0.1:${base + 10}`, zb = `http://127.0.0.1:${base + 20}`;
  run([path.join(MSG, "client.js"), "zenos", String(base + 10)], { HOME: home(), ZENOS_RELAY: A.url });
  run([path.join(MSG, "client.js"), "sato", String(base + 20)], { HOME: home(), ZENOS_RELAY: B.url });
  check("both clients start on their own organization's relay", !!(await wait(() => j(za + "/api/me"))) && !!(await wait(() => j(zb + "/api/me"))));
  await new Promise((z) => setTimeout(z, 1500));
  let r = await j(za + "/api/send", "POST", { to: "sato@city.example", text: "Please confirm the shelter list.", level: 2 });
  check("zenos at the ministry sends to sato@city.example", r.ok, r);
  const got = await wait(async () => (await j(zb + "/api/all")).find((m) => m.dir === "in" && m.from === "zenos@ministry.example"));
  check("sato reads it, from zenos@ministry.example", got && got.text === "Please confirm the shelter list.", got);
  r = await j(zb + "/api/send", "POST", { to: "zenos@ministry.example", text: "Confirmed, 3 shelters open.", level: 2 });
  check("sato replies", r.ok, r);
  const back = await wait(async () => (await j(za + "/api/all")).find((m) => m.dir === "in" && m.from === "sato@city.example"));
  check("zenos reads the reply, from sato@city.example", back && back.text === "Confirmed, 3 shelters open.", back);
  r = await j(za + "/api/send", "POST", { to: "sato@city.example", text: "x", level: 4 });
  check("L4 to the city (listed up to L3) refused", !!r.error && /level/.test(r.error), r);
  r = await j(za + "/api/send", "POST", { to: "someone@unlisted.example", text: "x", level: 1 });
  check("an unlisted organization is refused", !!r.error && /unlisted/.test(r.error), r);
  finish(fail ? 1 : 0);
})().catch((e) => { console.error(e); finish(1); });

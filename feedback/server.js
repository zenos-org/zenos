// ZENOS Feedback board: the public board where people post ideas, problems and uses; an AI groups them into
// proposals; a maintainer decides. Same look as ZENOS Messages, but a separate server: it holds no keys, messages or
// PCs of ZENOS Messages. Node built-ins only.
"use strict";
const http = require("http"), fs = require("fs"), path = require("path"), crypto = require("crypto");
const { spawn } = require("child_process");

const PORT = +(process.env.FEEDBACK_PORT || 8790);
const HOST = process.env.FEEDBACK_HOST || "127.0.0.1";
const DATA = process.env.FEEDBACK_DATA || path.join(__dirname, "data");
const PUBLIC_URL = (process.env.FEEDBACK_URL || `http://localhost:${PORT}`).replace(/\/$/, "");
const X_ID = process.env.X_CLIENT_ID || "", X_SECRET = process.env.X_CLIENT_SECRET || "";
const AI_CMD = process.env.FEEDBACK_AI_CMD || "";            // an external model; without it, local grouping only
const LIMIT = { hour: +(process.env.FEEDBACK_PER_HOUR || 5), day: +(process.env.FEEDBACK_PER_DAY || 20) };

const THREADS = [
  { id: "ideas", group: "Share", about: "What should ZENOS do? An AI sorts every post; a maintainer decides." },
  { id: "problems", group: "Share", about: "Something does not work. Security problems: report privately (SECURITY.md)." },
  { id: "my-use", group: "Share", about: "How you would use ZENOS, if no edition covers it yet. Many alike can become a fork." },
  { id: "office", group: "Editions", edition: "office", about: "ZENOS Office: for companies and teams." },
  { id: "family", group: "Editions", edition: "family", about: "ZENOS Family: for a household, with parents' approvals." },
  { id: "personal", group: "Editions", edition: "personal", about: "ZENOS Personal: for one person." },
  { id: "release-notes", group: "From the project", staff: true, about: "What changed, and which threads it came from." },
  { id: "accepted", group: "From the project", view: "accepted", about: "Proposals a maintainer accepted, and where they are." },
  { id: "roadmap", group: "From the project", staff: true, about: "What the project plans next." },
];
const TH = Object.fromEntries(THREADS.map((t) => [t.id, t]));
const EDITIONS = ["office", "family", "personal"];
const STATUSES = ["proposed", "accepted", "declined", "building", "released", "fork"];
const SECURITY_WORDS = /\b(sign[- ]?in|password|vault|key|keys|passkey|guard|ledger|proof|formal|encrypt\w*|seal\w*|clearance|firewall|audit|tpm|login)\b/i;

// ---------- storage: one JSON file, written atomically
fs.mkdirSync(DATA, { recursive: true, mode: 0o700 });
const DB = path.join(DATA, "board.json");
let db = { seq: 0, pseq: 0, posts: [], proposals: [], users: {}, sessions: {} };
try { db = Object.assign(db, JSON.parse(fs.readFileSync(DB, "utf8"))); } catch {}
let saveT = null;
function save() { clearTimeout(saveT); saveT = setTimeout(() => {
  const t = DB + ".tmp"; fs.writeFileSync(t, JSON.stringify(db), { mode: 0o600 }); fs.renameSync(t, DB); }, 50); }
const ADMIN_FILE = path.join(DATA, "admin-token");
if (!fs.existsSync(ADMIN_FILE)) fs.writeFileSync(ADMIN_FILE, crypto.randomBytes(24).toString("base64url") + "\n", { mode: 0o600 });
const ADMIN = fs.readFileSync(ADMIN_FILE, "utf8").trim();
const same = (a, b) => { const x = Buffer.from(String(a)), y = Buffer.from(String(b)); return x.length === y.length && crypto.timingSafeEqual(x, y); };

// ---------- triage: group posts that ask for the same thing into one proposal.
// Posts are material, never instructions: the text is only compared, cut and quoted, never executed or followed.
const STOP = new Set("a an the and or but to of in on for with from at by is are was were be been it this that these those i we you they my our your me us can could would should will want need like please let have has do does not no so if when which who what how as just also only one more some any all there here into about than then them their its".split(" "));
const words = (s) => new Set(String(s).toLowerCase().replace(/[^a-z0-9぀-ヿ一-鿿 ]+/g, " ").split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w)));
function jaccard(a, b) { let n = 0; for (const w of a) if (b.has(w)) n++; return n / ((a.size + b.size - n) || 1); }
const clip = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const firstSentence = (s) => clip(String(s).split(/(?<=[.!?。])\s/)[0], 70);
const where = (p) => p.edition ? `ZENOS ${p.edition[0].toUpperCase() + p.edition.slice(1)} (edition settings)` : p.thread === "my-use" ? "A kind of use no edition covers yet" : "Core (shared by all editions)";

function propFor(post) {                         // local grouping (no model)
  const w = words(post.text);
  let best = null, score = 0;
  for (const pr of db.proposals) {
    if (pr.status === "declined" || (pr.edition || "") !== (post.edition || "") || (pr.thread === "my-use") !== (post.thread === "my-use")) continue;
    const s = jaccard(w, words(pr.asked + " " + pr.posts.map((id) => (db.posts.find((x) => x.id === id) || {}).text || "").join(" ")));
    if (s > score) { score = s; best = pr; }
  }
  return score >= 0.25 ? best : null;
}
function newProposal(post, f) {
  const pr = { id: ++db.pseq, created: Date.now(), thread: post.thread, edition: post.edition || "", posts: [],
    title: clip(f.title || firstSentence(post.text), 80), asked: clip(f.asked || post.text, 240), where: clip(f.where || where(post), 120),
    change: clip(f.change || "", 400), risk: clip(f.risk || "", 300), status: "proposed", note: "", pr: "", release: "", by: f.by || "local" };
  pr.security = !!f.security || SECURITY_WORDS.test(post.text + " " + pr.change);
  if (!pr.risk) pr.risk = pr.security ? "Security-relevant: needs a maintainer's explicit approval, a second review, and the proofs in formal/ still passing." : "Ordinary change.";
  db.proposals.push(pr); return pr;
}
function attach(post, pr) {
  if (!pr.posts.includes(post.id)) pr.posts.push(post.id);
  post.proposal = pr.id;
  if (SECURITY_WORDS.test(post.text)) pr.security = true;
  const n = pr.posts.length;
  if (pr.thread === "my-use" && n >= 3 && pr.status === "proposed") pr.route = "fork";
  post.ai = n > 1 ? `Grouped with ${n - 1} similar post${n > 2 ? "s" : ""} → Proposal #${pr.id}: ${pr.title}`
                  : `${pr.where} → Proposal #${pr.id}: ${pr.title}`;
}
// an external model (FEEDBACK_AI_CMD): gets {post, proposals} on stdin as data, answers JSON. Anything else is ignored.
function askModel(post) {
  return new Promise((resolve) => {
    if (!AI_CMD) return resolve(null);
    const c = spawn("/bin/sh", ["-c", AI_CMD], { stdio: ["pipe", "pipe", "ignore"], env: { PATH: process.env.PATH } });
    let out = ""; const t = setTimeout(() => { c.kill("SIGKILL"); resolve(null); }, 30000);
    c.stdout.on("data", (d) => { out += d; if (out.length > 20000) c.kill("SIGKILL"); });
    c.on("close", () => { clearTimeout(t); try { const r = JSON.parse(out); resolve(r && typeof r === "object" ? r : null); } catch { resolve(null); } });
    c.on("error", () => { clearTimeout(t); resolve(null); });
    c.stdin.end(JSON.stringify({ post: { text: post.text, thread: post.thread, edition: post.edition || "" },
      proposals: db.proposals.filter((p) => p.status !== "declined").map((p) => ({ id: p.id, title: p.title, asked: p.asked, edition: p.edition })) }));
  });
}
let triaging = false;
async function triage() {
  if (triaging) return; triaging = true;
  try {
    for (const post of db.posts.filter((p) => !p.reply && !p.staff && !p.proposal)) {
      const m = await askModel(post);
      let pr = null;
      if (m && Number.isInteger(m.proposal)) pr = db.proposals.find((p) => p.id === m.proposal && p.status !== "declined") || null;
      if (!pr && !m) pr = propFor(post);
      if (!pr) pr = newProposal(post, m ? { title: m.title, asked: m.asked, where: m.where, change: m.change, risk: m.risk, security: m.security === true, by: "model" } : {});
      attach(post, pr);
    }
    save();
  } finally { triaging = false; }
}

// ---------- people: sign-in with X (OAuth 2.0 with PKCE). Without X keys, a test sign-in works on this machine only.
const LOCAL_TEST = !X_ID;
const pendingAuth = new Map();                       // state -> {verifier, at}
function cookies(req) { const o = {}; for (const c of String(req.headers.cookie || "").split(";")) { const i = c.indexOf("="); if (i > 0) o[c.slice(0, i).trim()] = c.slice(i + 1).trim(); } return o; }
function who(req) { const s = db.sessions[cookies(req).zf]; if (!s || s.exp < Date.now()) return null; return db.users[s.user] || null; }
const isAdmin = (req) => { const c = cookies(req).zfa; return !!c && same(c, ADMIN); };
function startSession(res, user, extra) {
  const id = crypto.randomBytes(24).toString("base64url");
  db.sessions[id] = { user: user.id, exp: Date.now() + 30 * 864e5 };
  for (const [k, s] of Object.entries(db.sessions)) if (s.exp < Date.now()) delete db.sessions[k];
  save();
  const sec = PUBLIC_URL.startsWith("https:") ? "; Secure" : "";
  res.writeHead(302, { "Set-Cookie": [`zf=${id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000${sec}`].concat(extra || []), Location: "/" });
  res.end();
}
async function xCallback(u, res) {
  const st = pendingAuth.get(u.searchParams.get("state") || "");
  pendingAuth.delete(u.searchParams.get("state") || "");
  if (!st || Date.now() - st.at > 600000 || !u.searchParams.get("code")) return text(res, 400, "Sign-in expired. Try again.");
  const body = new URLSearchParams({ grant_type: "authorization_code", code: u.searchParams.get("code"), redirect_uri: PUBLIC_URL + "/auth/x/callback", code_verifier: st.verifier, client_id: X_ID });
  const h = { "Content-Type": "application/x-www-form-urlencoded" };
  if (X_SECRET) h.Authorization = "Basic " + Buffer.from(X_ID + ":" + X_SECRET).toString("base64");
  try {
    const tok = await (await fetch("https://api.x.com/2/oauth2/token", { method: "POST", headers: h, body })).json();
    if (!tok.access_token) return text(res, 502, "X did not sign you in.");
    const me = await (await fetch("https://api.x.com/2/users/me?user.fields=created_at", { headers: { Authorization: "Bearer " + tok.access_token } })).json();
    const d = me && me.data; if (!d || !d.id) return text(res, 502, "X did not say who you are.");
    const id = "x:" + d.id;
    const young = d.created_at && Date.now() - Date.parse(d.created_at) < 30 * 864e5;   // new accounts: fewer posts
    db.users[id] = Object.assign(db.users[id] || { joined: Date.now() }, { id, handle: "@" + clip(d.username, 30), name: clip(d.name, 40), via: "X", young: !!young });
    startSession(res, db.users[id]);                  // the X token is not kept
  } catch { text(res, 502, "Could not reach X."); }
}
function postsBy(user, ms) { const t = Date.now() - ms; return db.posts.filter((p) => p.user === user.id && p.at > t).length; }
function limited(user) {
  const f = user.young ? 0.4 : 1;
  if (user.banned) return "This account cannot post.";
  if (postsBy(user, 36e5) >= Math.max(1, Math.floor(LIMIT.hour * f))) return "You have posted a lot this hour. Try again later.";
  if (postsBy(user, 864e5) >= Math.max(1, Math.floor(LIMIT.day * f))) return "You have reached today's limit.";
  return null;
}

// ---------- what the page sees (no session ids, no internal user ids beyond the handle)
const author = (p) => { const u = db.users[p.user] || {}; return { name: u.name || "Someone", handle: u.handle || "", staff: !!p.staff }; };
const statusOf = (pr) => pr.status === "proposed" && pr.route === "fork" ? "fork idea" : pr.status;
function viewPost(p, me) {
  const pr = p.proposal && db.proposals.find((x) => x.id === p.proposal);
  return { id: p.id, thread: p.thread, edition: p.edition || "", text: p.text, at: p.at, ...author(p), ai: p.ai || "",
    proposal: pr ? { id: pr.id, status: statusOf(pr) } : null, metoo: (p.metoo || []).length,
    mine: !!me && (p.metoo || []).includes(me.id), replies: db.posts.filter((r) => r.reply === p.id).length };
}
function viewProposal(pr) {
  return { ...pr, status: statusOf(pr), people: new Set(pr.posts.map((id) => (db.posts.find((p) => p.id === id) || {}).user)).size,
    posts: pr.posts.map((id) => db.posts.find((p) => p.id === id)).filter(Boolean).map((p) => ({ id: p.id, thread: p.thread, text: clip(p.text, 140), ...author(p) })),
    steps: [["Posts grouped", true], ["Proposal drafted", pr.by === "model" || !!pr.change],
      ["Maintainer decision", ["accepted", "declined", "building", "released", "fork"].includes(pr.status)],
      ["Build, tests, proofs", ["building", "released"].includes(pr.status) && !!pr.pr], ["Released", pr.status === "released"]] };
}
function threadPosts(t, me) {
  let list;
  if (TH[t].view === "accepted") return { proposals: db.proposals.filter((p) => ["accepted", "building", "released", "fork"].includes(p.status)).map(viewProposal).reverse() };
  if (TH[t].edition) list = db.posts.filter((p) => !p.reply && p.edition === TH[t].edition);
  else list = db.posts.filter((p) => !p.reply && p.thread === t);
  return { posts: list.slice(-200).map((p) => viewPost(p, me)) };
}

// ---------- HTTP
const CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://x.com https://twitter.com";
function send(res, code, type, body, extra) { res.writeHead(code, Object.assign({ "Content-Type": type, "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store" }, extra || {})); res.end(body); }
const json = (res, code, o) => send(res, code, "application/json", JSON.stringify(o));
const text = (res, code, s) => send(res, code, "text/plain; charset=utf-8", s);
function readBody(req) { return new Promise((ok) => { let b = ""; req.on("data", (d) => { b += d; if (b.length > 20000) req.destroy(); }); req.on("end", () => { try { ok(JSON.parse(b || "{}")); } catch { ok({}); } }); }); }
const STATIC = { "/": ["board.html", "text/html; charset=utf-8"], "/board.js": ["board.js", "text/javascript"], "/logo.svg": ["logo.svg", "image/svg+xml"] };

const loopback = (req) => ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(req.socket.remoteAddress) && /^(localhost|127\.0\.0\.1)(:\d+)?$/.test(req.headers.host || "");
async function handle(req, res) {
  const u = new URL(req.url, "http://x");
  const p = u.pathname;
  if (req.method === "GET" && STATIC[p]) { const [f, t] = STATIC[p]; return send(res, 200, t, fs.readFileSync(path.join(__dirname, f))); }
  if (p === "/auth/x/start") {
    if (!X_ID) return text(res, 404, "X sign-in is not set up on this server.");
    const state = crypto.randomBytes(16).toString("base64url"), verifier = crypto.randomBytes(32).toString("base64url");
    pendingAuth.set(state, { verifier, at: Date.now() });
    const q = new URLSearchParams({ response_type: "code", client_id: X_ID, redirect_uri: PUBLIC_URL + "/auth/x/callback", scope: "users.read tweet.read",
      state, code_challenge: crypto.createHash("sha256").update(verifier).digest("base64url"), code_challenge_method: "S256" });
    res.writeHead(302, { Location: "https://x.com/i/oauth2/authorize?" + q }); return res.end();
  }
  if (p === "/auth/x/callback") return xCallback(u, res);
  if (req.method === "POST" && req.headers["x-zf"] !== "1") return json(res, 403, { error: "bad request" });   // only the board's own script
  if (p === "/auth/test" && req.method === "POST") {
    if (!LOCAL_TEST || !loopback(req)) return json(res, 403, { error: "Test sign-in works only on this machine, before X is set up." });
    const b = await readBody(req); const h = clip(String(b.handle || "tester").replace(/[^A-Za-z0-9_]/g, ""), 15) || "tester";
    const id = "test:" + h; db.users[id] = db.users[id] || { id, handle: "@" + h, name: clip(b.name || h, 40), via: "test", joined: Date.now() };
    return startSession(res, db.users[id]);
  }
  if (p === "/auth/out" && req.method === "POST") { delete db.sessions[cookies(req).zf]; save(); res.writeHead(204, { "Set-Cookie": ["zf=; Path=/; Max-Age=0", "zfa=; Path=/; Max-Age=0"] }); return res.end(); }
  const me = who(req), admin = isAdmin(req);
  if (p === "/api/state") return json(res, 200, { me: me && { handle: me.handle, name: me.name, via: me.via }, admin, signin: LOCAL_TEST ? "test" : "x",
    threads: THREADS.map((t) => ({ id: t.id, group: t.group, about: t.about, staff: !!t.staff, view: t.view || "",
      count: t.view === "accepted" ? db.proposals.filter((x) => ["accepted", "building", "released", "fork"].includes(x.status)).length
        : db.posts.filter((x) => !x.reply && (t.edition ? x.edition === t.edition : x.thread === t.id)).length })) });
  if (p === "/api/thread") { const t = u.searchParams.get("t"); if (!TH[t]) return json(res, 404, { error: "no such thread" }); return json(res, 200, threadPosts(t, me)); }
  if (p === "/api/replies") { const id = +u.searchParams.get("post"); return json(res, 200, { posts: db.posts.filter((r) => r.reply === id).map((r) => viewPost(r, me)) }); }
  if (p === "/api/proposal") { const pr = db.proposals.find((x) => x.id === +u.searchParams.get("id")); return pr ? json(res, 200, viewProposal(pr)) : json(res, 404, { error: "no such proposal" }); }
  if (req.method !== "POST") return json(res, 404, { error: "not found" });
  const b = await readBody(req);
  if (p === "/api/admin/login") { if (!same(String(b.token || ""), ADMIN)) return json(res, 403, { error: "wrong token" });
    res.writeHead(204, { "Set-Cookie": `zfa=${ADMIN}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200${PUBLIC_URL.startsWith("https:") ? "; Secure" : ""}` }); return res.end(); }
  if (p === "/api/admin/decide") {
    if (!admin) return json(res, 403, { error: "maintainers only" });
    const pr = db.proposals.find((x) => x.id === +b.id); if (!pr) return json(res, 404, { error: "no such proposal" });
    if (b.status !== undefined) { if (!STATUSES.includes(b.status)) return json(res, 400, { error: "bad status" }); pr.status = b.status; }
    for (const k of ["note", "change", "risk", "title"]) if (typeof b[k] === "string") pr[k] = clip(b[k], k === "title" ? 80 : 400);
    for (const k of ["pr", "release"]) if (typeof b[k] === "string") { if (b[k] && !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(pull|releases|issues)\/[\w./-]+$/.test(b[k])) return json(res, 400, { error: "links go to the project's GitHub" }); pr[k] = b[k]; }
    pr.decided = Date.now(); save(); return json(res, 200, viewProposal(pr));
  }
  if (!me && !(admin && p === "/api/post")) return json(res, 401, { error: "Sign in with X to post." });
  if (p === "/api/post") {
    const t = TH[b.thread]; if (!t || t.view) return json(res, 400, { error: "no such thread" });
    if (t.staff && !admin) return json(res, 403, { error: "Only the project posts here." });
    const body = String(b.text || "").trim(); if (body.length < 10) return json(res, 400, { error: "Say a little more (10 characters or more)." });
    if (body.length > 2000) return json(res, 400, { error: "Keep it under 2000 characters." });
    if (me && !admin) { const l = limited(me); if (l) return json(res, 429, { error: l }); }
    const ed = t.edition || (EDITIONS.includes(b.edition) ? b.edition : "");
    const post = { id: ++db.seq, thread: t.id, edition: ed, text: body, at: Date.now(), user: me ? me.id : "staff", staff: !!t.staff || (!me && admin), metoo: [] };
    if (post.staff) db.users.staff = { id: "staff", handle: "@zenos", name: "ZENOS project" };
    db.posts.push(post); save(); setImmediate(triage); return json(res, 200, { ok: true, id: post.id });
  }
  if (p === "/api/reply") {
    const parent = db.posts.find((x) => x.id === +b.post && !x.reply); if (!parent) return json(res, 404, { error: "no such post" });
    const body = String(b.text || "").trim(); if (body.length < 2 || body.length > 1000) return json(res, 400, { error: "Replies are 2 to 1000 characters." });
    const l = limited(me); if (l) return json(res, 429, { error: l });
    db.posts.push({ id: ++db.seq, thread: parent.thread, reply: parent.id, text: body, at: Date.now(), user: me.id, metoo: [] }); save(); return json(res, 200, { ok: true });
  }
  if (p === "/api/metoo") {
    const x = db.posts.find((q) => q.id === +b.post && !q.reply); if (!x) return json(res, 404, { error: "no such post" });
    x.metoo = x.metoo || []; const i = x.metoo.indexOf(me.id); if (i < 0) x.metoo.push(me.id); else x.metoo.splice(i, 1);
    save(); return json(res, 200, { metoo: x.metoo.length, mine: i < 0 });
  }
  json(res, 404, { error: "not found" });
}

http.createServer((req, res) => handle(req, res).catch(() => { try { json(res, 500, { error: "server error" }); } catch {} }))
  .listen(PORT, HOST, () => console.log(`ZENOS Feedback on http://${HOST}:${PORT} (${LOCAL_TEST ? "test sign-in, this machine only" : "sign-in with X"}; ${AI_CMD ? "model triage" : "local grouping"}). Maintainer token: ${ADMIN_FILE}`));
setInterval(triage, 30000);
module.exports = { _db: () => db };

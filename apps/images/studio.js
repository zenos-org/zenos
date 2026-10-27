// ZENOS Images · Library and Studio (Figma 94:2, 94:307, 91:2). Names and paths are always set as text, never markup.
"use strict";
(function () {
const Z = window.zenos || { init: { level: 1 }, call: async () => null };
const $ = (id) => document.getElementById(id);
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "on") for (const [ev, f] of Object.entries(v)) e.addEventListener(ev, f);
    else if (k === "cls") e.className = v;
    else if (k === "style") e.style.cssText = v;
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : String(c));
  return e;
}
const fmt = (s) => { s = Math.max(0, s || 0); const m = Math.floor(s / 60), r = s - m * 60; return m + ":" + (r < 10 ? "0" : "") + r.toFixed(0).padStart(1, "0"); };
const fmt1 = (s) => { s = Math.max(0, s || 0); const m = Math.floor(s / 60), r = s - m * 60; return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1); };
const bg = (url) => url ? "background-image:url(" + JSON.stringify(url) + ")" : "";
const toast = (t) => { const m = $("msg"); if (!m) return; m.textContent = t; m.style.display = "block"; clearTimeout(m._z); m._z = setTimeout(() => (m.style.display = "none"), 3200); };
const store = { get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };

let lib = { audio: [], images: [], videos: [] }, meta = { playlists: [], albums: [], pairs: {}, projects: [] };
let view = "music", sel = null, q = "", chip = "all";
const audio = new Audio(); audio.preload = "metadata";
let playing = null;

// ---------- data ----------
async function load() {
  const [l, m] = await Promise.all([Z.call("studio_library", {}), Z.call("studio_meta_load", {})]);
  if (l && !l.error) lib = l; else if (l && l.error) toast(l.error);
  if (m && !m.error) meta = m;
}
const saveMeta = () => Z.call("studio_meta_save", { data: meta });
const byPath = (p) => lib.audio.concat(lib.images, lib.videos).find((x) => x.path === p);
const pairOf = (a) => meta.pairs[a.path] && byPath(meta.pairs[a.path]);
const projectsOf = (p) => meta.projects.filter((x) => x.audio === p || x.image === p);

// ---------- library ----------
function sideItem(icon, label, n, key) {
  const on = JSON.stringify(view) === JSON.stringify(key);
  return h("button", { cls: "zit" + (on ? " on" : ""), on: { click: () => { view = key; sel = null; renderLib(); } } }, h("i", {}, icon), h("span", {}, label), n != null ? h("small", {}, n) : null);
}
function renderSide() {
  const S = $("zside"); S.replaceChildren();
  S.append(...[h("div", { cls: "zsh" }, "Library"),
    sideItem("♪", "Music", lib.audio.length, "music"), sideItem("▣", "Pictures", lib.images.length, "pictures"),
    sideItem("◧", "Studio projects", meta.projects.length, "projects"), sideItem("▶", "Made videos", lib.videos.length, "videos"),
    h("div", { cls: "zsh" }, "Playlists"), meta.playlists.map((p, i) => sideItem("≡", p.name, p.items.length, { pl: i })),
    h("div", { cls: "zsh" }, "Picture albums"), meta.albums.map((p, i) => sideItem("▤", p.name, p.items.length, { al: i }))].flat());
  const add = h("button", { cls: "zadd", on: { click: () => newList(add) } }, "+  New playlist or album");
  S.append(add);
}
function newList(btn) {
  const inp = h("input", { type: "text", placeholder: "Name", maxlength: "60", style: "width:100%;background:rgba(0,0,0,.3);color:#fff;border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:6px 9px;font-size:12px" });
  const mk = (kind) => async () => { const n = inp.value.trim(); if (!n) return inp.focus(); meta[kind].push({ name: n, items: [] }); await saveMeta(); view = kind === "playlists" ? { pl: meta.playlists.length - 1 } : { al: meta.albums.length - 1 }; renderLib(); };
  const box = h("div", { style: "display:flex;flex-direction:column;gap:6px;padding:6px 8px" }, inp,
    h("div", { style: "display:flex;gap:6px" }, h("button", { cls: "btn2", on: { click: mk("playlists") } }, "Playlist"), h("button", { cls: "btn2", on: { click: mk("albums") } }, "Album")));
  btn.replaceWith(box); inp.focus();
}
function items() {
  const f = (arr) => q ? arr.filter((x) => x.name.toLowerCase().includes(q)) : arr;
  if (view === "music") return f(lib.audio);
  if (view === "pictures") return f(lib.images).filter((x) => chip === "all" || (chip === "studio" && meta.projects.some((p) => p.image === x.path)) || (chip === "audio" && Object.values(meta.pairs).includes(x.path)));
  if (view === "videos") return f(lib.videos);
  if (view.pl != null) return f((meta.playlists[view.pl] || { items: [] }).items.map(byPath).filter(Boolean));
  if (view.al != null) return f((meta.albums[view.al] || { items: [] }).items.map(byPath).filter(Boolean));
  return [];
}
const isPictures = () => view === "pictures" || view.al != null;
function renderMain() {
  const M = $("zlist"); M.replaceChildren();
  const seg = $("zseg"); [...seg.children].forEach((b) => b.classList.toggle("on", b.dataset.v === (isPictures() ? "pictures" : view === "projects" ? "projects" : "music")));
  $("zchips").style.display = isPictures() ? "flex" : "none";
  if (view === "projects") {
    if (!meta.projects.length) return M.append(h("div", { cls: "zempty" }, "No Studio projects yet. Choose a song, then Open in Studio."));
    for (const p of meta.projects.slice().reverse()) {
      const a = byPath(p.audio), im = byPath(p.image);
      M.append(h("div", { cls: "zrow", style: "grid-template-columns:36px 1fr 160px 70px", on: { click: () => a && openStudio(a, p) } },
        h("div", { cls: "zth", style: bg(im && im.url) }, im ? "" : "♪"), h("span", { cls: "t" }, (a ? a.name : "(audio moved)") + "  " + fmt(p.start) + "–" + fmt(p.end)),
        h("span", {}, p.video ? "Video made" : p.clip ? "AI motion ready" : "Draft"), h("span", {}, new Date(p.at || 0).toLocaleDateString())));
    }
    return;
  }
  const list = items();
  if (isPictures()) {
    if (!list.length) return M.append(h("div", { cls: "zempty" }, "No pictures here. Import some, or save pictures into Basic · L1 on the desktop or into Pictures."));
    const g = h("div", { cls: "zgrid" }); let month = "";
    for (const x of list) {
      const mo = new Date(x.mtime * 1000).toLocaleDateString(undefined, { month: "long", year: "numeric" });
      if (mo !== month) { month = mo; g.append(h("div", { cls: "zmonth" }, mo)); }
      const paired = Object.values(meta.pairs).includes(x.path);
      g.append(h("div", { cls: "zcell" + (sel && sel.path === x.path ? " sel" : ""), style: bg(x.url), title: x.name, on: { click: () => { sel = x; renderLib(); } } }, paired ? h("b", {}, "♪ with audio") : null));
    }
    return M.append(g);
  }
  if (!list.length) return M.append(h("div", { cls: "zempty" }, view === "videos" ? "Videos you make in the Studio appear here." : "No music here yet. Import songs, or save them into Music or Basic · L1."));
  M.append(h("div", { cls: "zrow hdr" }, ["#", "", "Title", "Folder", "Picture", "Size", "Level"].map((t) => h("span", {}, t))));
  list.forEach((x, i) => {
    const pic = pairOf(x), on = sel && sel.path === x.path;
    M.append(h("div", { cls: "zrow" + (on ? " sel" : ""), on: { click: () => { sel = x; renderLib(); }, dblclick: () => play(x) } },
      h("span", { style: playing === x.path ? "color:#C4B5FD" : "" }, playing === x.path ? "▶" : String(i + 1)),
      h("div", { cls: "zth", style: bg(pic && pic.url) }, pic ? "" : x.kind === "videos" ? "▶" : "♪"),
      h("span", { cls: "t" }, x.name), h("span", {}, x.dir.split("/").pop()), h("span", {}, pic ? pic.name : "—"),
      h("span", {}, (x.size / 1048576).toFixed(1) + " MB"), h("b", { cls: "zlvl lv1" }, "L" + x.level)));
  });
}
function renderDet() {
  const D = $("zdet"); D.replaceChildren();
  const x = sel || (view === "music" ? lib.audio[0] : null);
  if (!x) { D.append(h("div", { cls: "sub" }, "Choose a song or a picture to see it here.")); return; }
  const kv = (k, v) => h("div", { cls: "kv" }, h("b", {}, k), h("div", {}, v));
  if (x.kind === "images") {
    const used = Object.entries(meta.pairs).filter(([, im]) => im === x.path).map(([a]) => byPath(a)).filter(Boolean);
    D.append(h("div", { cls: "zcov", style: bg(x.url) }), h("h4", {}, x.name), h("div", { cls: "sub" }, (x.size / 1048576).toFixed(1) + " MB · L" + x.level),
      kv("Used with audio", used.length ? used.map((a) => a.name).join(", ") : "—"),
      kv("In albums", meta.albums.filter((a) => a.items.includes(x.path)).map((a) => a.name).join(", ") || "—"), kv("Folder", x.dir),
      used.length ? h("button", { cls: "btnp", on: { click: () => openStudio(used[0]) } }, "Open in Studio") : null,
      listPicker("albums", x, "Add to album…"),
      h("button", { cls: "btn2", on: { click: () => { window.__zopenImage && window.__zopenImage(x); } } }, "Edit (crop, adjust, mosaic)…"));
  } else {
    const pic = pairOf(x);
    D.append(h("div", { cls: "zcov", style: bg(pic && pic.url) }), h("h4", {}, x.name), h("div", { cls: "sub" }, (x.size / 1048576).toFixed(1) + " MB · L" + x.level),
      kv("Picture shown with it", pic ? pic.name : "—"), kv("In playlists", meta.playlists.filter((a) => a.items.includes(x.path)).map((a) => a.name).join(", ") || "—"),
      kv("Folder", x.dir), kv("Studio projects", String(projectsOf(x.path).length)),
      x.kind === "audio" ? h("button", { cls: "btnp", on: { click: () => openStudio(x) } }, "Open in Studio") : null,
      h("button", { cls: "btn2", on: { click: () => play(x) } }, playing === x.path && !audio.paused ? "Pause" : "Play"),
      x.kind === "audio" ? listPicker("playlists", x, "Add to playlist…") : null);
  }
  D.append(h("div", { cls: "hint" }, "Music and pictures stay in their folders. The library shows only plain files in L1 places: Basic · L1, Music, Pictures and Videos."));
}
function listPicker(kind, x, label) {
  if (!meta[kind].length) return h("button", { cls: "btn2", on: { click: () => toast("Make a " + (kind === "albums" ? "picture album" : "playlist") + " first (left column).") } }, label);
  const s = h("select", { cls: "btn2", style: "text-align:center" }, h("option", { value: "" }, label), meta[kind].map((l, i) => h("option", { value: String(i) }, l.name)));
  s.addEventListener("change", async () => { const l = meta[kind][+s.value]; if (!l) return; if (!l.items.includes(x.path)) l.items.push(x.path); await saveMeta(); toast("Added to " + l.name); renderLib(); });
  return s;
}
function renderNow() {
  const N = $("znow"), it = playing && byPath(playing);
  N.classList.toggle("on", !!it); if (!it) return;
  const pic = pairOf(it);
  $("zn_th").style.cssText = bg(pic && pic.url); $("zn_t").textContent = it.name;
  $("zn_p").textContent = audio.paused ? "▶" : "❚❚";
}
function renderLib() { renderSide(); renderMain(); renderDet(); renderNow(); }
function play(x) {
  if (playing === x.path) { audio.paused ? audio.play() : audio.pause(); return renderLib(); }
  playing = x.path; audio.src = x.url; audio.play().catch(() => toast("This file cannot be played here.")); renderLib();
}
audio.addEventListener("timeupdate", () => { if (!$("zn_s")) return; $("zn_s").max = audio.duration || 0; $("zn_s").value = audio.currentTime; $("zn_tm").textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration); if (stu.on) stuTick(); });
audio.addEventListener("play", () => { renderNow(); stuBtn(); }); audio.addEventListener("pause", () => { renderNow(); stuBtn(); });
async function importFiles() {
  const r = await Z.call("studio_import", { kind: isPictures() ? "images" : "audio" });
  if (r && r.error) return toast(r.error);
  if (r && r.length) { await load(); toast(r.length + (r.length === 1 ? " file" : " files") + " added"); renderLib(); }
}
async function openLib(on) {
  $("zlib").classList.toggle("on", on); $("zstu").classList.remove("on"); stu.on = false;
  $("blib") && $("blib").classList.toggle("on", on);
  if (on) { await load(); renderLib(); }
}

// ---------- studio ----------
const stu = { on: false, a: null, im: null, clip: null, dur: 0, peaks: [], start: 0, end: 0, fin: 1.5, fout: 3, loop: false, proj: null };
async function openStudio(a, proj) {
  $("zlib").classList.remove("on"); $("zstu").classList.add("on"); stu.on = true;
  stu.a = a; stu.proj = proj || null; stu.clip = proj && proj.clip ? byPath(proj.clip) : null;
  stu.im = proj && proj.image ? byPath(proj.image) : pairOf(a) || null;
  stu.fin = proj ? proj.fin : 1.5; stu.fout = proj ? proj.fout : 3;
  $("zs_name").textContent = a.name; $("zs_lab").textContent = "Reading the audio…";
  if (playing !== a.path) { playing = a.path; audio.src = a.url; }
  audio.pause();
  const r = await Z.call("studio_peaks", { path: a.path });
  if (!r || r.error) { $("zs_lab").textContent = (r && r.error) || "This audio could not be read."; return; }
  stu.peaks = r.peaks; stu.dur = r.duration; stu.start = proj ? proj.start : 0; stu.end = proj ? proj.end : r.duration;
  renderStudio();
}
function renderStudio() {
  $("zs_pic").style.cssText = stu.im ? bg(stu.im.url) : "";
  const v = $("zs_vid"); if (stu.clip) { v.src = stu.clip.url; v.style.display = "block"; v.play().catch(() => {}); } else { v.removeAttribute("src"); v.style.display = "none"; }
  $("zs_cap").textContent = stu.clip ? "AI motion (loops while the audio plays): " + stu.clip.name : stu.im ? "Picture shown while the audio plays: " + stu.im.name : "No picture yet. Choose one on the right.";
  $("zs_fi").value = stu.fin * 10; $("zs_fo").value = stu.fout * 10; $("zs_fiv").textContent = stu.fin.toFixed(1) + " s"; $("zs_fov").textContent = stu.fout.toFixed(1) + " s";
  const P = $("zs_picrow"); P.replaceChildren(h("div", { cls: "zth", style: bg(stu.im && stu.im.url) }), h("div", {}, h("b", {}, stu.im ? stu.im.name : "No picture"), h("small", {}, stu.im ? "L" + stu.im.level + " · " + stu.im.dir.split("/").pop() : "Choose one below")));
  $("zs_len").textContent = "Match the audio (" + fmt(stu.end - stu.start) + ")";
  const ok = stu.im && stu.im.level === 1; $("zs_make").disabled = !ok;
  $("zs_ainote").textContent = ok ? "L1 files only. The picture and your words are sent to the AI you registered, under your own account. ZENOS ships no video model." : "Choose an L1 picture first. Only L1 pictures can be sent to an AI.";
  aiForm(); drawWave(); stuTick(); stuBtn();
}
function drawWave() {
  const c = $("zs_cv"), W = c.clientWidth, H = c.clientHeight; if (!W) return;
  c.width = W * devicePixelRatio; c.height = H * devicePixelRatio; const g = c.getContext("2d"); g.scale(devicePixelRatio, devicePixelRatio); g.clearRect(0, 0, W, H);
  const n = stu.peaks.length || 1, bw = W / n, s0 = stu.start / (stu.dur || 1) * W, s1 = stu.end / (stu.dur || 1) * W;
  stu.peaks.forEach((p, i) => { const x = i * bw, hh = Math.max(3, p * (H - 14)); const inSel = x >= s0 && x <= s1; g.fillStyle = inSel ? "#B08CFF" : "rgba(255,255,255,.22)"; g.fillRect(x, (H - hh) / 2, Math.max(1, bw * 0.6), hh); });
  g.fillStyle = "rgba(0,0,0,.35)"; g.fillRect(0, 0, s0, H); g.fillRect(s1, 0, W - s1, H);
  const sl = $("zs_sel"); sl.style.left = s0 + "px"; sl.style.width = Math.max(0, s1 - s0) + "px";
  $("zs_h0").style.left = s0 + "px"; $("zs_h1").style.left = s1 + "px";
  $("zs_t0").textContent = fmt1(stu.start); $("zs_t1").textContent = fmt1(stu.end); $("zs_td").textContent = fmt(stu.dur);
  $("zs_t0").style.left = Math.max(0, Math.min(W - 80, s0 - 14)) + "px"; $("zs_t1").style.left = Math.max(40, Math.min(W - 70, s1 - 14)) + "px";
  $("zs_lab").textContent = "Audio · " + fmt(stu.dur) + " · trimmed to " + fmt(stu.start) + " – " + fmt(stu.end) + " (" + fmt(stu.end - stu.start) + ")";
}
function stuTick() {
  if (!stu.on) return; const W = $("zs_cv").clientWidth, t = audio.currentTime;
  $("zs_ph").style.left = (t / (stu.dur || 1) * W) + "px";
  $("zs_tm").textContent = fmt(Math.max(0, t - stu.start)) + " / " + fmt(stu.end - stu.start);
  if (!audio.paused && t >= stu.end) { if (stu.loop) audio.currentTime = stu.start; else { audio.pause(); audio.currentTime = stu.start; } }
}
function stuBtn() { const b = $("zs_play"); if (b) b.textContent = audio.paused ? "▶" : "❚❚"; }
function stuPlay() { if (audio.paused) { if (audio.currentTime < stu.start || audio.currentTime >= stu.end) audio.currentTime = stu.start; audio.play().catch(() => toast("This file cannot be played here.")); } else audio.pause(); }
function dragHandle(which) {
  return (e) => {
    e.preventDefault(); const r = $("zs_cv").getBoundingClientRect();
    const mv = (ev) => { const t = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * stu.dur;
      if (which === 0) stu.start = Math.min(t, stu.end - 0.5); else stu.end = Math.max(t, stu.start + 0.5); drawWave(); $("zs_len").textContent = "Match the audio (" + fmt(stu.end - stu.start) + ")"; };
    const up = () => { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); };
    addEventListener("mousemove", mv); addEventListener("mouseup", up);
  };
}
function aiForm() {
  const b = $("zs_aiset"); b.textContent = store.get("zs.ai.url", "") ? "Your video AI: " + (store.get("zs.ai.url", "").split("/")[2] || "") : "Register your video AI…";
}
async function choosePicture() {
  const lst = lib.images.length ? lib.images : (await load(), lib.images);
  const M = $("zs_pick"); M.replaceChildren(); M.style.display = "grid";
  if (!lst.length) { M.append(h("div", { cls: "hint" }, "No L1 pictures yet. Import some in the Library.")); return; }
  for (const x of lst.slice(0, 60)) M.append(h("div", { cls: "zcell", style: bg(x.url), title: x.name, on: { click: async () => { stu.im = x; stu.clip = null; meta.pairs[stu.a.path] = x.path; await saveMeta(); M.style.display = "none"; renderStudio(); } } }));
}
function project(extra) {
  let p = stu.proj;
  if (!p) { p = { audio: stu.a.path, at: Date.now() }; meta.projects.push(p); stu.proj = p; }
  Object.assign(p, { image: stu.im ? stu.im.path : null, clip: stu.clip ? stu.clip.path : null, start: stu.start, end: stu.end, fin: stu.fin, fout: stu.fout, at: Date.now() }, extra || {});
  return saveMeta();
}
async function saveAudio() {
  const r = await Z.call("studio_export_audio", { src: stu.a.path, start: stu.start, end: stu.end, fin: stu.fin, fout: stu.fout });
  if (!r) return; if (r.error) return toast(r.error);
  toast("Saved " + r.name); await project();
}
async function exportVideo() {
  if (!stu.im && !stu.clip) return toast("Choose a picture first.");
  $("zs_prog").textContent = "Making the video…";
  const r = await Z.call("studio_export_video", { audio: stu.a.path, image: stu.im && stu.im.path, clip: stu.clip && stu.clip.path, start: stu.start, end: stu.end, fin: stu.fin, fout: stu.fout });
  $("zs_prog").textContent = "";
  if (!r) return; if (r.error) return toast(r.error);
  toast("Saved " + r.name); await project({ video: r.path }); await load();
}
async function makeVideo() {
  const url = store.get("zs.ai.url", ""), key = store.get("zs.ai.key", ""), model = store.get("zs.ai.model", "");
  if (!url || !key) { $("zs_ai").classList.add("on"); return toast("Register your video AI first."); }
  const prompt = $("zs_prompt").value.trim(); if (!prompt) return $("zs_prompt").focus();
  $("zs_make").disabled = true; $("zs_prog").textContent = "Sent to your AI. This can take a few minutes…";
  const secs = Math.max(2, Math.min(10, Math.round(stu.end - stu.start)));
  const r = await Z.call("studio_ai", { image: stu.im.path, prompt, seconds: secs, endpoint: url, key, model });
  $("zs_make").disabled = false; $("zs_prog").textContent = "";
  if (!r) return; if (r.error) return toast(r.error);
  await load(); stu.clip = byPath(r.path) || r; await project(); renderStudio(); toast("AI motion ready: it loops under the audio when you export.");
}

// ---------- build ----------
function build() {
  const body = $("body"); if (!body || $("zlib")) return;
  const L = h("div", { id: "zlib" },
    h("div", { cls: "zside", id: "zside" }),
    h("div", { cls: "zmain" },
      h("div", { cls: "zhead" },
        h("div", { cls: "zseg inset", id: "zseg" }, ["music", "pictures", "projects"].map((v) => h("button", { "data-v": v, on: { click: () => { view = v; sel = null; renderLib(); } } }, v === "music" ? "Music" : v === "pictures" ? "Pictures" : "Projects"))),
        h("button", { cls: "btn2", on: { click: importFiles } }, "Import…"),
        h("input", { cls: "zsearch", placeholder: "Search songs, pictures", on: { input: (e) => { q = e.target.value.toLowerCase(); renderMain(); } } })),
      h("div", { cls: "zchips", id: "zchips" }, [["all", "All"], ["audio", "With audio"], ["studio", "Used in Studio"]].map(([k, t]) => h("button", { cls: "opt" + (k === chip ? " on" : ""), on: { click: (e) => { chip = k; [...e.target.parentNode.children].forEach((b) => b.classList.toggle("on", b === e.target)); renderMain(); } } }, t))),
      h("div", { cls: "zlist", id: "zlist" }),
      h("div", { cls: "znow glass", id: "znow" }, h("div", { cls: "zth", id: "zn_th" }), h("div", { cls: "nt" }, h("b", { id: "zn_t" }), h("small", { id: "zn_tm" })),
        h("button", { cls: "zplay", id: "zn_p", on: { click: () => { audio.paused ? audio.play() : audio.pause(); } } }, "▶"),
        h("input", { type: "range", id: "zn_s", min: "0", max: "1", step: "0.1", value: "0", on: { input: (e) => { audio.currentTime = +e.target.value; } } }),
        h("button", { cls: "btnp", on: { click: () => { const it = byPath(playing); if (it && it.kind === "audio") openStudio(it); } } }, "Open in Studio"))),
    h("div", { cls: "zdet", id: "zdet" }));
  const S = h("div", { id: "zstu" },
    h("div", { cls: "zstage" },
      h("div", { style: "align-self:stretch;display:flex;align-items:center;gap:10px;max-width:820px;width:100%;margin:0 auto" },
        h("button", { cls: "btn2", on: { click: () => openLib(true) } }, "‹ Library"), h("b", { id: "zs_name", style: "font-size:13px" })),
      h("div", { cls: "zpic", id: "zs_pic" }, h("video", { id: "zs_vid", muted: "", loop: "", playsinline: "" })),
      h("div", { cls: "zcap", id: "zs_cap" }),
      h("div", { cls: "ztl glass" },
        h("div", { cls: "lab", id: "zs_lab" }),
        h("div", { cls: "zwave", id: "zs_wave" }, h("canvas", { id: "zs_cv" }), h("div", { cls: "zsel", id: "zs_sel" }), h("div", { cls: "zph", id: "zs_ph" }),
          h("div", { cls: "zh", id: "zs_h0" }), h("div", { cls: "zh", id: "zs_h1" })),
        h("div", { cls: "ztimes" }, h("span", { id: "zs_t0" }), h("span", { id: "zs_t1" }), h("span", { id: "zs_td" })),
        h("div", { cls: "ztr" }, h("button", { cls: "zskip", on: { click: () => { audio.currentTime = stu.start; } } }, "«"),
          h("button", { cls: "zplay", id: "zs_play", on: { click: stuPlay } }, "▶"),
          h("button", { cls: "zskip", on: { click: () => { audio.currentTime = Math.max(stu.start, stu.end - 3); } } }, "»"),
          h("span", { id: "zs_tm" }), h("span", { cls: "sp" }),
          h("button", { cls: "opt on", on: { click: stuPlay } }, "Play selection"),
          h("button", { cls: "opt", id: "zs_loop", on: { click: (e) => { stu.loop = !stu.loop; e.target.classList.toggle("on", stu.loop); } } }, "Loop")))),
    h("div", { cls: "zpanel" },
      h("div", { style: "font-size:13px;font-weight:600" }, "Studio"),
      h("h5", {}, "Audio"),
      h("div", { cls: "sl" }, h("div", { cls: "h" }, h("span", {}, "Fade in"), h("span", { id: "zs_fiv" })), h("input", { type: "range", id: "zs_fi", min: "0", max: "100", on: { input: (e) => { stu.fin = e.target.value / 10; $("zs_fiv").textContent = stu.fin.toFixed(1) + " s"; } } })),
      h("div", { cls: "sl" }, h("div", { cls: "h" }, h("span", {}, "Fade out"), h("span", { id: "zs_fov" })), h("input", { type: "range", id: "zs_fo", min: "0", max: "100", on: { input: (e) => { stu.fout = e.target.value / 10; $("zs_fov").textContent = stu.fout.toFixed(1) + " s"; } } })),
      h("h5", {}, "Picture"),
      h("div", { cls: "zpicrow", id: "zs_picrow" }),
      h("button", { cls: "btn2", on: { click: choosePicture } }, "Choose picture…"),
      h("div", { cls: "zgrid", id: "zs_pick", style: "display:none;grid-template-columns:repeat(3,1fr);gap:6px;padding:0" }),
      h("h5", {}, "Motion with AI"),
      h("button", { cls: "btn2", id: "zs_aiset", on: { click: () => $("zs_ai").classList.toggle("on") } }),
      h("div", { cls: "zai", id: "zs_ai" },
        h("input", { type: "text", id: "zs_url", placeholder: "https://… (your video AI)", value: store.get("zs.ai.url", "") }),
        h("input", { type: "password", id: "zs_key", placeholder: "API key (kept on this PC)", value: store.get("zs.ai.key", "") }),
        h("input", { type: "text", id: "zs_model", placeholder: "Model (optional)", value: store.get("zs.ai.model", "") }),
        h("button", { cls: "btn2", on: { click: () => { const u = $("zs_url").value.trim(); if (u && !u.startsWith("https://")) return toast("The address must start with https://"); store.set("zs.ai.url", u); store.set("zs.ai.key", $("zs_key").value.trim()); store.set("zs.ai.model", $("zs_model").value.trim()); $("zs_ai").classList.remove("on"); aiForm(); toast("Saved on this PC."); } } }, "Save"),
        h("div", { cls: "hint" }, "Any service that turns a picture and a sentence into a short video. You choose it and use it under your own account; ZENOS adds none.")),
      h("textarea", { id: "zs_prompt", placeholder: "Describe the motion: camera, light, what moves" }),
      h("div", { cls: "zkv" }, h("span", {}, "Length"), h("span", { id: "zs_len" })),
      h("div", { cls: "hint", id: "zs_ainote" }),
      h("button", { cls: "btnp", id: "zs_make", on: { click: makeVideo } }, "Make video"),
      h("div", { cls: "zprog", id: "zs_prog" }),
      h("div", { cls: "zfoot" }, h("button", { cls: "btn2", on: { click: saveAudio } }, "Save audio"), h("button", { cls: "btnp", on: { click: exportVideo } }, "Export MP4"))));
  body.style.position = "relative"; body.append(L, S);
  $("zs_h0").addEventListener("mousedown", dragHandle(0)); $("zs_h1").addEventListener("mousedown", dragHandle(1));
  $("zs_wave").addEventListener("click", (e) => { if (e.target.classList.contains("zh")) return; const r = $("zs_cv").getBoundingClientRect(); audio.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * stu.dur; stuTick(); });
  addEventListener("resize", () => stu.on && drawWave());
  // the toolbar button
  const tb = document.querySelector("#top .tb");
  if (tb && !$("blib")) {
    const b = h("button", { cls: "ib", id: "blib", title: "Library and Studio (L)" });
    b.innerHTML = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none"><path d="M9 17.5V6l10-2v11.5" stroke="#fff" stroke-width="1.7" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5" stroke="#fff" stroke-width="1.7"/><circle cx="16.5" cy="15.5" r="2.5" stroke="#fff" stroke-width="1.7"/></svg>';
    b.addEventListener("click", () => openLib(!$("zlib").classList.contains("on") && !$("zstu").classList.contains("on")));
    tb.insertBefore(b, tb.firstChild);
  }
  addEventListener("keydown", (e) => {
    if (e.target.matches && e.target.matches("input,textarea,select")) return;
    const over = $("zlib").classList.contains("on") || $("zstu").classList.contains("on");
    if ((e.key === "l" || e.key === "L") && !e.ctrlKey && !e.metaKey) { e.stopPropagation(); openLib(!over); return; }
    if (!over) return;
    if (e.ctrlKey || e.metaKey) return;               // Ctrl+O still opens pictures
    e.stopPropagation();                              // keys for the picture viewer do nothing under the Library
    if (stu.on && e.key === " ") { e.preventDefault(); stuPlay(); }
    else if (e.key === "Escape") { stu.on ? openLib(true) : openLib(false); }
  }, true);
  // opened with an audio file: go straight to the Studio
  const f = Z.init && Z.init.file;
  if (f && /\.(mp3|m4a|aac|wav|flac|ogg|oga|opus)$/i.test(f.name || "")) load().then(() => { const a = lib.audio.find((x) => x.path === f.path) || Object.assign({ kind: "audio", level: 1 }, f); openStudio(a); });
}
window.__zstudio = { openLib, openStudio };
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build); else build();
})();

// ZENOS Messages: sign-in with this phone (phone side).
// The PC's vault service (zenos_credd) asks; this page shows the site, the account and three codes. The person picks
// the code the PC shows and approves with fingerprint, face or PIN. The phone's passkey signs this request's digest and
// derives the entry's key (WebAuthn PRF), which goes to the PC encrypted to the request's one-time key: the ZENOS
// Messages process in between sees neither the password nor the key.
// Uses ui.html's helpers ($, api, post, esc, me).
"use strict";
(() => {
  const b64u = (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const unb64u = (s) => Uint8Array.from(atob(String(s).replace(/-/g, "+").replace(/_/g, "/") + "===".slice((String(s).length + 3) % 4)), (c) => c.charCodeAt(0));
  const enc = new TextEncoder();
  const host = (o) => String(o || "").replace(/^https:\/\//, "");
  const MSG = {
    "code-mismatch": "That was not the number on your PC. Nothing was released. Start again on the PC.",
    "expired": "The request expired. Start again on the PC.",
    "already-answered": "This request was already answered.",
    "not-for-this-request": "The approval did not match this request.",
    "person-not-verified": "Your phone did not verify you. Use fingerprint, face or PIN.",
    "cloned-passkey": "This phone's key looks copied. Tell your administrator.",
    "unknown-phone": "This phone is not registered for sign-in.",
    "wrong-phone-page": "Approve only from ZENOS Messages on your phone.",
    "bad-key-envelope": "The key could not be passed to the PC. Try again.",
    "wrong-phone-key": "This password was saved with another phone.",
  };

  // the entry's key, encrypted to this request's one-time key (ECDH P-256, HKDF-SHA-256, AES-GCM bound to the digest)
  async function envelope(p, prf) {
    const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
    const peer = await crypto.subtle.importKey("raw", unb64u(p.server_key), { name: "ECDH", namedCurve: "P-256" }, false, []);
    const bits = await crypto.subtle.deriveBits({ name: "ECDH", public: peer }, kp.privateKey, 256);
    const hk = await crypto.subtle.importKey("raw", bits, "HKDF", false, ["deriveKey"]);
    const dig = unb64u(p.challenge);
    const k = await crypto.subtle.deriveKey({ name: "HKDF", hash: "SHA-256", salt: dig, info: enc.encode("zenos-cred-prf") }, hk, { name: "AES-GCM", length: 256 }, false, ["encrypt"]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: dig }, k, prf);
    return { phone_key: b64u(await crypto.subtle.exportKey("raw", kp.publicKey)), iv: b64u(iv), ct: b64u(ct) };
  }

  async function approve(p, code) {
    const cred = await navigator.credentials.get({ publicKey: {
      challenge: unb64u(p.challenge), rpId: p.rp_id || location.hostname, timeout: 90000, userVerification: "required",
      allowCredentials: (p.allow || []).map((id) => ({ type: "public-key", id: unb64u(id) })),
      extensions: { prf: { eval: { first: unb64u(p.salt) } } } } });
    const ext = cred.getClientExtensionResults ? cred.getClientExtensionResults() : {};
    const prf = ext.prf && ext.prf.results && ext.prf.results.first;
    if (!prf) throw new Error("This phone could not unlock the key (its passkeys lack the PRF extension).");
    const r = cred.response;
    return post("cred/answer", { id: p.id, code, credential_id: b64u(cred.rawId), authenticator_data: b64u(r.authenticatorData),
      client_data_json: b64u(r.clientDataJSON), signature: b64u(r.signature), ...(await envelope(p, prf)) });
  }

  // ---------- the request sheet
  (() => { const s = document.createElement("style"); s.textContent = `
#zcred{position:fixed;right:20px;bottom:20px;width:400px;max-width:calc(100vw - 24px);z-index:41;background:var(--side);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 12px 32px rgba(0,0,0,.5);display:none}
#zcred .zh{display:flex;align-items:center;gap:10px;margin-bottom:12px}#zcred .zh i{width:10px;height:10px;border-radius:5px;background:var(--acc)}#zcred .zh b{font-size:17px;font-weight:600;color:var(--t-strong);flex:1}#zcred .zh span{font-size:12px;color:var(--t-mute)}
#zcred .zkv{background:var(--bg);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:80px 1fr;gap:6px 12px;font-size:13px;margin-bottom:14px}#zcred .zkv span{color:var(--t-mute)}#zcred .zkv b{color:var(--t-head);font-weight:500;word-break:break-all}
#zcred .zn{font-size:13px;line-height:1.5;color:var(--t-sub);margin-bottom:10px}
#zcred .zc{display:flex;gap:10px;margin-bottom:14px}#zcred .zc button{flex:1;border:1px solid var(--chipline);border-radius:10px;padding:14px 0;font:600 24px Inter,system-ui,sans-serif;background:var(--bg);color:var(--t-strong);cursor:pointer}
#zcred .zb{display:flex;gap:10px}#zcred .zb button{flex:1;border:0;border-radius:8px;padding:10px 18px;font:500 14px Inter,system-ui,sans-serif;cursor:pointer;background:var(--tile);color:var(--t-body)}
#zcred .zm{font-size:13px;margin:0 0 12px}#zcred .zm.ok{color:#4ADE80}#zcred .zm.ng{color:#FCA5A5}#zcred .zw{font-size:13px;color:#FCA5A5;margin-bottom:10px}
@media(max-width:700px){#zcred{right:12px;left:12px;bottom:calc(12px + env(safe-area-inset-bottom));width:auto}}`; document.head.appendChild(s); })();

  let cur = null, note = null, sig = "", busy = false;
  const gone = new Set();
  function sheet() { let el = $("zcred"); if (!el) { el = document.createElement("div"); el.id = "zcred"; document.body.appendChild(el); } return el; }

  async function poll() {
    if (!me || !me.remote || busy) return;
    const r = await api("cred/pending").catch(() => null);
    if (!r) return;
    const p = (r.pending || []).find((x) => !gone.has(x.id));
    if (!p && !note) { cur = null; sig = ""; sheet().style.display = "none"; return; }
    if (p && (!cur || cur.id !== p.id) && !note) { cur = p; draw(); }
  }

  function draw() {
    const el = sheet(), p = cur;
    const s = (p ? p.id : "") + "|" + (note ? note.text : "");
    if (s === sig) return; sig = s;
    el.style.display = "block";
    if (note) {
      el.innerHTML = `<div class="zh"><i></i><b>${note.ok ? "Done" : "Not released"}</b></div><div class="zm ${note.ok ? "ok" : "ng"}">${esc(note.text)}</div><div class="zb"><button id="zcclose">Close</button></div>`;
      $("zcclose").onclick = () => { note = null; cur = null; sig = ""; el.style.display = "none"; poll(); };
      return;
    }
    const left = Math.max(0, Math.round((p.expires - Date.now()) / 1000));
    el.innerHTML = `<div class="zh"><i></i><b>${p.kind === "save" ? "Save a password" : "Sign-in request"}</b><span id="zcleft">${left}s</span></div>
      <div class="zkv"><span>Site</span><b>${esc(host(p.origin))}</b><span>Account</span><b>${esc(p.account || "")}</b><span>Asked</span><b>${esc(new Date(p.created).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</b></div>
      ${p.tls_ok ? "" : '<div class="zw">The PC could not verify this site\'s connection. Do not approve.</div>'}
      <div class="zn">${p.kind === "save" ? "Your PC wants to keep this password, opened only by this phone." : "Your PC wants to sign in."} Check the site. Tap the number your PC shows, then confirm with fingerprint or face.</div>
      <div class="zc">${p.codes.map((c) => `<button data-code="${c}">${String(c).padStart(2, "0")}</button>`).join("")}</div>
      <div class="zb"><button id="zcno">Decline</button></div>`;
    el.querySelectorAll("[data-code]").forEach((b) => b.onclick = () => go(p, +b.dataset.code));
    $("zcno").onclick = async () => { gone.add(p.id); await post("cred/answer", { id: p.id, decline: true }).catch(() => {}); note = { ok: true, text: "Declined. Nothing was released." }; draw(); };
    clearInterval(window._zcl); window._zcl = setInterval(() => { const e = $("zcleft"); if (!e || !cur) return clearInterval(window._zcl);
      const l = Math.max(0, Math.round((cur.expires - Date.now()) / 1000)); e.textContent = l + "s"; if (!l) { gone.add(cur.id); note = { ok: false, text: MSG.expired }; draw(); } }, 1000);
  }

  async function go(p, code) {
    busy = true; gone.add(p.id);
    let r;
    try { r = await approve(p, code); } catch (e) { r = { error: e.name === "NotAllowedError" ? "Cancelled on the phone. Nothing was released." : e.message }; }
    busy = false;
    note = r && r.ok ? { ok: true, text: p.kind === "save" ? "Saved on your PC, locked to this phone." : "Approved. Your PC is signing in." }
      : { ok: false, text: MSG[r && r.error] || (r && r.error) || "Not released." };
    draw();
  }

  // ---------- Settings: set this phone up for sign-in (the administrator gives a one-time enrolment code)
  async function settings(box) {
    if (!box) return;
    if (!window.PublicKeyCredential) { box.innerHTML = '<p class="warn">This browser has no passkeys.</p>'; return; }
    box.innerHTML = `<p>Passwords on your ZENOS PC open only after you approve here with fingerprint or face. Ask your administrator for an enrolment code (sudo zenos_credd.py --enroll ${esc(me.id)}).</p>
      <div class="rowb" style="margin-top:8px"><input id="zcenc" inputmode="numeric" maxlength="8" placeholder="Enrolment code" style="width:160px;letter-spacing:.1em"><button class="send" id="zcenb">Set up</button></div><div class="kv" id="zcenm"></div>`;
    $("zcenb").onclick = async () => {
      const m = $("zcenm"); m.textContent = "";
      try {
        const s = await post("cred/enroll/start", { code: $("zcenc").value.trim() });
        if (s.error) throw new Error(s.error);
        const cred = await navigator.credentials.create({ publicKey: {
          rp: { id: s.rp_id, name: "ZENOS" }, user: { id: unb64u(s.user_handle), name: s.user, displayName: s.user },
          challenge: unb64u(s.challenge), timeout: 120000, attestation: "none",
          pubKeyCredParams: [{ type: "public-key", alg: -7 }, { type: "public-key", alg: -8 }],
          authenticatorSelection: { authenticatorAttachment: "platform", residentKey: "preferred", userVerification: "required" },
          extensions: { prf: {} } } });
        const ext = cred.getClientExtensionResults ? cred.getClientExtensionResults() : {};
        const r = await post("cred/enroll/finish", { challenge: s.challenge, prf: !!(ext.prf && ext.prf.enabled),
          attestation_object: b64u(cred.response.attestationObject), client_data_json: b64u(cred.response.clientDataJSON),
          name: (navigator.userAgent.match(/\(([^)]+)\)/) || [, "phone"])[1].slice(0, 60) });
        if (r.error) throw new Error(r.error);
        m.innerHTML = '<span class="ok">This phone now approves sign-ins on your PC.</span>';
      } catch (e) { m.innerHTML = `<span class="ng">${esc(e.name === "NotAllowedError" ? "Cancelled." : e.message)}</span>`; }
    };
  }

  window.zcred = { poll, settings };
  setInterval(() => poll().catch(() => {}), 2000);
})();

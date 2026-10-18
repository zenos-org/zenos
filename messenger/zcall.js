/* ZENOS call module — WebRTC via a self-hosted LiveKit SFU, media end-to-end encrypted.
   The call key is created on a device and handed to members only inside libsignal-encrypted messages;
   the SFU forwards encrypted frames and never holds the key. */
(function () {
  const LK = window.LivekitClient;
  let lastHeal = 0;
  let room = null, onState = () => {}, grid = null, names = {}, kp = null, keyIdx = 0, onMembers = null, memTimer = null;
  // shared call key with Signal-style rotation: on every join/leave a new key is handed (via libsignal) only to
  // the people actually in the call; everyone switches 3 s later, so a departed member cannot follow the call.
  class ZKeyProvider extends LK.ExternalE2EEKeyProvider {
    async addKey(buf, idx, switchNow) {
      const key = await LK.createKeyMaterialFromBuffer(buf);
      const info = { key, participantIdentity: undefined, keyIndex: idx };
      this.keyInfoMap.set("shared-" + idx, info);
      this.emit(LK.KeyProviderEvent.SetKey, info, !!switchNow);
    }
  }
  function members() { return room ? [room.localParticipant.identity, ...room.remoteParticipants.keys()].sort() : []; }
  function membershipChanged() {
    if (!onMembers || !room) return;
    clearTimeout(memTimer);
    memTimer = setTimeout(() => { const m = members(); if (m[0] === room.localParticipant.identity) onMembers(m, (keyIdx + 1) % 16); }, 1500);
  }
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0)).buffer;
  function tile(id) {
    let t = grid.querySelector(`[data-p="${CSS.escape(id)}"]`);
    if (!t) {
      t = document.createElement("div"); t.className = "ctile"; t.dataset.p = id;
      t.innerHTML = `<div class="cav">${names.avatar ? names.avatar(id) : ""}</div><div class="cnm"></div>`;
      grid.appendChild(t);
    }
    t.querySelector(".cnm").textContent = names.label ? names.label(id) : id;
    if (!t.dataset.laid) { t.dataset.laid = 1; setTimeout(layout, 0); }
    return t;
  }
  function attach(track, pid) {
    const t = tile(pid);
    if (track.kind === "video") {
      t.querySelectorAll("video").forEach((v) => v.remove());
      const el = track.attach(); el.playsInline = true; el.muted = true; el.autoplay = true; t.prepend(el); t.classList.add("hasv"); el.play().catch(() => {});
    } else if (track.kind === "audio") { const el = track.attach(); el.style.display = "none"; t.appendChild(el); }
  }
  function detach(track, pid) { track.detach().forEach((e) => e.remove()); if (track.kind === "video") { const t = tile(pid); t.classList.remove("hasv"); } }
  // "stage" layout: whoever spoke most recently is the largest tile, the one before them the next largest, and so on.
  // Your own tile always stays small at the end.
  let lastSpoke = {}, joinedAt = {};
  let mode = (() => { try { return localStorage.getItem("zenos-call-layout") || "stage"; } catch (_) { return "stage"; } })();
  function setMode(m) { mode = m === "grid" ? "grid" : "stage"; try { localStorage.setItem("zenos-call-layout", mode); } catch (_) {} layout(); return mode; }
  function layout() {
    if (!grid || !room) return;
    const me = room.localParticipant.identity;
    const tiles = [...grid.querySelectorAll(".ctile")];
    tiles.forEach((t) => { if (!(t.dataset.p in joinedAt)) joinedAt[t.dataset.p] = Date.now(); });
    const others = tiles.filter((t) => t.dataset.p !== me)
      .sort((a, b) => (lastSpoke[b.dataset.p] || 0) - (lastSpoke[a.dataset.p] || 0) || joinedAt[a.dataset.p] - joinedAt[b.dataset.p]);
    // tiers, each half the width of the one above: 1st = full width, 2nd = 1/2, next four = 1/4 (a 2x2 block the size of the 2nd),
    // everyone else (and you) = small 1/8 thumbnails in a strip underneath
    const grid4 = mode === "grid";   // "grid" mode: everyone the same size, no reordering by speaker
    const tier = (i) => grid4 ? "eq" : i === 0 ? "r1" : i === 1 ? "r2" : i <= 5 ? "r3" : "r4";
    others.forEach((t, i) => { t.style.order = i; t.classList.remove("r1", "r2", "r3", "r4", "eq"); t.classList.add(tier(i)); if (grid4) t.style.order = joinedAt[t.dataset.p] % 100000; });
    const mine = tiles.find((t) => t.dataset.p === me); if (mine) { mine.style.order = 9999999; mine.classList.remove("r1", "r2", "r3", "r4", "eq"); mine.classList.add(grid4 ? "eq" : "r4", "self"); }
    // when only you and one other are in the call, the other takes the stage

  }
  function speakers(list) {
    const now = Date.now(); list.forEach((p) => { lastSpoke[p.identity] = now; });
    grid.querySelectorAll(".ctile").forEach((t) => t.classList.toggle("spk", list.some((p) => p.identity === t.dataset.p)));
    layout();
  }
  async function join({ url, token, key, gridEl, video, label, avatar, workerUrl, state }) {
    if (room) await leave();
    grid = gridEl; names = { label, avatar, onScreen: arguments[0].onScreen }; onState = state || (() => {}); grid.innerHTML = "";
    const keyProvider = kp = new ZKeyProvider(); keyIdx = 0; onMembers = arguments[0].onMembers || null;
    await keyProvider.addKey(b64(key), 0, true);
    room = new LK.Room({ adaptiveStream: false, dynacast: true, encryption: { keyProvider, worker: new Worker(workerUrl) },
      audioCaptureDefaults: { deviceId: pref("audioinput"), echoCancellation: true, noiseSuppression: true },
      videoCaptureDefaults: { deviceId: pref("videoinput") } });
    const isScreen = (pub) => pub && pub.source === LK.Track.Source.ScreenShare;
    room.on(LK.RoomEvent.TrackSubscribed, (tr, pub, p) => { if (isScreen(pub)) { if (names.onScreen) names.onScreen(tr.attach(), p.identity); } else attach(tr, p.identity); })
      .on(LK.RoomEvent.TrackUnsubscribed, (tr, pub, p) => { if (isScreen(pub)) { tr.detach(); if (names.onScreen) names.onScreen(null, p.identity); } else detach(tr, p.identity); })
      .on(LK.RoomEvent.LocalTrackUnpublished, (pub) => { if (isScreen(pub) && names.onScreen) names.onScreen(null, room && room.localParticipant.identity); })
      .on(LK.RoomEvent.ParticipantConnected, (p) => { tile(p.identity); onState(info()); membershipChanged(); })
      .on(LK.RoomEvent.ParticipantDisconnected, (p) => { const t = grid.querySelector(`[data-p="${CSS.escape(p.identity)}"]`); if (t) t.remove(); onState(info()); membershipChanged(); layout(); })
      .on(LK.RoomEvent.ActiveSpeakersChanged, speakers)
      // someone turns their camera off/on: show the avatar while it is off, the video again when it comes back
      .on(LK.RoomEvent.TrackMuted, (pub, p) => { if (pub.kind === "video") tile(p.identity).classList.remove("hasv"); })
      .on(LK.RoomEvent.TrackUnmuted, (pub, p) => {
        if (pub.kind !== "video" || !pub.track) return;
        const t = tile(p.identity), v = t.querySelector("video");
        if (v) { t.classList.add("hasv"); v.play().catch(() => {}); } else attach(pub.track, p.identity);   // keep the same element (Safari)
      })
      .on(LK.RoomEvent.LocalTrackPublished, (pub) => { if (!pub.track) return; if (isScreen(pub)) { if (names.onScreen) names.onScreen(pub.track.attach(), room.localParticipant.identity); } else if (pub.kind === "video") attach(pub.track, room.localParticipant.identity); })
      .on(LK.RoomEvent.EncryptionError, (e) => { const now = Date.now(); if (now - lastHeal > 4000) { lastHeal = now; membershipChanged(); }
        onState({ ...info(), error: /missing ?key|invalid ?key|decrypt/i.test(String(e && e.message)) ? "Re-syncing call keys…" : "Encryption error: " + (e && e.message) }); })
      .on(LK.RoomEvent.ParticipantEncryptionStatusChanged, () => onState({ ...info(), error: "" }))
      .on(LK.RoomEvent.Disconnected, () => onState({ ended: true }));
    await room.setE2EEEnabled(true);
    await room.connect(url, token);
    setTimeout(membershipChanged, 500);
    tile(room.localParticipant.identity);
    room.remoteParticipants.forEach((p) => tile(p.identity));
    try { await room.localParticipant.setMicrophoneEnabled(true); } catch (e) { onState({ ...info(), error: "Microphone: " + e.message }); }
    if (video) { try { await room.localParticipant.setCameraEnabled(true); } catch (e) { onState({ ...info(), error: "Camera: " + e.message }); } }
    onState(info()); return info();
  }
  function info() {
    if (!room) return {};
    const lp = room.localParticipant;
    return { connected: room.state === "connected", e2ee: room.isE2EEEnabled, count: room.remoteParticipants.size + 1,
      mic: lp.isMicrophoneEnabled, cam: lp.isCameraEnabled, keyIndex: keyIdx, members: members(),
      remote: [...room.remoteParticipants.values()].map((p) => ({ id: p.identity, encrypted: p.isEncrypted, tracks: [...p.trackPublications.values()].filter((t) => t.track).map((t) => t.kind) })) };
  }
  async function applyKey(keyB64, idx, delayMs) {
    if (!kp) return;
    await kp.addKey(b64(keyB64), idx, false);
    setTimeout(async () => { if (kp) { await kp.addKey(b64(keyB64), idx, true); keyIdx = idx; onState({ ...info(), error: "" }); } }, delayMs === undefined ? 3000 : delayMs);
  }
  async function leave() { lastSpoke = {}; joinedAt = {}; clearTimeout(memTimer); onMembers = null; kp = null; if (room) { const r = room; room = null; await r.disconnect(); } if (grid) grid.innerHTML = ""; }
  async function toggle(kind) {
    if (!room) return; const lp = room.localParticipant;
    if (kind === "mic") await lp.setMicrophoneEnabled(!lp.isMicrophoneEnabled);
    if (kind === "cam") {
      await lp.setCameraEnabled(!lp.isCameraEnabled);
      const t = tile(lp.identity);
      if (!lp.isCameraEnabled) { t.querySelectorAll("video").forEach((v) => v.remove()); t.classList.remove("hasv"); }
      else { const pub = lp.getTrackPublication(LK.Track.Source.Camera); if (pub && pub.track) attach(pub.track, lp.identity); }   // camera back on: show it again
    }
    onState(info());
  }
  // microphone / camera choice (e.g. an iRig audio interface); remembered on this device
  const pref = (k) => { try { return localStorage.getItem("zenos-dev-" + k) || undefined; } catch (_) { return undefined; } };
  async function devices(kind) { try { return await LK.Room.getLocalDevices(kind, true); } catch (_) { return []; } }
  async function switchDevice(kind, id) {
    try { localStorage.setItem("zenos-dev-" + kind, id); } catch (_) {}
    if (room) await room.switchActiveDevice(kind, id);
  }
  async function screen(on) { if (!room) return false; await room.localParticipant.setScreenShareEnabled(!!on); return room.localParticipant.isScreenShareEnabled; }
  const canScreen = () => !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);
  window.ZCall = { join, leave, toggle, info, screen, canScreen, applyKey, devices, switchDevice, setMode, mode: () => mode, supported: () => typeof RTCPeerConnection !== "undefined" && LK && LK.isE2EESupported && LK.isE2EESupported() };
})();

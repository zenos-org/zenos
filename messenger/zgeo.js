// Place on the device (docs/FEDERATION.md, "Place").
// The device's own location is read and compared here, on the device; it is never sent to a relay. A relay or
// a ministry only ever learns an answer the person chose to give (safe / need help), counted without accounts.
// Location can be faked, so it narrows what may be done, and widens it only together with a second proof that does
// not come from positioning (a beacon or NFC tag in the building, the office network, a check-in at a cordon).
// The decision itself is zenos-decide "place" (formal/ZenosFormal/Federation.lean); this file only measures.
"use strict";

/** Is [lat, lon] inside the polygon [[lat, lon], ...]? (ray casting; the edge counts as outside) */
function inPolygon(pt, poly) {
  const [y, x] = pt; let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [yi, xi] = poly[i], [yj, xj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** An alert's area: any of its polygons, or the device's municipality code among its codes. */
function inArea(pt, area, myCode) {
  if (pt && (area.polygons || []).some((p) => inPolygon(pt, p))) return true;
  return !!myCode && (area.codes || []).includes(myCode);
}

/** A reading is used only when it is recent and precise enough; otherwise it counts as "not inside". */
function usable(fix, now = Date.now(), maxAgeMs = 120e3, maxErrM = 200) {
  return !!fix && Number.isFinite(fix.lat) && Number.isFinite(fix.lon) && now - fix.t <= maxAgeMs && fix.accuracy <= maxErrM;
}

/** The request for zenos-decide "place", from what the device measured and what the content requires. */
function placeRequest({ baseAllow, level, zone, fix, proofInside, abroad, closeAbroadFrom = 3, emergency = false, emergencyShare = false, now }) {
  const gps = zone ? usable(fix, now) && inPolygon([fix.lat, fix.lon], zone) : false;
  return { op: "place", base_allow: !!baseAllow, level: Number(level) || 0, zone_required: !!zone, gps_inside: gps,
           proof_inside: !!proofInside, abroad: !!abroad, close_abroad_from: closeAbroadFrom, emergency: !!emergency,
           emergency_share: !!emergencyShare };
}

module.exports = { inPolygon, inArea, usable, placeRequest };

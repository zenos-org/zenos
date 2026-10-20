'use strict'
// ZENOS storage: automatic repair of missing shards.
//
// The erasure code runs over ciphertext, so rebuilding a shard needs no key. A repairing node gathers
// k shards, rebuilds the ciphertext, re-encodes it and hands out only the missing shards. It never sees
// the plaintext.
//
// peers: [{ label, publicKey, clearance, zone, request(header, body) }] (the node itself included)
// Targets follow the placement rules (lib/policy.js): cleared nodes only, at most n-k shards per zone.

const crypto = require('crypto')
const rs = require('./rs')
const { eligible, zoneCap } = require('./policy')

const sha256hex = b => crypto.createHash('sha256').update(b).digest('hex')

// Order of the nodes for one file (rendezvous hashing)
function rank (fileId, peers) {
  const score = p => sha256hex(fileId + p.publicKey)
  return [...peers].sort((a, b) => (score(a) < score(b) ? -1 : 1))
}

// Is this node the repair leader for the file (first in rank)? Every node reaches the same answer,
// so a file is repaired once, not by every node.
function isLeader (fileId, self, peers) {
  const r = rank(fileId, peers)
  return r.length > 0 && r[0].publicKey === self.publicKey
}

async function survey (fileId, peers) {
  const holders = new Map() // index -> [peer]
  const perPeer = new Map() // publicKey -> Set(index), null when the peer did not answer
  await Promise.all(peers.map(async p => {
    try {
      const { header } = await p.request({ op: 'list_shards', fileId })
      perPeer.set(p.publicKey, new Set(header.indices))
      for (const i of header.indices) {
        if (!holders.has(i)) holders.set(i, [])
        holders.get(i).push(p)
      }
    } catch { perPeer.set(p.publicKey, null) }
  }))
  return { holders, perPeer }
}

// With `self`, returns null unless this node leads the repair among the nodes that hold shards
// (a node that just joined has no manifest and cannot repair).
async function repairFile (manifestBuf, peers, { log: rawLog = () => {}, self = null } = {}) {
  const m = JSON.parse(manifestBuf)
  const tag = `${m.fileId.slice(0, 8)}`
  const log = s => rawLog(`${tag} ${s.trim()}`)
  const report = { fileId: m.fileId, missing: [], rebuilt: [], copied: [], skipped: null }
  const { holders, perPeer } = await survey(m.fileId, peers)
  const alive = peers.filter(p => perPeer.get(p.publicKey) !== null)
  if (self) {
    const holding = alive.filter(p => perPeer.get(p.publicKey).size > 0)
    if (holding.length && !isLeader(m.fileId, self, holding)) return null
  }

  const load = p => (perPeer.get(p.publicKey) || new Set()).size
  const cap = zoneCap(m.k, m.n)
  const zoneIndices = zone => {
    const set = new Set()
    for (const p of alive) if (p.zone === zone) for (const i of (perPeer.get(p.publicKey) || [])) set.add(i)
    return set
  }
  const zoneOk = (p, i) => {
    const set = zoneIndices(p.zone)
    return set.has(i) || set.size < cap
  }
  const placeable = alive.filter(p => eligible(p, m.level))
  const pickTarget = i => {
    const cands = rank(m.fileId, placeable).filter(p => zoneOk(p, i) && !(perPeer.get(p.publicKey) || new Set()).has(i))
    cands.sort((a, b) => load(a) - load(b))
    return cands[0]
  }
  const assign = (p, i) => {
    if (!perPeer.get(p.publicKey)) perPeer.set(p.publicKey, new Set())
    perPeer.get(p.publicKey).add(i)
  }

  // 1) rebuild missing shards
  for (let i = 0; i < m.n; i++) if (!holders.has(i)) report.missing.push(i)
  if (report.missing.length) {
    const have = new Map()
    for (const [i, hs] of holders) {
      if (have.size >= m.k) break
      for (const h of hs) {
        try {
          const { body } = await h.request({ op: 'get_shard', fileId: m.fileId, index: i })
          if (sha256hex(body) === m.shardHashes[i]) { have.set(i, body); break }
          log(`shard #${i} on ${h.label} does not match its hash: not used`)
        } catch {}
      }
    }
    if (have.size < m.k) {
      report.skipped = `only ${have.size}/${m.k} good shards: cannot rebuild`
      log(report.skipped)
      return report
    }
    const blob = rs.decode(have, m.k, m.n, m.length) // still ciphertext; no key involved
    const all = rs.encode(blob, m.k, m.n)
    for (const i of report.missing) {
      if (sha256hex(all[i]) !== m.shardHashes[i]) throw new Error(`rebuilt shard #${i} does not match the manifest`)
      const target = pickTarget(i)
      if (!target) {
        log(`shard #${i}: no node cleared for ${m.level} with room in its zone (${cap} per zone); waiting`)
        report.skipped = report.skipped || 'no target meets the placement rules'
        continue
      }
      await target.request({ op: 'put_manifest' }, manifestBuf)
      await target.request({ op: 'put_shard', fileId: m.fileId, index: i }, all[i])
      assign(target, i)
      report.rebuilt.push({ index: i, node: target.label })
      log(`shard #${i} rebuilt on ${target.label}`)
    }
  }

  // 2) spread doubled-up shards to empty nodes, one at a time from the most loaded node, so losing any
  //    one node costs fewer shards. Originals are never deleted (deleting is a way in for tampering).
  const soleHolder = i => {
    const hs = (holders.get(i) || []).filter(h => perPeer.get(h.publicKey) !== null)
    return hs.length === 1 ? hs[0] : null
  }
  for (;;) {
    const heavy = alive
      .map(p => ({ p, mine: [...(perPeer.get(p.publicKey) || [])].filter(i => soleHolder(i) === p) }))
      .filter(x => x.mine.length > 1)
      .sort((a, b) => b.mine.length - a.mine.length)
    let move = null
    for (const { p: from, mine } of heavy) {
      for (const i of mine) {
        const empty = rank(m.fileId, placeable).find(p => load(p) === 0 && zoneOk(p, i))
        if (empty) { move = { from, i, empty }; break }
      }
      if (move) break
    }
    if (!move) break
    const { from, i, empty } = move
    try {
      const { body } = await from.request({ op: 'get_shard', fileId: m.fileId, index: i })
      if (sha256hex(body) !== m.shardHashes[i]) break
      await empty.request({ op: 'put_manifest' }, manifestBuf)
      await empty.request({ op: 'put_shard', fileId: m.fileId, index: i }, body)
      assign(empty, i)
      holders.get(i).push(empty)
      report.copied.push({ index: i, from: from.label, node: empty.label })
      log(`shard #${i} copied from ${from.label} to ${empty.label} (spreading)`)
    } catch { break }
  }
  return report
}

module.exports = { repairFile, isLeader, rank }

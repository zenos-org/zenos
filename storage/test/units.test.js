'use strict'
// Erasure code, sealing and certificates: no network.
const test = require('node:test')
const assert = require('node:assert')
const crypto = require('crypto')
const rs = require('../lib/rs')
const { seal, open, verifyManifest, checkManifest, shardOk } = require('../lib/seal')
const policy = require('../lib/policy')

function subsets (n, k) {
  const out = []
  const walk = (start, acc) => {
    if (acc.length === k) return out.push([...acc])
    for (let i = start; i < n; i++) walk(i + 1, [...acc, i])
  }
  walk(0, [])
  return out
}

test('any k of n shards rebuild the data', () => {
  for (const [k, n] of [[3, 5], [2, 4], [4, 7]]) {
    const data = crypto.randomBytes(1000 + k * 13)
    const shards = rs.encode(data, k, n)
    for (const s of subsets(n, k)) {
      const m = new Map(s.map(i => [i, shards[i]]))
      assert.ok(rs.decode(m, k, n, data.length).equals(data), `k=${k} n=${n} subset ${s}`)
    }
  }
})

test('fewer than k shards is refused', () => {
  const shards = rs.encode(Buffer.from('hello world'), 3, 5)
  assert.throws(() => rs.decode(new Map([[0, shards[0]], [4, shards[4]]]), 3, 5, 11))
})

test('seal and open round trip; the capability pins the manifest', () => {
  const pt = crypto.randomBytes(5000)
  const { capability, manifest, manifestBuf, shards } = seal(pt, { level: 'L3', name: 'x' })
  assert.strictEqual(manifest.level, 'L3')
  checkManifest(manifestBuf)
  verifyManifest(capability, manifestBuf)
  const m2 = Buffer.from(manifestBuf.toString().replace('"L3"', '"L1"'))
  assert.throws(() => verifyManifest(capability, m2), /altered/)
  const got = new Map([[1, shards[1]], [3, shards[3]], [4, shards[4]]])
  assert.ok(open(capability, manifest, got).equals(pt))
})

test('a changed shard is caught by its hash, and by the cipher if it slipped through', () => {
  const pt = Buffer.from('sealed contents')
  const { capability, manifest, shards } = seal(pt)
  const bad = Buffer.from(shards[0]); bad[0] ^= 1
  assert.strictEqual(shardOk(manifest, 0, bad), false)
  assert.throws(() => open(capability, manifest, new Map([[0, bad], [1, shards[1]], [2, shards[2]]])))
})

test('certificates: role, key binding, forged signature', () => {
  const admin = policy.createAdminKey()
  const other = policy.createAdminKey()
  const key = crypto.randomBytes(32).toString('hex')
  const c = policy.signCert(admin.privateJwk, { key, role: 'client', clearance: 'L2', zone: 'Site A' })
  assert.deepStrictEqual(policy.verifyCert(c, admin.publicKey, key), { role: 'client', clearance: 'L2', zone: 'Site A' })
  assert.strictEqual(policy.verifyCert(c, admin.publicKey, crypto.randomBytes(32).toString('hex')), null) // another peer's key
  assert.strictEqual(policy.verifyCert(c, other.publicKey, key), null) // another administrator
  assert.strictEqual(policy.verifyCert({ ...c, clearance: 'L5' }, admin.publicKey, key), null) // edited
  const t = policy.resolveTrust({ cert: c }, key, admin.publicKey)
  assert.ok(t.certified)
  assert.strictEqual(policy.mayAccess(t, 'L2', admin.publicKey), true)
  assert.strictEqual(policy.mayAccess(t, 'L3', admin.publicKey), false)
  assert.strictEqual(policy.mayAccess(policy.resolveTrust({}, key, admin.publicKey), 'L1', admin.publicKey), false)
})

test('placement: only cleared nodes, never more than n-k shards per zone, never on a client', () => {
  const peers = []
  for (let i = 0; i < 6; i++) peers.push({ publicKey: crypto.randomBytes(32).toString('hex'), label: 'n' + i, role: 'node', zone: 'Z' + (i % 3), clearance: i < 5 ? 'L4' : 'L1' })
  peers.push({ publicKey: crypto.randomBytes(32).toString('hex'), label: 'pc', role: 'client', zone: 'Z9', clearance: 'L5' })
  const { targets } = policy.planPlacement({ fileId: 'a'.repeat(32), k: 3, n: 5, level: 'L4' }, peers)
  assert.strictEqual(targets.length, 5)
  for (const t of targets) assert.ok(t.role === 'node' && t.clearance === 'L4')
  const perZone = {}
  for (const t of targets) perZone[t.zone] = (perZone[t.zone] || 0) + 1
  for (const z of Object.values(perZone)) assert.ok(z <= 2)
  assert.throws(() => policy.planPlacement({ fileId: 'b'.repeat(32), k: 3, n: 5, level: 'L5' }, peers), /no storage node/)
})

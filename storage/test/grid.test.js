'use strict'
// A certified grid on this machine: own bootstrap, six storage nodes, PCs with and without certificates.
const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const crypto = require('crypto')
const DHT = require('hyperdht')
const { StorageNode } = require('../lib/node')
const { ZenosClient } = require('../lib/client')
const { createAdminKey, signCert } = require('../lib/policy')

const HOST = '127.0.0.1'
const sleep = ms => new Promise(r => setTimeout(r, ms))

test('certified grid', { timeout: 240000 }, async t => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'zenos-grid-'))
  const port = 40000 + Math.floor(Math.random() * 20000)
  const boot = DHT.bootstrapper(port, HOST)
  await boot.ready()
  const bs = [`${HOST}:${port}`]
  const extra = []
  for (let i = 0; i < 2; i++) {
    const n = new DHT({ ephemeral: false, firewalled: false, bootstrap: bs, host: HOST })
    await n.fullyBootstrapped()
    extra.push(n)
  }
  const dht = () => new DHT({ bootstrap: bs, host: HOST })
  const admin = createAdminKey()
  const grid = 'test-' + crypto.randomBytes(4).toString('hex')

  // nodes A-E cleared for L4, one per zone; node F only for L2
  const specs = [['A', 'L4'], ['B', 'L4'], ['C', 'L4'], ['D', 'L4'], ['E', 'L4'], ['F', 'L2']]
  const nodes = {}
  for (const [z, lvl] of specs) {
    const dir = path.join(tmp, 'node-' + z)
    fs.mkdirSync(dir)
    const seed = crypto.randomBytes(32)
    fs.writeFileSync(path.join(dir, 'node.seed'), seed)
    const key = DHT.keyPair(seed).publicKey.toString('hex')
    const cert = signCert(admin.privateJwk, { key, role: 'node', clearance: lvl, zone: 'Zone ' + z })
    nodes[z] = await new StorageNode({ dir, grid, label: 'Node ' + z, dht: dht(), adminKey: admin.publicKey, cert, repairIntervalMs: 0 }).start()
  }
  const client = async (clearance, { certified = true, role = 'client' } = {}) => {
    const seed = crypto.randomBytes(32)
    const key = DHT.keyPair(seed).publicKey.toString('hex')
    const cert = certified ? signCert(admin.privateJwk, { key, role, clearance, zone: 'Office' }) : undefined
    return new ZenosClient({ grid, dht: dht(), adminKey: admin.publicKey, seed, cert }).connect({ minPeers: 6, timeoutMs: 60000 })
  }
  const pcs = []
  const pc3 = await client('L3'); pcs.push(pc3)
  const data = crypto.randomBytes(200000)
  let cap, fileId

  try {
    await t.test('an L3 PC stores an L3 file: five shards on nodes cleared for L3, none on the L2 node', async () => {
      const r = await pc3.put(data, { level: 'L3', k: 3, n: 5, name: 'opaque-id' })
      cap = r.capability; fileId = r.fileId
      assert.strictEqual(r.stored, 5)
      assert.ok(r.placement.every(p => p.node !== 'Node F'))
      assert.ok(!fs.existsSync(path.join(tmp, 'node-F', 'files', fileId)))
    })

    await t.test('an L3 PC cannot store above its clearance', async () => {
      await assert.rejects(pc3.put(Buffer.from('x'), { level: 'L4' }), /k shards|not cleared/)
    })

    await t.test('an L1 PC with the capability is still refused', async () => {
      const pc1 = await client('L1'); pcs.push(pc1)
      await assert.rejects(pc1.get(cap), /not cleared|no node holds/)
    })

    await t.test('a PC without a certificate gets nothing', async () => {
      const stranger = await client('L5', { certified: false }); pcs.push(stranger)
      await assert.rejects(stranger.get(cap), /no node holds/)
      await assert.rejects(stranger.put(Buffer.from('x'), { level: 'L1' }), /k shards|certificate/)
    })

    await t.test('a client certificate cannot pose as a storage node', async () => {
      const seed = crypto.randomBytes(32)
      const key = DHT.keyPair(seed).publicKey.toString('hex')
      const cert = signCert(admin.privateJwk, { key, role: 'client', clearance: 'L5', zone: 'Zone X' })
      const dir = path.join(tmp, 'fake')
      fs.mkdirSync(dir)
      fs.writeFileSync(path.join(dir, 'node.seed'), seed)
      const fake = await new StorageNode({ dir, grid, label: 'Fake', dht: dht(), adminKey: admin.publicKey, cert, repairIntervalMs: 0 }).start()
      assert.strictEqual(fake.trust.certified, false)
      await sleep(3000)
      assert.ok(!pc3.livePeers().some(p => p.label === 'Fake'))
      await fake.stop()
    })

    await t.test('restores with two nodes down', async () => {
      const holders = await pc3.locate(fileId)
      const down = [...new Set([...holders.values()].flat())].slice(0, 2).map(l => l.split(' ')[1])
      for (const z of down) { await nodes[z].stop(); delete nodes[z] }
      await sleep(2000)
      const r = await pc3.get(cap)
      assert.ok(r.data.equals(data))
    })

    await t.test('a shard altered on disk is never used: with only k shards left the restore stops', async () => {
      // two nodes are down, so exactly three shards remain; alter one of them
      const z = Object.keys(nodes).find(k => k !== 'F' && fs.existsSync(path.join(tmp, 'node-' + k, 'files', fileId)))
      const dir = path.join(tmp, 'node-' + z, 'files', fileId)
      const shard = fs.readdirSync(dir).find(f => f.endsWith('.shard'))
      const p = path.join(dir, shard)
      const good = fs.readFileSync(p)
      const bad = Buffer.from(good); bad[10] ^= 0xff
      fs.writeFileSync(p, bad)
      await assert.rejects(pc3.get(cap), /not enough shards to restore \(2\/3\)/)
      fs.writeFileSync(p, good)
      assert.ok((await pc3.get(cap)).data.equals(data))
    })

    await t.test('a revoked PC is refused everywhere once the list reaches one node', async () => {
      const { signRevocations } = require('../lib/policy')
      const list = signRevocations(admin.privateJwk, [pc3.publicKey])
      const live = Object.values(nodes)
      assert.ok(live[0].adoptRevocations(list))
      for (let round = 0; round < 3; round++) {          // peer exchange (normally every repair interval)
        for (const n of live) for (const peer of n.peers.values()) await n._exchange(peer)
      }
      assert.ok(live.every(n => n.revocations && n.revocations.revoked.has(pc3.publicKey)))
      await assert.rejects(pc3.get(cap), /no node holds|not cleared/)
      assert.ok(fs.existsSync(path.join(live[1].dir, 'revocations.json')))   // kept across restarts
    })
  } finally {
    for (const pc of pcs) await pc.close().catch(() => {})
    for (const n of Object.values(nodes)) await n.stop().catch(() => {})
    for (const n of extra) await n.destroy()
    await boot.destroy()
    fs.rmSync(tmp, { recursive: true, force: true })
  }
})

test('repair rebuilds a lost shard without the key', { timeout: 180000 }, async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'zenos-repair-'))
  const port = 40000 + Math.floor(Math.random() * 20000)
  const boot = DHT.bootstrapper(port, HOST)
  await boot.ready()
  const bs = [`${HOST}:${port}`]
  const extra = []
  for (let i = 0; i < 2; i++) {
    const n = new DHT({ ephemeral: false, firewalled: false, bootstrap: bs, host: HOST })
    await n.fullyBootstrapped()
    extra.push(n)
  }
  const dht = () => new DHT({ bootstrap: bs, host: HOST })
  const admin = createAdminKey()
  const grid = 'repair-' + crypto.randomBytes(4).toString('hex')
  const nodes = []
  try {
    for (const z of ['A', 'B', 'C', 'D', 'E', 'F']) {
      const dir = path.join(tmp, z)
      fs.mkdirSync(dir)
      const seed = crypto.randomBytes(32)
      fs.writeFileSync(path.join(dir, 'node.seed'), seed)
      const cert = signCert(admin.privateJwk, { key: DHT.keyPair(seed).publicKey.toString('hex'), role: 'node', clearance: 'L4', zone: 'Zone ' + z })
      nodes.push(await new StorageNode({ dir, grid, label: z, dht: dht(), adminKey: admin.publicKey, cert, repairIntervalMs: 0 }).start())
    }
    const seed = crypto.randomBytes(32)
    const cert = signCert(admin.privateJwk, { key: DHT.keyPair(seed).publicKey.toString('hex'), role: 'client', clearance: 'L4', zone: 'Office' })
    const pc = await new ZenosClient({ grid, dht: dht(), adminKey: admin.publicKey, seed, cert }).connect({ minPeers: 6, timeoutMs: 60000 })
    const data = crypto.randomBytes(50000)
    const r = await pc.put(data, { level: 'L2' })
    for (let i = 0; i < 60 && nodes.some(n => n.peers.size < 5); i++) await sleep(500) // nodes know each other
    const victim = nodes.find(n => fs.existsSync(path.join(n.dir, 'files', r.fileId)))
    const vdir = path.join(victim.dir, 'files', r.fileId)
    for (const f of fs.readdirSync(vdir)) if (f.endsWith('.shard')) fs.unlinkSync(path.join(vdir, f))
    const reports = []
    for (const n of nodes) reports.push(...await n.repairAll())
    assert.ok(reports.some(x => x.rebuilt.length === 1), JSON.stringify(reports))
    const holders = await pc.locate(r.fileId)
    assert.strictEqual(holders.size, 5)
    assert.ok((await pc.get(r.capability)).data.equals(data))
    await pc.close()
  } finally {
    for (const n of nodes) await n.stop().catch(() => {})
    for (const n of extra) await n.destroy()
    await boot.destroy()
    fs.rmSync(tmp, { recursive: true, force: true })
  }
})

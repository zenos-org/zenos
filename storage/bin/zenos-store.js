#!/usr/bin/env node
'use strict'
// ZENOS storage layer
//
//   zenos-store admin-init --out admin.json            create the grid administrator key (keep it off the grid)
//   zenos-store node-id --dir <store>                  create a node key and print it (to be certified)
//   zenos-store client-id --dir <dir>                  create a client (PC) key and print it (to be certified)
//   zenos-store certify --admin-file admin.json --key <public key> --role node|client --clearance L4 --zone "Site A" --out cert.json
//                                                      sign a certificate: role, highest level, zone
//   zenos-store bootstrap --host <IP> [--port 49737]   run the grid's own bootstrap (DHT entry point)
//   zenos-store node --dir <store> --cert cert.json [--label NAME] [--repair 60] [--max-bytes N]
//                                                      run a storage node (checks and repairs every --repair seconds)
//   zenos-store put <file> [--level L3] [--k 3] [--n 5] [--name ID]
//                                                      seal and spread a file; prints the capability
//   zenos-store get <capability> --out <file>          gather and restore (--cap-stdin reads the capability from stdin)
//   zenos-store status                                 the nodes this client reaches, and their certificates
//   put, get and status take --json; on a certified grid they need --id-dir and --cert (the client's identity)
//
// Common: --grid NAME (only peers of the same grid name meet)
//         --bootstrap IP:port,... (the grid's own bootstrap; required on a certified grid)
//         --host IP (address this machine uses on the LAN)
//         --admin KEY (the administrator's public key: only certified peers are used or served)
//         --config FILE (a JSON file with any of these options, e.g. /etc/zenos/storage-node.json)

const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const DHT = require('hyperdht')
const { StorageNode } = require('../lib/node')
const { ZenosClient } = require('../lib/client')
const { createAdminKey, signCert } = require('../lib/policy')

const argv = process.argv.slice(2)
const cmd = argv[0]
const pos = []
let opt = {}
const FLAGS = new Set(['json', 'cap-stdin', 'public-dht'])
for (let i = 1; i < argv.length; i++) {
  if (argv[i].startsWith('--')) {
    const k = argv[i].slice(2)
    if (FLAGS.has(k)) opt[k] = true
    else { opt[k] = argv[i + 1]; i++ }
  } else pos.push(argv[i])
}
if (opt.config) {
  const c = JSON.parse(fs.readFileSync(opt.config, 'utf8'))
  const fromFile = {}
  for (const [k, v] of Object.entries(c)) fromFile[k] = Array.isArray(v) ? v.join(',') : (typeof v === 'boolean' ? v : String(v))
  opt = { ...fromFile, ...opt } // the command line wins over the file
}
const out = (obj, human) => { if (opt.json) process.stdout.write(JSON.stringify(obj) + '\n'); else human() }
const stamp = () => new Date().toISOString().slice(0, 19)

function makeDht () {
  if (opt.admin && !opt.bootstrap && !opt['public-dht']) {
    throw new Error('a certified grid runs on its own bootstrap: give --bootstrap IP:port (or --public-dht to use the public network on purpose)')
  }
  if (!opt.bootstrap && !opt.host) return undefined
  const bootstrap = opt.bootstrap ? String(opt.bootstrap).split(',').map(s => s.trim()) : undefined
  return new DHT({ bootstrap, ...(opt.host ? { host: opt.host } : {}) })
}

function seedFile (dir, name) {
  dir = path.resolve(dir)
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 })
  const f = path.join(dir, name)
  if (!fs.existsSync(f)) fs.writeFileSync(f, crypto.randomBytes(32), { mode: 0o600 })
  return fs.readFileSync(f)
}

function identity () {
  const id = {}
  if (opt['id-dir']) id.seed = seedFile(opt['id-dir'], 'client.seed')
  if (opt.cert) id.cert = JSON.parse(fs.readFileSync(opt.cert, 'utf8'))
  if (opt.admin && !(id.seed && id.cert)) throw new Error('a certified grid needs this client\'s identity: --id-dir and --cert')
  return id
}

const grid = opt.grid || 'default'

async function main () {
  switch (cmd) {
    case 'admin-init': {
      const file = opt.out || 'admin.json'
      if (fs.existsSync(file)) throw new Error(`${file} already exists (not overwritten)`)
      const a = createAdminKey()
      fs.writeFileSync(file, JSON.stringify(a, null, 2), { mode: 0o600 })
      console.log(`administrator key written to ${file} (it holds the private key: keep it off the grid)`)
      console.log(`administrator public key (every node and PC uses it as --admin):\n${a.publicKey}`)
      break
    }

    case 'node-id':
    case 'client-id': {
      if (!opt.dir) throw new Error('give --dir <folder>')
      const seed = seedFile(opt.dir, cmd === 'node-id' ? 'node.seed' : 'client.seed')
      console.log(DHT.keyPair(seed).publicKey.toString('hex'))
      break
    }

    case 'certify': {
      const key = opt.key || opt.node
      if (!opt['admin-file'] || !key || !opt.clearance || !opt.zone) {
        throw new Error('usage: zenos-store certify --admin-file admin.json --key <public key> --role node|client --clearance L4 --zone "Site A" --out cert.json')
      }
      const a = JSON.parse(fs.readFileSync(opt['admin-file'], 'utf8'))
      const cert = signCert(a.privateJwk, { key, role: opt.role || 'node', clearance: opt.clearance, zone: opt.zone })
      const file = opt.out || 'cert.json'
      fs.writeFileSync(file, JSON.stringify(cert, null, 2))
      console.log(`certificate written to ${file} (${cert.role} ${key.slice(0, 16)}…, up to ${cert.clearance}, zone ${cert.zone})`)
      break
    }

    case 'bootstrap': {
      if (!opt.host) throw new Error('give --host <this machine\'s IP>')
      const port = Number(opt.port || 49737)
      const first = DHT.bootstrapper(port, opt.host)
      await first.ready()
      const bs = [`${opt.host}:${port}`]
      const extra = [] // two resident DHT nodes so the routing table works
      for (let i = 0; i < 2; i++) {
        const n = new DHT({ ephemeral: false, firewalled: false, bootstrap: bs, host: opt.host })
        await n.fullyBootstrapped()
        extra.push(n)
      }
      console.log(`${stamp()} bootstrap running at ${bs[0]} (give every node and PC --bootstrap ${bs[0]})`)
      const quit = async () => { for (const n of extra) await n.destroy(); await first.destroy(); process.exit(0) }
      process.once('SIGINT', quit)
      process.once('SIGTERM', quit)
      break
    }

    case 'node': {
      if (!opt.dir) throw new Error('give --dir <storage folder>')
      const repairSec = opt.repair === undefined ? 60 : Number(opt.repair)
      // no certificate yet: the node starts, prints its key for the administrator, and holds nothing
      const cert = opt.cert && fs.existsSync(opt.cert) ? JSON.parse(fs.readFileSync(opt.cert, 'utf8')) : undefined
      if (opt.cert && !cert) console.log(`${stamp()} ${opt.cert} not found: certify the key below, put the certificate there and restart`)
      if (opt.cert && !opt.admin) throw new Error('--cert needs --admin <administrator public key>')
      const node = await new StorageNode({
        dir: path.resolve(opt.dir), grid, label: opt.label, dht: makeDht(),
        adminKey: opt.admin, cert, clearance: opt.clearance || 'L5', zone: opt.zone,
        repairIntervalMs: repairSec * 1000, maxBytes: Number(opt['max-bytes'] || 0),
        log: s => console.log(`${stamp()} ${s}`)
      }).start()
      const how = node.trust.certified ? 'certified' : opt.admin ? 'certificate INVALID: holds nothing' : 'self-declared, development only'
      console.log(`${stamp()} storage node ${node.label} on grid ${grid}`)
      console.log(`  key ${node.publicKey}`)
      console.log(`  store ${node.dir}${node.maxBytes ? ` (limit ${node.maxBytes} bytes)` : ''}`)
      console.log(`  up to ${node.trust.clearance}, zone ${node.trust.zone || '-'} (${how})`)
      console.log(`  repair ${repairSec > 0 ? `every ${repairSec} s` : 'off'}`)
      const quit = async () => { await node.stop(); process.exit(0) }
      process.once('SIGINT', quit)
      process.once('SIGTERM', quit)
      break
    }

    case 'put': {
      if (!pos[0]) throw new Error('give the file to store')
      const k = Number(opt.k || 3)
      const n = Number(opt.n || 5)
      const data = fs.readFileSync(pos[0])
      const client = await new ZenosClient({ grid, dht: makeDht(), adminKey: opt.admin, ...identity() }).connect({ minPeers: Number(opt['min-nodes'] || k), timeoutMs: 20000 })
      try {
        const r = await client.put(data, { k, n, level: opt.level || 'L1', name: opt.name || path.basename(pos[0]) })
        out({ ok: true, capability: r.capability, fileId: r.fileId, k: r.k, n: r.n, stored: r.stored, placement: r.placement, warnings: r.warnings }, () => {
          console.log(`stored (${r.k}-of-${r.n}, ${r.stored} shards)`)
          for (const p of r.placement) console.log(`  shard #${p.index} -> ${p.node} (${p.zone})`)
          for (const w of r.warnings) console.log(`  warning: ${w}`)
          console.log('\ncapability (without it the file cannot be restored; keep it safe):')
          console.log(r.capability)
        })
      } finally { await client.close() }
      break
    }

    case 'get': {
      // the capability holds the key: read it from stdin so other users cannot see it in ps
      const cap = opt['cap-stdin'] ? fs.readFileSync(0, 'utf8').trim() : pos[0]
      if (!cap || !opt.out) throw new Error('usage: zenos-store get <capability> --out <file>')
      const client = await new ZenosClient({ grid, dht: makeDht(), adminKey: opt.admin, ...identity() }).connect({ minPeers: Number(opt['min-nodes'] || 1), timeoutMs: 20000 })
      try {
        await new Promise(r => setTimeout(r, Number(opt.wait || 2000))) // let the other nodes connect
        const r = await client.get(cap, { log: s => { if (!opt.json) console.log(s) } })
        fs.writeFileSync(opt.out, r.data, { mode: 0o600 })
        out({ ok: true, out: opt.out, bytes: r.data.length, level: r.manifest.level, used: r.used, rejected: r.rejected }, () => {
          console.log(`restored ${opt.out} (${r.data.length} bytes, level ${r.manifest.level}, shards ${r.used.join(',')})`)
          if (r.rejected.length) console.log(`  discarded as altered or damaged: ${r.rejected.map(x => `#${x.index}(${x.node})`).join(', ')}`)
        })
      } finally { await client.close() }
      break
    }

    case 'status': {
      const client = await new ZenosClient({ grid, dht: makeDht(), adminKey: opt.admin, ...identity() }).connect({ minPeers: 1, timeoutMs: 15000 })
      try {
        await new Promise(r => setTimeout(r, Number(opt.wait || 2000)))
        const nodes = client.livePeers().map(p => ({ label: p.label, clearance: p.clearance, zone: p.zone, certified: p.certified }))
          .sort((a, b) => (a.label < b.label ? -1 : 1))
        out({ ok: true, nodes }, () => nodes.forEach(x => console.log(`${x.label}: up to ${x.clearance}, zone ${x.zone || '-'}, ${x.certified ? 'certificate valid' : 'no certificate'}`)))
      } finally { await client.close() }
      break
    }

    default: {
      const lines = fs.readFileSync(__filename, 'utf8').split('\n').slice(2)
      console.log(lines.slice(0, lines.findIndex(l => !l.startsWith('//'))).map(l => l.replace(/^\/\/ ?/, '')).join('\n'))
    }
  }
}

main().catch(e => {
  if (opt.json) process.stdout.write(JSON.stringify({ ok: false, error: e.message }) + '\n')
  else console.error('error:', e.message)
  process.exit(1)
})

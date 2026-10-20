'use strict'
// ZENOS storage: encrypt then erasure-code (seal), and the reverse (open).
//
//   1. Encrypt with a fresh AES-256-GCM key per file (any change makes decryption fail)
//   2. Reed-Solomon the ciphertext into n shards (any k rebuild it)
//   3. A manifest records the SHA-256 of every shard
//   4. capability = fileId + key + hash of the manifest
//
// Storage nodes hold only ciphertext shards and the manifest (a list of hashes). The key exists only in
// the capability, so all the nodes together still cannot read the file.
//
// Not yet: issuing capabilities through the request-and-approval flow, bound to issued devices.
// Today ZENOS keeps each capability inside an index entry sealed at the file's level.

const crypto = require('crypto')
const rs = require('./rs')

const sha256 = b => crypto.createHash('sha256').update(b).digest()
const b64u = b => Buffer.from(b).toString('base64url')
const LEVEL = /^L[1-5]$/

function seal (plaintext, { k = 3, n = 5, level = 'L1', name = '' } = {}) {
  if (!LEVEL.test(level)) throw new Error(`invalid level: ${level}`)
  const key = crypto.randomBytes(32)
  const iv = crypto.randomBytes(12)
  const fileId = crypto.randomBytes(16).toString('hex')

  const c = crypto.createCipheriv('aes-256-gcm', key, iv)
  c.setAAD(Buffer.from(fileId)) // shards cannot be moved under another file id
  const blob = Buffer.concat([iv, c.update(plaintext), c.final(), c.getAuthTag()])

  const shards = rs.encode(blob, k, n)
  const manifest = {
    v: 1,
    fileId,
    level,
    name: String(name).slice(0, 128),
    k,
    n,
    length: blob.length,
    shardHashes: shards.map(s => sha256(s).toString('hex')),
    createdAt: new Date().toISOString()
  }
  const manifestBuf = Buffer.from(JSON.stringify(manifest))
  const capability = ['zenos', '1', fileId, b64u(key), sha256(manifestBuf).toString('hex')].join(':')
  return { capability, manifest, manifestBuf, shards }
}

function parseCapability (cap) {
  const p = String(cap).trim().split(':')
  if (p.length !== 5 || p[0] !== 'zenos' || p[1] !== '1' || !/^[0-9a-f]{32}$/.test(p[2])) throw new Error('malformed capability')
  const key = Buffer.from(p[3], 'base64url')
  if (key.length !== 32) throw new Error('capability key has the wrong length')
  return { fileId: p[2], key, manifestHash: p[4] }
}

// Check a manifest against the capability and return it
function verifyManifest (cap, manifestBuf) {
  const { fileId, manifestHash } = parseCapability(cap)
  if (sha256(manifestBuf).toString('hex') !== manifestHash) throw new Error('manifest has been altered')
  const m = JSON.parse(manifestBuf)
  if (m.fileId !== fileId) throw new Error('manifest belongs to another file')
  return m
}

// Basic shape check for a manifest a node is asked to keep (it cannot check the capability hash)
function checkManifest (manifestBuf) {
  const m = JSON.parse(manifestBuf)
  if (m.v !== 1 || !/^[0-9a-f]{32}$/.test(m.fileId) || !LEVEL.test(m.level)) throw new Error('malformed manifest')
  if (!(Number.isInteger(m.k) && Number.isInteger(m.n) && m.k >= 1 && m.n > m.k && m.n <= 255)) throw new Error('malformed manifest')
  if (!Array.isArray(m.shardHashes) || m.shardHashes.length !== m.n || !m.shardHashes.every(h => /^[0-9a-f]{64}$/.test(h))) throw new Error('malformed manifest')
  if (!(Number.isInteger(m.length) && m.length > 0)) throw new Error('malformed manifest')
  return m
}

// Does a shard match the manifest?
function shardOk (manifest, index, buf) {
  return manifest.shardHashes[index] === sha256(buf).toString('hex')
}

function open (cap, manifest, shardMap) {
  const { fileId, key } = parseCapability(cap)
  const blob = rs.decode(shardMap, manifest.k, manifest.n, manifest.length)
  const iv = blob.subarray(0, 12)
  const tag = blob.subarray(blob.length - 16)
  const d = crypto.createDecipheriv('aes-256-gcm', key, iv)
  d.setAAD(Buffer.from(fileId))
  d.setAuthTag(tag)
  return Buffer.concat([d.update(blob.subarray(12, blob.length - 16)), d.final()])
}

module.exports = { seal, open, parseCapability, verifyManifest, checkManifest, shardOk }

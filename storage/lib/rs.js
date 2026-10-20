'use strict'
// ZENOS storage: Reed-Solomon erasure code (GF(2^8), Cauchy matrix, systematic).
// Any k of the n shards rebuild the data. No external dependencies.

const EXP = new Uint8Array(512)
const LOG = new Uint8Array(256)
;(() => {
  let x = 1
  for (let i = 0; i < 255; i++) {
    EXP[i] = x
    LOG[x] = i
    x <<= 1
    if (x & 0x100) x ^= 0x11d // primitive polynomial x^8+x^4+x^3+x^2+1
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255]
})()

function mul (a, b) {
  if (a === 0 || b === 0) return 0
  return EXP[LOG[a] + LOG[b]]
}
function inv (a) {
  if (a === 0) throw new Error('GF(256): 0 has no inverse')
  return EXP[255 - LOG[a]]
}

// multiplication table per coefficient (speed)
const MUL_TABLE = Array.from({ length: 256 }, (_, c) => {
  const t = new Uint8Array(256)
  for (let v = 0; v < 256; v++) t[v] = mul(c, v)
  return t
})

// Row r (0..n-1) of the encoding matrix: identity for the first k rows, Cauchy below
function matrixRow (r, k) {
  const row = new Uint8Array(k)
  if (r < k) {
    row[r] = 1
  } else {
    for (let j = 0; j < k; j++) row[j] = inv(r ^ j) // x_r = r, y_j = j (distinct because r >= k > j)
  }
  return row
}

function invertMatrix (m) {
  const n = m.length
  const a = m.map((row, i) => {
    const r = new Uint8Array(2 * n)
    r.set(row)
    r[n + i] = 1
    return r
  })
  for (let col = 0; col < n; col++) {
    let p = col
    while (p < n && a[p][col] === 0) p++
    if (p === n) throw new Error('decoding matrix is singular (cannot happen)')
    ;[a[col], a[p]] = [a[p], a[col]]
    const s = inv(a[col][col])
    for (let j = 0; j < 2 * n; j++) a[col][j] = mul(a[col][j], s)
    for (let i = 0; i < n; i++) {
      if (i === col || a[i][col] === 0) continue
      const f = a[i][col]
      for (let j = 0; j < 2 * n; j++) a[i][j] ^= mul(f, a[col][j])
    }
  }
  return a.map(r => r.slice(n))
}

// Encode data (Buffer) into k data shards + (n-k) parity shards
function encode (data, k, n) {
  if (!(k >= 1 && n > k && n <= 255)) throw new Error('k and n out of range (1 <= k < n <= 255)')
  const shardSize = Math.ceil(data.length / k) || 1
  const shards = []
  for (let i = 0; i < k; i++) {
    const s = Buffer.alloc(shardSize)
    const start = i * shardSize
    if (start < data.length) data.copy(s, 0, start, Math.min(data.length, start + shardSize))
    shards.push(s)
  }
  for (let r = k; r < n; r++) {
    const row = matrixRow(r, k)
    const out = Buffer.alloc(shardSize)
    for (let j = 0; j < k; j++) {
      const t = MUL_TABLE[row[j]]
      const src = shards[j]
      for (let b = 0; b < shardSize; b++) out[b] ^= t[src[b]]
    }
    shards.push(out)
  }
  return shards
}

// available: Map<index, Buffer> with at least k shards. Returns the data cut to `length`.
function decode (available, k, n, length) {
  const idx = [...available.keys()].filter(i => i >= 0 && i < n).sort((a, b) => a - b).slice(0, k)
  if (idx.length < k) throw new Error(`not enough shards (${idx.length}/${k})`)
  const shardSize = available.get(idx[0]).length
  if (idx.some(i => available.get(i).length !== shardSize)) throw new Error('shards differ in size')
  if (idx.every((v, i) => v === i)) {
    return Buffer.concat(idx.map(i => available.get(i))).subarray(0, length)
  }
  const decM = invertMatrix(idx.map(r => matrixRow(r, k)))
  const out = []
  for (let i = 0; i < k; i++) {
    const s = Buffer.alloc(shardSize)
    for (let j = 0; j < k; j++) {
      const c = decM[i][j]
      if (c === 0) continue
      const t = MUL_TABLE[c]
      const src = available.get(idx[j])
      for (let b = 0; b < shardSize; b++) s[b] ^= t[src[b]]
    }
    out.push(s)
  }
  return Buffer.concat(out).subarray(0, length)
}

module.exports = { encode, decode }

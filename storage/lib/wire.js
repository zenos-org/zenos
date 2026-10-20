'use strict'
// Messages between peers: [total length 4B][header length 4B][header JSON][binary body]
// The connection itself is encrypted end to end by Hyperswarm (Noise protocol).

const MAX_FRAME = 64 * 1024 * 1024
const MAX_HEADER = 256 * 1024

function frame (header, body = Buffer.alloc(0)) {
  const h = Buffer.from(JSON.stringify(header))
  const out = Buffer.alloc(8 + h.length + body.length)
  out.writeUInt32BE(4 + h.length + body.length, 0)
  out.writeUInt32BE(h.length, 4)
  h.copy(out, 8)
  body.copy(out, 8 + h.length)
  return out
}

// Split the bytes from a socket into frames and call onFrame(header, body)
function reader (socket, onFrame) {
  let buf = Buffer.alloc(0)
  socket.on('data', chunk => {
    buf = buf.length ? Buffer.concat([buf, chunk]) : chunk
    while (buf.length >= 4) {
      const total = buf.readUInt32BE(0)
      if (total > MAX_FRAME || total < 4) { socket.destroy(new Error('frame too large')); return }
      if (buf.length < 4 + total) break
      const hl = buf.readUInt32BE(4)
      if (hl > MAX_HEADER || hl > total - 4) { socket.destroy(new Error('bad frame')); return }
      let header
      try { header = JSON.parse(buf.subarray(8, 8 + hl)) } catch { socket.destroy(); return }
      if (!header || typeof header !== 'object') { socket.destroy(); return }
      const body = Buffer.from(buf.subarray(8 + hl, 4 + total))
      buf = buf.subarray(4 + total)
      onFrame(header, body)
    }
  })
}

// Match requests and answers by id
class Rpc {
  constructor (socket, onRequest) {
    this.socket = socket
    this.pending = new Map()
    this.seq = 0
    this.closed = false
    reader(socket, (h, body) => {
      if (h.re !== undefined) {
        const p = this.pending.get(h.re)
        if (!p) return
        this.pending.delete(h.re)
        clearTimeout(p.timer)
        h.ok ? p.resolve({ header: h, body }) : p.reject(new Error(h.error || 'the other side refused'))
      } else if (onRequest) {
        Promise.resolve()
          .then(() => onRequest(h, body))
          .then(r => this._send({ re: h.id, ok: true, ...(r?.header || {}) }, r?.body))
          .catch(e => this._send({ re: h.id, ok: false, error: String(e.message).slice(0, 300) }))
      }
    })
    const fail = () => {
      this.closed = true
      for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(new Error('connection closed')) }
      this.pending.clear()
    }
    socket.on('close', fail)
    socket.on('error', fail)
  }

  _send (header, body) {
    if (!this.closed) this.socket.write(frame(header, body))
  }

  request (header, body, timeoutMs = 15000) {
    if (this.closed) return Promise.reject(new Error('connection is closed'))
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('no answer (timeout)')) }, timeoutMs)
      this.pending.set(id, { resolve, reject, timer })
      this._send({ ...header, id }, body)
    })
  }
}

module.exports = { Rpc, frame }

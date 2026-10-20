'use strict'
const crypto = require('crypto')
// Peers find each other only within the same grid name (32-byte topic)
const topicFor = grid => crypto.createHash('sha256').update('zenos-grid:v1:' + grid).digest()
module.exports = { topicFor }

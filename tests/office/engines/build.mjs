// bundles zapps.mjs with the apps' own sources. MODS: a node_modules folder holding mammoth, jszip, xlsx,
// @xmldom/xmldom (default: the apps' own node_modules after npm ci).
import { build } from 'esbuild'
import { createRequire } from 'node:module'
const require = createRequire(import.meta.url)
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const here = path.dirname(fileURLToPath(import.meta.url))
const mods = process.env.MODS
await build({
  entryPoints: [path.join(here, 'zapps.mjs')], bundle: true, platform: 'browser', external: ['node:*'], format: 'esm',
  outfile: path.join(here, 'zapps.bundle.mjs'), logLevel: 'warning',
  mainFields: ['browser', 'module', 'main'],  // the apps run the browser builds (mammoth reads {arrayBuffer} there)
  nodePaths: [mods || path.join(here, 'node_modules')],
  banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
  plugins: [{ name: 'zenos-stubs', setup(b) {
    b.onResolve({ filter: /^\.\/(chrome|ribbon|docstyle)$/ }, () => ({ path: path.join(here, 'stubs.js') }))
  } }],
})

// Runs the ZENOS 0.1.x apps' own open/save code (apps/docs/src/docx.ts, apps/sheets/src/xlsx.ts,
// apps/slides/src/pptx.ts) on one file, outside the browser: open the file, then save it, as a person would.
//   node zapps.bundle.mjs IN OUT
// The editors themselves (Univer) are replaced by a stand-in that keeps exactly what the apps hand to them,
// so formulas are not recalculated here (the compatibility check recalculates both files the same way).
import { readFileSync, writeFileSync } from 'node:fs'
import { DOMParser } from '@xmldom/xmldom'
import { openDocxFile, saveDocx } from '../../../apps/docs/src/docx.ts'
import { openXlsxFile, saveXlsx } from '../../../apps/sheets/src/xlsx.ts'
import { importPptx, exportPptx } from '../../../apps/slides/src/pptx.ts'

const [, , IN, OUT] = process.argv
globalThis.DOMParser = DOMParser
let saved = null
globalThis.URL.createObjectURL = (blob) => { saved = blob; return 'blob:zenos' }
globalThis.URL.revokeObjectURL = () => {}
globalThis.document = { createElement: () => ({ click() {}, remove() {} }), body: { appendChild() {} } }
globalThis.setTimeout = (f) => 0

const buf = readFileSync(IN)
const file = { name: IN.split('/').pop(), arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
               text: async () => buf.toString('utf8') }

function univerStub() {
  let doc = null, wb = null
  return {
    createDocument(cfg) { doc = { text: '', name: cfg.title } },
    getActiveDocument() {
      return doc && { setText(t) { doc.text = t }, insertText(_, t) { doc.text = t }, getName() { return doc.name },
                      getBody() { return { dataStream: doc.text.replace(/\n/g, '\r') } } }
    },
    createWorkbook(cfg) { wb = cfg },
    getActiveWorkbook() { return wb && { save() { return wb }, getName() { return wb.name } } },
  }
}

const ext = IN.toLowerCase().split('.').pop()
const api = univerStub()
if (ext === 'docx' || ext === 'doc') { await openDocxFile(api, file); await saveDocx(api) }
else if (ext === 'xlsx' || ext === 'xls') { await openXlsxFile(api, file); saveXlsx(api) }
else if (ext === 'pptx') { const slides = await importPptx(file); await exportPptx(slides) }
else { console.error('not handled by the apps:', ext); process.exit(3) }
if (!saved) { console.error('nothing saved'); process.exit(4) }
writeFileSync(OUT, Buffer.from(await saved.arrayBuffer()))

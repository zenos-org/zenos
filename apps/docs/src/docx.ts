import mammoth from 'mammoth'
import JSZip from 'jszip'
import { ZENOS_DOC_STYLE } from './docstyle'
import { applyDarkChrome } from './chrome'
import { liftRibbonTabs } from './ribbon'

// --- Open a .docx/.txt into a new Univer document (text + paragraphs) ---
export async function openDocxFile(univerAPI: any, file: File) {
  let text = ''
  if (/\.txt$/i.test(file.name)) {
    text = await file.text()
  } else {
    const buf = await file.arrayBuffer()
    const result = await mammoth.extractRawText({ arrayBuffer: buf })
    text = result.value || ''
  }
  text = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n')

  univerAPI.createDocument({ title: file.name.replace(/\.(docx|doc|txt)$/i, ''), documentStyle: ZENOS_DOC_STYLE })
  const doc = univerAPI.getActiveDocument()
  try {
    doc.setText(text)
  } catch (e) {
    try { doc.insertText(0, text) } catch {}
  }
  applyDarkChrome()
  liftRibbonTabs()
}

// --- Read the full plain text of the active document (via body dataStream) ---
function readDocText(doc: any): string {
  let raw = ''
  try {
    const body = doc.getBody ? doc.getBody() : null
    raw = body && body.dataStream ? body.dataStream : ''
  } catch {}
  // Univer data stream: \r = paragraph break, \n = section break. Strip other
  // control/sentinel characters, keep tab/newlines.
  let text = String(raw).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
  return text
}

// --- XML escape for text nodes/attributes ---
function escapeXml(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// A minimal, maximally-compatible .docx package. The `docx` library bundles many
// extra parts (numbering/theme/footnotes/endnotes/settings/fontTable) whose
// relationships Google Docs' importer rejects, so we emit only the three parts a
// valid WordprocessingML package needs. Opens cleanly in Word, Google Docs and
// LibreOffice.
const CONTENT_TYPES =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
  '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
  '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
  '<Default Extension="xml" ContentType="application/xml"/>' +
  '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
  '</Types>'

const ROOT_RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
  '</Relationships>'

function buildDocumentXml(lines: string[]): string {
  const paras = (lines.length ? lines : [''])
    .map((line) =>
      line === ''
        ? '<w:p/>'
        : `<w:p><w:r><w:t xml:space="preserve">${escapeXml(line)}</w:t></w:r></w:p>`,
    )
    .join('')
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
    '<w:body>' +
    paras +
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>' +
    '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>' +
    '</w:sectPr></w:body></w:document>'
  )
}

// --- Save the active Univer document to a .docx download (self-built package) ---
export async function saveDocx(univerAPI: any) {
  const doc = univerAPI.getActiveDocument()
  if (!doc) return
  const text = readDocText(doc)
  const lines = text.split(/\r\n|\r|\n/)
  while (lines.length && lines[lines.length - 1] === '') lines.pop()

  const zip = new JSZip()
  zip.file('[Content_Types].xml', CONTENT_TYPES)
  zip.file('_rels/.rels', ROOT_RELS)
  zip.file('word/document.xml', buildDocumentXml(lines))
  const blob = await zip.generateAsync({
    type: 'blob',
    mimeType:
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  let base = 'ZENOS'
  try { base = doc.getName ? doc.getName() : 'ZENOS' } catch {}
  a.download = (base || 'ZENOS') + '.docx'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(url)
    a.remove()
  }, 1500)
}

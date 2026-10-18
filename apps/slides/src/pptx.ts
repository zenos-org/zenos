import JSZip from 'jszip'
import type { Slide, TBox, Shape, ShapeKind, Img, AnimKind } from './main'

const BASE_W = 1280
const BASE_H = 720
const EMU = 9525 // EMU per pixel (914400 per inch / 96)

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  setTimeout(() => { URL.revokeObjectURL(url); a.remove() }, 1500)
}

function esc(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
const P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
const R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

const RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>' +
  '</Relationships>'

const THEME =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  `<a:theme xmlns:a="${A}" name="ZENOS"><a:themeElements>` +
  '<a:clrScheme name="ZENOS">' +
  '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>' +
  '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>' +
  '<a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>' +
  '<a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>' +
  '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>' +
  '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>' +
  '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>' +
  '</a:clrScheme>' +
  '<a:fontScheme name="ZENOS">' +
  '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>' +
  '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>' +
  '</a:fontScheme>' +
  '<a:fmtScheme name="ZENOS">' +
  '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>' +
  '<a:lnStyleLst><a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>' +
  '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>' +
  '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>' +
  '</a:fmtScheme>' +
  '</a:themeElements></a:theme>'

const MASTER =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  `<p:sldMaster xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}">` +
  '<p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>' +
  '<p:spTree>' +
  '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>' +
  '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
  '</p:spTree></p:cSld>' +
  '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>' +
  '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>' +
  '<p:txStyles>' +
  '<p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="4400" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr></p:titleStyle>' +
  '<p:bodyStyle><a:lvl1pPr algn="l"><a:defRPr sz="1800" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:bodyStyle>' +
  '<p:otherStyle><a:lvl1pPr algn="l"><a:defRPr sz="1800" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:otherStyle>' +
  '</p:txStyles>' +
  '</p:sldMaster>'

const MASTER_RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>' +
  '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>' +
  '</Relationships>'

const LAYOUT =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  `<p:sldLayout xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}" type="blank" preserve="1">` +
  '<p:cSld name="Blank"><p:spTree>' +
  '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>' +
  '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
  '</p:spTree></p:cSld>' +
  '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>' +
  '</p:sldLayout>'

const LAYOUT_RELS =
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>' +
  '</Relationships>'

const ALGN: Record<string, string> = { left: 'l', center: 'ctr', right: 'r', justify: 'just' }

function shapeSp(sh: Shape, id: number): string {
  const x = Math.round(sh.x * EMU)
  const y = Math.round(sh.y * EMU)
  const cx = Math.round(Math.max(1, sh.w) * EMU)
  const cy = Math.round(Math.max(1, sh.h) * EMU)
  const stroke = (sh.stroke || '#111111').replace('#', '')
  const fillXml =
    sh.kind === 'line' || sh.fill === 'none'
      ? '<a:noFill/>'
      : `<a:solidFill><a:srgbClr val="${(sh.fill || '#4472c4').replace('#', '')}"/></a:solidFill>`
  const lnW = Math.max(1, Math.round((sh.strokeW || 0) * EMU))
  const lnXml =
    sh.kind === 'line'
      ? `<a:ln w="${Math.max(1, Math.round((sh.strokeW || 4) * EMU))}"><a:solidFill><a:srgbClr val="${stroke}"/></a:solidFill></a:ln>`
      : sh.strokeW > 0
      ? `<a:ln w="${lnW}"><a:solidFill><a:srgbClr val="${stroke}"/></a:solidFill></a:ln>`
      : ''
  return (
    '<p:sp>' +
    `<p:nvSpPr><p:cNvPr id="${id}" name="Shape ${id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>` +
    `<p:spPr><a:xfrm><a:off x="${x}" y="${y}"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>` +
    `<a:prstGeom prst="${sh.kind}"><a:avLst/></a:prstGeom>${fillXml}${lnXml}</p:spPr>` +
    '<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'
  )
}

function textSp(b: TBox, id: number): string {
  const x = Math.round(b.x * EMU)
  const y = Math.round(b.y * EMU)
  const cx = Math.round(Math.max(1, b.w) * EMU)
  const cy = Math.round(Math.max(1, b.h) * EMU)
  const sz = Math.max(100, Math.round((b.size || 18) * 0.75) * 100)
  const bold = b.bold ? '1' : '0'
  const ital = b.italic ? '1' : '0'
  const color = (b.color || '#111111').replace('#', '')
  const algn = ALGN[b.align] || 'l'
  const lines = (b.text || '').split(/\r\n|\r|\n/)
  const paras = lines
    .map((line) => {
      const lead = (line.match(/^\t*/) || [''])[0].length
      const lvl = Math.min(4, lead)
      const t = line.slice(lead)
      const marL = b.bullet ? 285750 * (lvl + 1) : 0
      const indent = b.bullet ? -285750 : 0
      const bu = b.bullet ? '<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' : '<a:buNone/>'
      const pPr = `<a:pPr marL="${marL}" lvl="${lvl}" indent="${indent}" algn="${algn}">${bu}</a:pPr>`
      const run = t
        ? `<a:r><a:rPr lang="en-US" sz="${sz}" b="${bold}" i="${ital}" dirty="0"><a:solidFill><a:srgbClr val="${color}"/></a:solidFill></a:rPr><a:t>${esc(t)}</a:t></a:r>`
        : `<a:endParaRPr lang="en-US" sz="${sz}"/>`
      return `<a:p>${pPr}${run}</a:p>`
    })
    .join('')
  return (
    '<p:sp>' +
    `<p:nvSpPr><p:cNvPr id="${id}" name="TextBox ${id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>` +
    `<p:spPr><a:xfrm><a:off x="${x}" y="${y}"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>` +
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>' +
    `<p:txBody><a:bodyPr wrap="square" rtlCol="0"/><a:lstStyle/>${paras || '<a:p/>'}</p:txBody></p:sp>`
  )
}

function picSp(im: Img, id: number, rId: string): string {
  const x = Math.round(im.x * EMU)
  const y = Math.round(im.y * EMU)
  const cx = Math.round(Math.max(1, im.w) * EMU)
  const cy = Math.round(Math.max(1, im.h) * EMU)
  return (
    '<p:pic>' +
    `<p:nvPicPr><p:cNvPr id="${id}" name="Picture ${id}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>` +
    `<p:blipFill><a:blip r:embed="${rId}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>` +
    `<p:spPr><a:xfrm><a:off x="${x}" y="${y}"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>` +
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
  )
}

// Click-triggered fade entrance timing for the given shape ids.
function buildTiming(spids: number[]): string {
  if (!spids.length) return ''
  let cid = 100
  const effects = spids
    .map((spid) => {
      const a = cid++, b = cid++, c = cid++, d = cid++, e = cid++
      return (
        `<p:par><p:cTn id="${a}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>` +
        `<p:par><p:cTn id="${b}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>` +
        `<p:par><p:cTn id="${c}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" nodeType="clickEffect"><p:childTnLst>` +
        `<p:set><p:cBhvr><p:cTn id="${d}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="${spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>` +
        `<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="${e}" dur="500"/><p:tgtEl><p:spTgt spid="${spid}"/></p:tgtEl></p:cBhvr></p:animEffect>` +
        `</p:childTnLst></p:cTn></p:par>` +
        `</p:childTnLst></p:cTn></p:par>` +
        `</p:childTnLst></p:cTn></p:par>`
      )
    })
    .join('')
  const bld = spids.map((spid) => `<p:bldP spid="${spid}" grpId="0"/>`).join('')
  return (
    '<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>' +
    '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>' +
    effects +
    '</p:childTnLst></p:cTn>' +
    '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>' +
    '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>' +
    '</p:childTnLst></p:cTn></p:par></p:tnLst>' +
    `<p:bldLst>${bld}</p:bldLst></p:timing>`
  )
}

interface MediaFile { path: string; b64: string }

function buildSlide(slide: Slide, mediaCounter: { n: number }): { xml: string; rels: string; media: MediaFile[] } {
  let id = 2
  const media: MediaFile[] = []
  const relEntries: string[] = []
  const animIds: number[] = []

  const shapeXml = (slide.shapes || [])
    .map((sh) => {
      const myId = id++
      if (sh.anim && sh.anim !== 'none') animIds.push(myId)
      return shapeSp(sh, myId)
    })
    .join('')

  const imgXml = (slide.images || [])
    .map((im) => {
      const myId = id++
      const m = /^data:image\/(png|jpeg|jpg|gif);base64,(.*)$/i.exec(im.src || '')
      const ext = m ? (m[1].toLowerCase() === 'jpeg' ? 'jpg' : m[1].toLowerCase()) : 'png'
      const b64 = m ? m[2] : ''
      mediaCounter.n += 1
      const fname = `image${mediaCounter.n}.${ext}`
      media.push({ path: `ppt/media/${fname}`, b64 })
      const rId = `rId${relEntries.length + 2}`
      relEntries.push(
        `<Relationship Id="${rId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/${fname}"/>`,
      )
      if (im.anim && im.anim !== 'none') animIds.push(myId)
      return picSp(im, myId, rId)
    })
    .join('')

  const textXml = slide.boxes
    .map((b) => {
      const myId = id++
      if (b.anim && b.anim !== 'none') animIds.push(myId)
      return textSp(b, myId)
    })
    .join('')

  const bg = slide.bg
    ? `<p:bg><p:bgPr><a:solidFill><a:srgbClr val="${slide.bg.replace('#', '')}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>`
    : ''

  const timing = buildTiming(animIds)

  const xml =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    `<p:sld xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}">` +
    `<p:cSld>${bg}<p:spTree>` +
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>' +
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>' +
    shapeXml + imgXml + textXml +
    '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>' +
    timing +
    '</p:sld>'

  const rels =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>' +
    relEntries.join('') +
    '</Relationships>'

  return { xml, rels, media }
}

// ---- Export the deck to a .pptx download (self-built minimal package) ----
export async function exportPptx(slides: Slide[]) {
  const data: Slide[] = slides.length ? slides : [{ id: 'x', boxes: [], shapes: [], images: [] }]

  const slideOverrides = data
    .map((_, i) => `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`)
    .join('')
  const contentTypes =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Default Extension="png" ContentType="image/png"/>' +
    '<Default Extension="jpg" ContentType="image/jpeg"/>' +
    '<Default Extension="jpeg" ContentType="image/jpeg"/>' +
    '<Default Extension="gif" ContentType="image/gif"/>' +
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>' +
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>' +
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>' +
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>' +
    slideOverrides +
    '</Types>'

  const sldIds = data.map((_, i) => `<p:sldId id="${256 + i}" r:id="rId${2 + i}"/>`).join('')
  const presentation =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    `<p:presentation xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}">` +
    '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>' +
    `<p:sldIdLst>${sldIds}</p:sldIdLst>` +
    '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>' +
    '<p:notesSz cx="6858000" cy="9144000"/>' +
    '<p:defaultTextStyle>' +
    '<a:defPPr><a:defRPr lang="en-US"/></a:defPPr>' +
    '<a:lvl1pPr algn="l"><a:defRPr sz="1800" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr>' +
    '</p:defaultTextStyle>' +
    '</p:presentation>'

  const presRels =
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>' +
    data.map((_, i) => `<Relationship Id="rId${2 + i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${i + 1}.xml"/>`).join('') +
    '</Relationships>'

  const zip = new JSZip()
  zip.file('[Content_Types].xml', contentTypes)
  zip.file('_rels/.rels', RELS)
  zip.file('ppt/presentation.xml', presentation)
  zip.file('ppt/_rels/presentation.xml.rels', presRels)
  zip.file('ppt/theme/theme1.xml', THEME)
  zip.file('ppt/slideMasters/slideMaster1.xml', MASTER)
  zip.file('ppt/slideMasters/_rels/slideMaster1.xml.rels', MASTER_RELS)
  zip.file('ppt/slideLayouts/slideLayout1.xml', LAYOUT)
  zip.file('ppt/slideLayouts/_rels/slideLayout1.xml.rels', LAYOUT_RELS)

  const mediaCounter = { n: 0 }
  data.forEach((sl, i) => {
    const built = buildSlide(sl, mediaCounter)
    zip.file(`ppt/slides/slide${i + 1}.xml`, built.xml)
    zip.file(`ppt/slides/_rels/slide${i + 1}.xml.rels`, built.rels)
    built.media.forEach((m) => { if (m.b64) zip.file(m.path, m.b64, { base64: true }) })
  })

  const blob = await zip.generateAsync({
    type: 'blob',
    mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  })
  download(blob, 'ZENOS.pptx')
}

// ---- Import a .pptx (text + positions + shapes + images + bg) into slides ----
export async function importPptx(file: File): Promise<Slide[]> {
  const zip = await JSZip.loadAsync(await file.arrayBuffer())
  const names = Object.keys(zip.files)
    .filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n))
    .sort((a, b) => parseInt(a.match(/slide(\d+)/)![1]) - parseInt(b.match(/slide(\d+)/)![1]))

  const uid = () => Math.random().toString(36).slice(2, 9)
  const out: Slide[] = []

  const hex = (el: Element | undefined): string | null => {
    if (!el) return null
    const c = el.getElementsByTagNameNS('*', 'srgbClr')[0]
    const v = c && c.getAttribute('val')
    return v ? '#' + v : null
  }
  const geomOf = (sp: Element) => {
    let x = 120, y = 120, w = 400, h = 200
    const off = sp.getElementsByTagNameNS('*', 'off')[0]
    const ext = sp.getElementsByTagNameNS('*', 'ext')[0]
    if (off && ext) {
      x = Math.round(parseInt(off.getAttribute('x') || '0') / EMU)
      y = Math.round(parseInt(off.getAttribute('y') || '0') / EMU)
      w = Math.round(parseInt(ext.getAttribute('cx') || '0') / EMU)
      h = Math.round(parseInt(ext.getAttribute('cy') || '0') / EMU)
    }
    return { x, y, w, h }
  }

  for (const n of names) {
    const xml = await zip.files[n].async('string')
    const doc = new DOMParser().parseFromString(xml, 'application/xml')
    const boxes: TBox[] = []
    const shapes: Shape[] = []
    const images: Img[] = []

    // slide background
    let bg: string | undefined
    const bgPr = doc.getElementsByTagNameNS('*', 'bgPr')[0]
    if (bgPr) bg = hex(bgPr.getElementsByTagNameNS('*', 'solidFill')[0] as Element | undefined) || undefined

    // rels (for images)
    const relsName = n.replace('ppt/slides/', 'ppt/slides/_rels/') + '.rels'
    const relMap: Record<string, string> = {}
    if (zip.files[relsName]) {
      const relXml = await zip.files[relsName].async('string')
      const relDoc = new DOMParser().parseFromString(relXml, 'application/xml')
      Array.from(relDoc.getElementsByTagNameNS('*', 'Relationship')).forEach((r) => {
        const idr = r.getAttribute('Id')
        const tgt = r.getAttribute('Target')
        if (idr && tgt) relMap[idr] = tgt
      })
    }

    // pictures
    const pics = Array.from(doc.getElementsByTagNameNS('*', 'pic'))
    for (const pic of pics) {
      const g = geomOf(pic)
      const blip = pic.getElementsByTagNameNS('*', 'blip')[0]
      let embed = blip ? (blip.getAttribute('r:embed') || blip.getAttributeNS(R, 'embed')) : null
      let src = ''
      if (embed && relMap[embed]) {
        const tgt = relMap[embed].replace(/^\.\.\//, 'ppt/')
        if (zip.files[tgt]) {
          const b64 = await zip.files[tgt].async('base64')
          const ext = (tgt.match(/\.(\w+)$/) || [, 'png'])[1]!.toLowerCase()
          const mime = ext === 'jpg' ? 'jpeg' : ext
          src = `data:image/${mime};base64,${b64}`
        }
      }
      if (src) {
        images.push({
          id: uid(),
          x: Math.max(0, Math.min(g.x, BASE_W - 10)),
          y: Math.max(0, Math.min(g.y, BASE_H - 10)),
          w: Math.max(10, Math.min(g.w, BASE_W)),
          h: Math.max(10, Math.min(g.h, BASE_H)),
          src,
        })
      }
    }

    // shapes & text
    const sps = Array.from(doc.getElementsByTagNameNS('*', 'sp'))
    sps.forEach((sp) => {
      const pEls = Array.from(sp.getElementsByTagNameNS('*', 'p'))
      const hasBullet = sp.getElementsByTagNameNS('*', 'buChar').length > 0 || sp.getElementsByTagNameNS('*', 'buAutoNum').length > 0
      const lines = pEls.map((p) => {
        const lvl = parseInt((p.getElementsByTagNameNS('*', 'pPr')[0]?.getAttribute('lvl')) || '0') || 0
        const txt = Array.from(p.getElementsByTagNameNS('*', 't')).map((t) => t.textContent || '').join('')
        return '\t'.repeat(Math.min(4, lvl)) + txt
      })
      const text = lines.join('\n').replace(/\n+$/, '')
      const g = geomOf(sp)

      if (text.trim()) {
        let size = 32, bold = false, italic = false
        const rPr = sp.getElementsByTagNameNS('*', 'rPr')[0]
        if (rPr) {
          const sz = rPr.getAttribute('sz')
          if (sz) size = Math.max(10, Math.round((parseInt(sz) / 100) * 96 / 72))
          bold = rPr.getAttribute('b') === '1'
          italic = rPr.getAttribute('i') === '1'
        }
        boxes.push({
          id: uid(),
          x: Math.max(0, Math.min(g.x, BASE_W - 80)),
          y: Math.max(0, Math.min(g.y, BASE_H - 40)),
          w: Math.max(80, Math.min(g.w, BASE_W)),
          h: Math.max(40, Math.min(g.h, BASE_H)),
          text,
          size,
          bold,
          italic,
          color: hex(rPr) || '#111111',
          align: 'left',
          bullet: hasBullet,
        })
        return
      }

      const geom = sp.getElementsByTagNameNS('*', 'prstGeom')[0]
      if (!geom) return
      const prst = geom.getAttribute('prst') || 'rect'
      const kind: ShapeKind = prst === 'ellipse' ? 'ellipse' : prst === 'line' ? 'line' : 'rect'
      const spPr = sp.getElementsByTagNameNS('*', 'spPr')[0]
      const fillEl = spPr ? (spPr.getElementsByTagNameNS('*', 'solidFill')[0] as Element | undefined) : undefined
      const lnEl = sp.getElementsByTagNameNS('*', 'ln')[0] as Element | undefined
      const noFill = spPr ? spPr.getElementsByTagNameNS('*', 'noFill').length > 0 : false
      const fill = kind === 'line' ? 'none' : noFill ? 'none' : hex(fillEl) || '#4472c4'
      const stroke = hex(lnEl) || '#111111'
      let strokeW = 0
      if (lnEl) {
        const lw = lnEl.getAttribute('w')
        if (lw) strokeW = Math.max(1, Math.round(parseInt(lw) / EMU))
      }
      if (kind === 'line' && strokeW === 0) strokeW = 4
      shapes.push({
        id: uid(),
        x: Math.max(0, Math.min(g.x, BASE_W - 10)),
        y: Math.max(0, Math.min(g.y, BASE_H - 10)),
        w: Math.max(4, Math.min(g.w, BASE_W)),
        h: Math.max(kind === 'line' ? 0 : 4, Math.min(g.h, BASE_H)),
        kind,
        fill,
        stroke,
        strokeW,
      })
    })

    out.push({ id: uid(), boxes, shapes, images, bg })
  }

  return out
}

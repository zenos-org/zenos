import './style.css'
import { openAiPanel, openSettings } from './ai'
import { exportPptx, importPptx } from './pptx'

export const BASE_W = 1280
export const BASE_H = 720

export type AnimKind = 'none' | 'fade'
export type ShapeKind = 'rect' | 'ellipse' | 'line'

export interface TBox {
  id: string
  x: number
  y: number
  w: number
  h: number
  text: string
  size: number
  bold: boolean
  italic: boolean
  color: string
  align: 'left' | 'center' | 'right'
  bullet?: boolean
  anim?: AnimKind
}
export interface Shape {
  id: string
  x: number
  y: number
  w: number
  h: number
  kind: ShapeKind
  fill: string
  stroke: string
  strokeW: number
  anim?: AnimKind
}
export interface Img {
  id: string
  x: number
  y: number
  w: number
  h: number
  src: string
  anim?: AnimKind
}
export interface Slide {
  id: string
  boxes: TBox[]
  shapes?: Shape[]
  images?: Img[]
  bg?: string
}

let slides: Slide[] = []
let cur = 0
let selId: string | null = null
let scale = 1

const uid = () => Math.random().toString(36).slice(2, 9)

function defaultSlide(title = 'Click to add title', sub = 'Subtitle'): Slide {
  return {
    id: uid(),
    shapes: [],
    images: [],
    boxes: [
      { id: uid(), x: 120, y: 210, w: 1040, h: 150, text: title, size: 60, bold: true, italic: false, color: '#111111', align: 'center' },
      { id: uid(), x: 120, y: 380, w: 1040, h: 90, text: sub, size: 32, bold: false, italic: false, color: '#555555', align: 'center' },
    ],
  }
}

const $ = (id: string) => document.getElementById(id)!
const slideEl = () => $('slide')
const stageEl = () => $('stage')

function curSlide(): Slide { return slides[cur] }
function shapesOf(s: Slide): Shape[] { if (!s.shapes) s.shapes = []; return s.shapes }
function imagesOf(s: Slide): Img[] { if (!s.images) s.images = []; return s.images }
function selBox(): TBox | undefined { return curSlide().boxes.find((b) => b.id === selId) }
function selShape(): Shape | undefined { return shapesOf(curSlide()).find((s) => s.id === selId) }
function selImg(): Img | undefined { return imagesOf(curSlide()).find((im) => im.id === selId) }
function selAny(): TBox | Shape | Img | undefined { return selBox() || selShape() || selImg() }

// ---------- rendering ----------
function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function applyBoxStyle(el: HTMLElement, b: TBox) {
  el.style.left = b.x + 'px'
  el.style.top = b.y + 'px'
  el.style.width = b.w + 'px'
  el.style.height = b.h + 'px'
  el.style.fontSize = b.size + 'px'
  el.style.fontWeight = b.bold ? '700' : '400'
  el.style.fontStyle = b.italic ? 'italic' : 'normal'
  el.style.color = b.color
  el.style.textAlign = b.align
}

function renderBoxContent(el: HTMLElement, b: TBox) {
  // formatted view (bullets / indentation); editing swaps to raw text
  el.innerHTML = ''
  const lines = (b.text || '').split('\n')
  lines.forEach((line) => {
    const lead = (line.match(/^\t*/) || [''])[0].length
    const t = line.slice(lead)
    const d = document.createElement('div')
    if (b.bullet) {
      d.style.paddingLeft = lead * 24 + 18 + 'px'
      d.style.textIndent = '-18px'
      d.textContent = '• ' + t
    } else {
      d.innerHTML = (escapeHtml(line.replace(/\t/g, '    ')) || '​')
    }
    el.appendChild(d)
  })
}

function applyShapeEl(el: HTMLElement, s: Shape) {
  el.style.left = s.x + 'px'
  el.style.top = s.y + 'px'
  el.style.width = s.w + 'px'
  el.style.height = s.h + 'px'
  if (s.kind === 'line') {
    el.style.background = 'transparent'
    el.style.border = 'none'
    el.style.borderRadius = '0'
    el.innerHTML =
      `<svg width="100%" height="100%" viewBox="0 0 ${Math.max(1, s.w)} ${Math.max(1, s.h)}" preserveAspectRatio="none" style="position:absolute;inset:0;overflow:visible">` +
      `<line x1="0" y1="0" x2="${Math.max(1, s.w)}" y2="${Math.max(1, s.h)}" stroke="${s.stroke}" stroke-width="${s.strokeW}" stroke-linecap="round"/></svg>`
  } else {
    el.innerHTML = ''
    el.style.background = s.fill === 'none' ? 'transparent' : s.fill
    el.style.border = s.strokeW > 0 ? `${s.strokeW}px solid ${s.stroke}` : 'none'
    el.style.borderRadius = s.kind === 'ellipse' ? '50%' : '0'
  }
}

function applyImgEl(el: HTMLImageElement, im: Img) {
  el.style.left = im.x + 'px'
  el.style.top = im.y + 'px'
  el.style.width = im.w + 'px'
  el.style.height = im.h + 'px'
  if (el.src !== im.src) el.src = im.src
}

function fitScale() {
  const st = stageEl()
  const availW = st.clientWidth - 48
  const availH = st.clientHeight - 48
  scale = Math.max(0.1, Math.min(availW / BASE_W, availH / BASE_H))
  const s = slideEl()
  s.style.transform = `scale(${scale})`
  const wrap = $('slidewrap')
  wrap.style.width = BASE_W * scale + 'px'
  wrap.style.height = BASE_H * scale + 'px'
}

function addResizeHandle(host: HTMLElement, elem: { w: number; h: number }, el: HTMLElement) {
  const rh = document.createElement('div')
  rh.className = 'rh'
  attachResize(rh, elem, el)
  host.appendChild(rh)
}

function renderSlide() {
  const s = slideEl()
  s.innerHTML = ''
  const slide = curSlide()
  s.style.background = slide.bg || '#ffffff'
  // shapes
  shapesOf(slide).forEach((sh) => {
    const el = document.createElement('div')
    el.className = 'shape' + (sh.id === selId ? ' sel' : '')
    el.dataset.id = sh.id
    applyShapeEl(el, sh)
    attachDrag(el, sh)
    s.appendChild(el)
    if (sh.id === selId) addResizeHandle(el, sh, el)
  })
  // images
  imagesOf(slide).forEach((im) => {
    const el = document.createElement('img') as HTMLImageElement
    el.className = 'simg' + (im.id === selId ? ' sel' : '')
    el.dataset.id = im.id
    el.draggable = false
    applyImgEl(el, im)
    attachDrag(el, im)
    s.appendChild(el)
    if (im.id === selId) {
      // <img> is a void element; place the resize handle on the slide at its corner
      const rh = document.createElement('div')
      rh.className = 'rh'
      rh.style.left = im.x + im.w - 6 + 'px'
      rh.style.top = im.y + im.h - 6 + 'px'
      rh.style.right = 'auto'
      rh.style.bottom = 'auto'
      attachResize(rh, im, el)
      s.appendChild(rh)
    }
  })
  // text
  slide.boxes.forEach((b) => {
    const el = document.createElement('div')
    el.className = 'tbox' + (b.id === selId ? ' sel' : '')
    el.dataset.id = b.id
    applyBoxStyle(el, b)
    renderBoxContent(el, b)
    attachDrag(el, b)
    attachTextEdit(el, b)
    s.appendChild(el)
    if (b.id === selId) addResizeHandle(el, b, el)
  })
  fitScale()
}

function renderRail() {
  const rail = $('rail')
  rail.innerHTML = ''
  const innerW = rail.clientWidth - 20
  const tScale = (innerW > 0 ? innerW : 166) / BASE_W
  slides.forEach((slide, i) => {
    const t = document.createElement('div')
    t.className = 'thumb' + (i === cur ? ' active' : '')
    const num = document.createElement('div'); num.className = 'num'; num.textContent = String(i + 1)
    const tn = document.createElement('div'); tn.className = 'tn'
    tn.style.transform = `scale(${tScale})`
    tn.style.background = slide.bg || '#ffffff'
    shapesOf(slide).forEach((sh) => {
      const el = document.createElement('div'); el.className = 'shape'; applyShapeEl(el, sh); tn.appendChild(el)
    })
    imagesOf(slide).forEach((im) => {
      const el = document.createElement('img') as HTMLImageElement; el.className = 'simg'; el.draggable = false; applyImgEl(el, im); tn.appendChild(el)
    })
    slide.boxes.forEach((b) => {
      const el = document.createElement('div'); el.className = 'tbox'; applyBoxStyle(el, b); renderBoxContent(el, b); el.style.cursor = 'pointer'; tn.appendChild(el)
    })
    t.appendChild(tn); t.appendChild(num)
    t.addEventListener('click', () => { cur = i; selId = null; render() })
    rail.appendChild(t)
  })
  const add = document.createElement('button')
  add.className = 'addslide'; add.textContent = '+ Add slide'
  add.addEventListener('click', addSlide)
  rail.appendChild(add)
}

function updateToolbar() {
  const b = selBox()
  const sh = selShape()
  const any = selAny()
  ;($('t-size') as HTMLSelectElement).value = b ? String(b.size) : '32'
  ;($('t-color') as HTMLInputElement).value = b ? b.color : '#111111'
  $('t-bold').classList.toggle('on', !!(b && b.bold))
  $('t-italic').classList.toggle('on', !!(b && b.italic))
  $('t-left').classList.toggle('on', !!(b && b.align === 'left'))
  $('t-center').classList.toggle('on', !!(b && b.align === 'center'))
  $('t-right').classList.toggle('on', !!(b && b.align === 'right'))
  $('t-bullet').classList.toggle('on', !!(b && b.bullet))
  const fill = $('t-fill') as HTMLInputElement
  if (sh) fill.value = sh.kind === 'line' ? sh.stroke : (sh.fill === 'none' ? '#4472c4' : sh.fill)
  ;($('t-bg') as HTMLInputElement).value = curSlide().bg || '#ffffff'
  ;($('t-anim') as HTMLSelectElement).value = (any && any.anim) || 'none'
}

function render() { renderSlide(); renderRail(); updateToolbar() }

// ---------- interactions ----------
function attachDrag(el: HTMLElement, elem: { id: string; x: number; y: number }) {
  el.addEventListener('mousedown', (e) => {
    if (el.getAttribute('contenteditable') === 'true') return
    if ((e.target as HTMLElement).classList.contains('rh')) return
    e.preventDefault()
    selId = elem.id
    renderSlide(); renderRail(); updateToolbar()
    const startX = e.clientX, startY = e.clientY
    const ox = elem.x, oy = elem.y
    const move = (ev: MouseEvent) => {
      elem.x = Math.round(ox + (ev.clientX - startX) / scale)
      elem.y = Math.round(oy + (ev.clientY - startY) / scale)
      const live = slideEl().querySelector(`[data-id="${elem.id}"]`) as HTMLElement
      if (live) { live.style.left = elem.x + 'px'; live.style.top = elem.y + 'px' }
    }
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up) }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  })
}

function attachTextEdit(el: HTMLElement, b: TBox) {
  el.addEventListener('dblclick', (e) => {
    e.stopPropagation()
    el.textContent = b.text // raw text for editing (tabs preserved)
    el.setAttribute('contenteditable', 'true')
    el.focus()
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Tab') {
        ev.preventDefault()
        if (ev.shiftKey) {
          // remove one tab before caret if present
          document.execCommand('delete', false)
        } else {
          document.execCommand('insertText', false, '\t')
        }
      }
    }
    el.addEventListener('keydown', onKey)
    el.addEventListener('blur', () => {
      el.removeAttribute('contenteditable')
      b.text = el.innerText.replace(/ /g, ' ')
      el.removeEventListener('keydown', onKey)
      render()
    }, { once: true })
  })
}

function attachResize(rh: HTMLElement, elem: { w: number; h: number; kind?: ShapeKind }, boxEl: HTMLElement) {
  rh.addEventListener('mousedown', (e) => {
    e.preventDefault(); e.stopPropagation()
    const startX = e.clientX, startY = e.clientY
    const ow = elem.w, oh = elem.h
    const isText = (elem as any).text !== undefined
    const minW = isText ? 60 : 12
    const minH = isText ? 36 : 12
    const move = (ev: MouseEvent) => {
      elem.w = Math.max(minW, Math.round(ow + (ev.clientX - startX) / scale))
      elem.h = Math.max(minH, Math.round(oh + (ev.clientY - startY) / scale))
      boxEl.style.width = elem.w + 'px'; boxEl.style.height = elem.h + 'px'
    }
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); render() }
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
  })
}

stageEl().addEventListener('mousedown', (e) => {
  if (e.target === stageEl() || e.target === slideEl() || (e.target as HTMLElement).id === 'slidewrap') {
    selId = null; renderSlide(); renderRail(); updateToolbar()
  }
})

// ---------- actions ----------
function addTextBox() {
  const b: TBox = { id: uid(), x: 300, y: 300, w: 680, h: 120, text: 'Text', size: 32, bold: false, italic: false, color: '#111111', align: 'left' }
  curSlide().boxes.push(b)
  selId = b.id
  render()
}
function addShape(kind: ShapeKind) {
  const base = { id: uid(), x: 440, y: 260, w: 400, h: kind === 'line' ? 0 : 220 }
  const sh: Shape = kind === 'line'
    ? { ...base, w: 400, h: 200, kind, fill: 'none', stroke: '#111111', strokeW: 4 }
    : { ...base, kind, fill: '#4472c4', stroke: '#2f5597', strokeW: 0 }
  shapesOf(curSlide()).push(sh)
  selId = sh.id
  render()
}
function addImageFromDataURL(src: string) {
  const probe = new Image()
  probe.onload = () => {
    const maxW = 520
    const ratio = probe.naturalHeight / probe.naturalWidth || 0.66
    const w = Math.min(maxW, probe.naturalWidth || maxW)
    const h = Math.round(w * ratio)
    const im: Img = { id: uid(), x: Math.round((BASE_W - w) / 2), y: Math.round((BASE_H - h) / 2), w, h, src }
    imagesOf(curSlide()).push(im)
    selId = im.id
    render()
  }
  probe.onerror = () => {
    const im: Img = { id: uid(), x: 400, y: 240, w: 480, h: 320, src }
    imagesOf(curSlide()).push(im); selId = im.id; render()
  }
  probe.src = src
}
function addSlide() { slides.push({ id: uid(), boxes: [], shapes: [], images: [] }); cur = slides.length - 1; selId = null; render() }
function delSlide() {
  if (slides.length <= 1) { slides[0] = { id: uid(), boxes: [], shapes: [], images: [] }; cur = 0; selId = null; render(); return }
  slides.splice(cur, 1)
  if (cur >= slides.length) cur = slides.length - 1
  selId = null; render()
}
function delSel() {
  const slide = curSlide()
  let i = slide.boxes.findIndex((b) => b.id === selId)
  if (i >= 0) { slide.boxes.splice(i, 1); selId = null; render(); return }
  i = shapesOf(slide).findIndex((s) => s.id === selId)
  if (i >= 0) { shapesOf(slide).splice(i, 1); selId = null; render(); return }
  i = imagesOf(slide).findIndex((im) => im.id === selId)
  if (i >= 0) { imagesOf(slide).splice(i, 1); selId = null; render() }
}

function applyToSelBox(fn: (b: TBox) => void) { const b = selBox(); if (b) { fn(b); render() } }
function applyToSelShape(fn: (s: Shape) => void) { const s = selShape(); if (s) { fn(s); render() } }

// ---------- wire toolbar ----------
$('t-addtext').addEventListener('click', addTextBox)
$('t-addrect').addEventListener('click', () => addShape('rect'))
$('t-addellipse').addEventListener('click', () => addShape('ellipse'))
$('t-addline').addEventListener('click', () => addShape('line'))
$('t-addimg').addEventListener('click', () => (imgInput).click())
$('t-addslide').addEventListener('click', addSlide)
$('t-delslide').addEventListener('click', delSlide)
$('t-delbox').addEventListener('click', delSel)
$('t-bold').addEventListener('click', () => applyToSelBox((b) => (b.bold = !b.bold)))
$('t-italic').addEventListener('click', () => applyToSelBox((b) => (b.italic = !b.italic)))
$('t-left').addEventListener('click', () => applyToSelBox((b) => (b.align = 'left')))
$('t-center').addEventListener('click', () => applyToSelBox((b) => (b.align = 'center')))
$('t-right').addEventListener('click', () => applyToSelBox((b) => (b.align = 'right')))
$('t-bullet').addEventListener('click', () => applyToSelBox((b) => (b.bullet = !b.bullet)))
;($('t-size') as HTMLSelectElement).addEventListener('change', (e) => applyToSelBox((b) => (b.size = parseInt((e.target as HTMLSelectElement).value) || 32)))
;($('t-color') as HTMLInputElement).addEventListener('input', (e) => applyToSelBox((b) => (b.color = (e.target as HTMLInputElement).value)))
;($('t-fill') as HTMLInputElement).addEventListener('input', (e) => applyToSelShape((s) => {
  const v = (e.target as HTMLInputElement).value
  if (s.kind === 'line') s.stroke = v
  else s.fill = v
}))
;($('t-bg') as HTMLInputElement).addEventListener('input', (e) => { curSlide().bg = (e.target as HTMLInputElement).value; render() })
;($('t-anim') as HTMLSelectElement).addEventListener('change', (e) => {
  const v = (e.target as HTMLSelectElement).value as AnimKind
  const any = selAny()
  if (any) { any.anim = v; render() }
})

const imgInput = document.createElement('input')
imgInput.type = 'file'
imgInput.accept = 'image/png,image/jpeg,image/gif'
imgInput.style.display = 'none'
document.body.appendChild(imgInput)
imgInput.addEventListener('change', () => {
  const f = imgInput.files && imgInput.files[0]
  if (f) {
    const reader = new FileReader()
    reader.onload = () => addImageFromDataURL(String(reader.result))
    reader.readAsDataURL(f)
    imgInput.value = ''
  }
})

document.addEventListener('keydown', (e) => {
  if ((e.key === 'Delete' || e.key === 'Backspace') && selId) {
    const active = document.activeElement as HTMLElement
    if (active && active.getAttribute('contenteditable') === 'true') return
    delSel()
  }
})

// ---------- ZENOS bar: open/save/ai ----------
const fileInput = $('fileinput') as HTMLInputElement
$('btn-open').addEventListener('click', () => fileInput.click())
fileInput.addEventListener('change', async () => {
  const f = fileInput.files && fileInput.files[0]
  if (f) {
    try {
      const imported = await importPptx(f)
      if (imported.length) { slides = imported; cur = 0; selId = null; render() }
    } catch (err) { console.error('[ZENOS Slides] open failed:', err) }
    fileInput.value = ''
  }
})
$('btn-save').addEventListener('click', async () => {
  try { await exportPptx(slides) } catch (err) { console.error('[ZENOS Slides] save failed:', err) }
})

function getContext(): string {
  const s = curSlide()
  const txt = s.boxes.map((b) => b.text).filter(Boolean).join('\n')
  return 'Slide ' + (cur + 1) + ' / ' + slides.length + ' contents:\n' + txt
}
$('btn-ai').addEventListener('click', () => openAiPanel(getContext))
$('btn-settings').addEventListener('click', () => openSettings())

window.addEventListener('resize', () => fitScale())

// ---------- init ----------
slides = [defaultSlide('ZENOS Slides', 'Presentation')]
render()
;(window as any).__zenosSlides = () => slides

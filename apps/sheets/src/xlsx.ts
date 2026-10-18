import * as XLSX from 'xlsx'
import { applyDarkChrome } from './chrome'
import { liftRibbonTabs } from './ribbon'

// --- Open an .xlsx/.xls/.csv file into a new Univer workbook (values + formulas) ---
export async function openXlsxFile(univerAPI: any, file: File) {
  const buf = await file.arrayBuffer()
  // sheetStubs: a formula saved without a cached value (openpyxl, scripts) is otherwise dropped entirely
  const wb = XLSX.read(new Uint8Array(buf), { type: 'array', cellFormula: true, sheetStubs: true })
  const sheets: Record<string, any> = {}
  const sheetOrder: string[] = []

  wb.SheetNames.forEach((name, i) => {
    const ws = wb.Sheets[name]
    const id = 'sheet-' + i
    sheetOrder.push(id)
    const cellData: Record<number, Record<number, any>> = {}
    let maxR = 0
    let maxC = 0
    if (ws && ws['!ref']) {
      const range = XLSX.utils.decode_range(ws['!ref'])
      for (let r = range.s.r; r <= range.e.r; r++) {
        for (let c = range.s.c; c <= range.e.c; c++) {
          const addr = XLSX.utils.encode_cell({ r, c })
          const cell = (ws as any)[addr]
          if (!cell) continue
          if (!cellData[r]) cellData[r] = {}
          if (cell.f) cellData[r][c] = { f: '=' + String(cell.f) }          // recalculated by the formula engine
          else if (cell.t !== 'z' && cell.v !== undefined && cell.v !== null) cellData[r][c] = { v: cell.v }
          else { if (!Object.keys(cellData[r]).length) delete cellData[r]; continue }
          if (r > maxR) maxR = r
          if (c > maxC) maxC = c
        }
      }
    }
    sheets[id] = {
      id,
      name,
      rowCount: Math.max(maxR + 50, 100),
      columnCount: Math.max(maxC + 10, 26),
      cellData,
    }
  })

  if (sheetOrder.length === 0) throw new Error('empty workbook')

  univerAPI.createWorkbook({
    id: 'wb-' + Date.now(),
    name: file.name.replace(/\.(xlsx|xls|csv)$/i, ''),
    sheetOrder,
    sheets,
  })
  applyDarkChrome()
  liftRibbonTabs()
}

// --- Save the active Univer workbook to an .xlsx download (values/formulas) ---
export function saveXlsx(univerAPI: any) {
  const wb = univerAPI.getActiveWorkbook()
  if (!wb) return
  const snap = wb.save()
  const out = XLSX.utils.book_new()
  const order: string[] = snap.sheetOrder && snap.sheetOrder.length ? snap.sheetOrder : Object.keys(snap.sheets)

  order.forEach((sid) => {
    const s = snap.sheets[sid]
    if (!s) return
    const cd = s.cellData || {}
    // cell by cell, so formulas stay formulas (with their last computed value) instead of becoming text
    const ws: any = {}
    let maxR = 0, maxC = 0
    for (const rk of Object.keys(cd)) {
      const r = Number(rk)
      for (const ck of Object.keys(cd[rk] || {})) {
        const c = Number(ck), cell = cd[rk][ck]
        if (!cell) continue
        const v = cell.v, f = cell.f ? String(cell.f).replace(/^=/, '') : ''
        if (!f && (v === undefined || v === null || v === '')) continue
        const o: any = typeof v === 'number' ? { t: 'n', v } : typeof v === 'boolean' ? { t: 'b', v }
          : v === undefined || v === null ? { t: 'n' } : { t: 's', v: String(v) }
        if (f) o.f = f
        ws[XLSX.utils.encode_cell({ r, c })] = o
        if (r > maxR) maxR = r
        if (c > maxC) maxC = c
      }
    }
    ws['!ref'] = XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: maxR, c: maxC } })
    const nm = String(s.name || sid).replace(/[\\/?*\[\]:]/g, '_').substring(0, 31)
    XLSX.utils.book_append_sheet(out, ws, nm || 'Sheet')
  })

  const wbout = XLSX.write(out, { bookType: 'xlsx', type: 'array' })
  const blob = new Blob([wbout], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const base = wb.getName ? wb.getName() : 'ZENOS'
  a.download = (base || 'ZENOS') + '.xlsx'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    URL.revokeObjectURL(url)
    a.remove()
  }, 1500)
}

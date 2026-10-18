import * as XLSX from 'xlsx'
import { applyDarkChrome } from './chrome'
import { liftRibbonTabs } from './ribbon'

// --- Open an .xlsx/.xls/.csv file into a new Univer workbook (values + formulas) ---
export async function openXlsxFile(univerAPI: any, file: File) {
  const buf = await file.arrayBuffer()
  const wb = XLSX.read(new Uint8Array(buf), { type: 'array', cellFormula: true })
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
          if (cell.f) cellData[r][c] = { f: '=' + String(cell.f) }
          else if (cell.v !== undefined && cell.v !== null) cellData[r][c] = { v: cell.v }
          else continue
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
    const rows = Object.keys(cd).map(Number)
    const maxR = rows.length ? Math.max(...rows) : 0
    const aoa: any[][] = []
    for (let r = 0; r <= maxR; r++) {
      const rowObj = cd[r] || {}
      const cols = Object.keys(rowObj).map(Number)
      const maxC = cols.length ? Math.max(...cols) : 0
      const arr: any[] = []
      for (let c = 0; c <= maxC; c++) {
        const cell = rowObj[c]
        if (!cell) { arr.push(null); continue }
        if (cell.v !== undefined && cell.v !== null) arr.push(cell.v)
        else if (cell.f) arr.push(String(cell.f))
        else arr.push(null)
      }
      aoa.push(arr)
    }
    const ws = XLSX.utils.aoa_to_sheet(aoa)
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

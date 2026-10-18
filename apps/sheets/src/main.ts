import './style.css'
import { createUniver, defaultTheme, LocaleType, merge } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US'
import '@univerjs/preset-sheets-core/lib/index.css'
import { openXlsxFile, saveXlsx } from './xlsx'
import { openAiPanel, openSettings } from './ai'
import { applyDarkChrome } from './chrome'
import { liftRibbonTabs } from './ribbon'

const { univerAPI } = createUniver({
  locale: LocaleType.EN_US,
  locales: {
    [LocaleType.EN_US]: merge({}, sheetsCoreEnUS),
  },
  theme: defaultTheme,
  presets: [
    UniverSheetsCorePreset({ container: 'app' }),
  ],
})

univerAPI.createWorkbook({ name: 'ZENOS Sheet' })
// Light canvas (white cells + white formula bar, black text) + dark top toolbar.
applyDarkChrome()
liftRibbonTabs()
;(window as any).univerAPI = univerAPI

// --- ZENOS bar wiring ---
const $ = (id: string) => document.getElementById(id)!
const fileInput = $('fileinput') as HTMLInputElement

$('btn-open').addEventListener('click', () => fileInput.click())
fileInput.addEventListener('change', async () => {
  const f = fileInput.files && fileInput.files[0]
  if (f) {
    try {
      await openXlsxFile(univerAPI, f)
    } catch (e) {
      console.error('[ZENOS Sheets] open failed:', e)
    }
    fileInput.value = ''
  }
})

$('btn-save').addEventListener('click', () => {
  try {
    saveXlsx(univerAPI)
  } catch (e) {
    console.error('[ZENOS Sheets] save failed:', e)
  }
})

$('btn-ai').addEventListener('click', () => openAiPanel(univerAPI))
$('btn-settings').addEventListener('click', () => openSettings())

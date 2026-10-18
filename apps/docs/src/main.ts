import './style.css'
import { createUniver, defaultTheme, LocaleType, merge } from '@univerjs/presets'
import { UniverDocsCorePreset } from '@univerjs/preset-docs-core'
import docsCoreEnUS from '@univerjs/preset-docs-core/locales/en-US'
import '@univerjs/preset-docs-core/lib/index.css'
import { openDocxFile, saveDocx } from './docx'
import { openAiPanel, openSettings } from './ai'
import { ZENOS_DOC_STYLE } from './docstyle'
import { applyDarkChrome } from './chrome'
import { liftRibbonTabs } from './ribbon'

const { univerAPI } = createUniver({
  locale: LocaleType.EN_US,
  locales: {
    [LocaleType.EN_US]: merge({}, docsCoreEnUS),
  },
  theme: defaultTheme,
  presets: [
    UniverDocsCorePreset({ container: 'app' }),
  ],
})

univerAPI.createDocument({ title: 'ZENOS Document', documentStyle: ZENOS_DOC_STYLE })
// Light canvas (white paper, black text) + dark top chrome to match ZENOS Sheets.
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
      await openDocxFile(univerAPI, f)
    } catch (e) {
      console.error('[ZENOS Docs] open failed:', e)
    }
    fileInput.value = ''
  }
})

$('btn-save').addEventListener('click', async () => {
  try {
    await saveDocx(univerAPI)
  } catch (e) {
    console.error('[ZENOS Docs] save failed:', e)
  }
})

$('btn-ai').addEventListener('click', () => openAiPanel(univerAPI))
$('btn-settings').addEventListener('click', () => openSettings())

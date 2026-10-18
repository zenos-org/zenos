// ZENOS Sheets - user-supplied AI, protected by a password-locked vault.
import * as vault from './vault'
import type { AiConfig, AiProvider } from './vault'

function esc(s: string): string {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export function isConfigured(): boolean {
  if (!vault.isUnlocked()) return false
  const c = vault.getConfig()
  if (!c || !c.apiKey) return false
  return c.provider === 'anthropic' ? true : !!c.baseUrl
}

// ---- password gate (create or unlock) ----
function overlay(html: string): { ov: HTMLElement; close: () => void } {
  const ov = document.createElement('div')
  ov.className = 'zov'
  ov.innerHTML = html
  document.body.appendChild(ov)
  return { ov, close: () => ov.remove() }
}

function showCreate(resolve: (ok: boolean) => void) {
  const { ov, close } = overlay(`
    <div class="zmodal">
      <div class="zmodal-h">AI 保護パスワードの設定</div>
      <div class="zmodal-b">
        <p class="znote">この端末で AI（あなたのAPIキー）を使うためのパスワードを決めてください。キーはこのパスワードで暗号化して保存され、パスワードを知らない第三者は AI を使うことも、キーを見ることもできません。</p>
        <label>新しいパスワード</label>
        <input id="z-p1" type="password" spellcheck="false" autocomplete="new-password">
        <label>確認（もう一度）</label>
        <input id="z-p2" type="password" spellcheck="false" autocomplete="new-password">
        <div class="zhint" id="z-perr"></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-pcancel" class="zbtn-ghost">キャンセル</button>
        <button id="z-pok" class="zbtn-primary">設定</button>
      </div>
    </div>`)
  const p1 = ov.querySelector('#z-p1') as HTMLInputElement
  const p2 = ov.querySelector('#z-p2') as HTMLInputElement
  const err = ov.querySelector('#z-perr') as HTMLElement
  const done = (ok: boolean) => { close(); resolve(ok) }
  ;(ov.querySelector('#z-pcancel') as HTMLElement).addEventListener('click', () => done(false))
  ;(ov.querySelector('#z-pok') as HTMLElement).addEventListener('click', async () => {
    const a = p1.value, b = p2.value
    if (a.length < 4) { err.textContent = '4文字以上にしてください。'; return }
    if (a !== b) { err.textContent = 'パスワードが一致しません。'; return }
    try {
      await vault.createVault(a, { provider: 'openai', baseUrl: '', apiKey: '', model: '' })
      done(true)
    } catch (e: any) {
      err.textContent = '設定に失敗: ' + (e && e.message ? e.message : String(e))
    }
  })
  setTimeout(() => p1.focus(), 50)
}

function showUnlock(resolve: (ok: boolean) => void) {
  const { ov, close } = overlay(`
    <div class="zmodal">
      <div class="zmodal-h">ロック解除</div>
      <div class="zmodal-b">
        <p class="znote">AI を使うにはパスワードが必要です。第三者による無断利用を防ぐため、正しいパスワードを入力するまで AI は使えません。</p>
        <label>パスワード</label>
        <input id="z-up" type="password" spellcheck="false" autocomplete="current-password">
        <div class="zhint" id="z-uerr"></div>
        <div class="zhint"><a href="#" id="z-reset" style="color:#8a7bff">パスワードを忘れた場合は初期化</a></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-ucancel" class="zbtn-ghost">キャンセル</button>
        <button id="z-uok" class="zbtn-primary">解除</button>
      </div>
    </div>`)
  const pw = ov.querySelector('#z-up') as HTMLInputElement
  const err = ov.querySelector('#z-uerr') as HTMLElement
  const done = (ok: boolean) => { close(); resolve(ok) }
  const tryUnlock = async () => {
    try {
      await vault.unlock(pw.value)
      done(true)
    } catch (e: any) {
      err.textContent = e && e.message ? e.message : String(e)
      pw.value = ''
      pw.focus()
    }
  }
  ;(ov.querySelector('#z-ucancel') as HTMLElement).addEventListener('click', () => done(false))
  ;(ov.querySelector('#z-uok') as HTMLElement).addEventListener('click', tryUnlock)
  pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') tryUnlock() })
  ;(ov.querySelector('#z-reset') as HTMLElement).addEventListener('click', (e) => {
    e.preventDefault()
    if (confirm('金庫を初期化すると、保存済みのAPI接続情報は消えます。よろしいですか？')) {
      vault.destroyVault()
      close()
      showCreate(resolve)
    }
  })
  setTimeout(() => pw.focus(), 50)
}

function ensureAccess(): Promise<boolean> {
  if (vault.isUnlocked()) return Promise.resolve(true)
  if (!vault.cryptoAvailable()) {
    alert('この環境では暗号化（WebCrypto）が使えないため、保護付きAIを有効にできません。')
    return Promise.resolve(false)
  }
  return new Promise((resolve) => {
    if (vault.hasVault()) showUnlock(resolve)
    else showCreate(resolve)
  })
}

function showChangePassword() {
  const { ov, close } = overlay(`
    <div class="zmodal">
      <div class="zmodal-h">パスワード変更</div>
      <div class="zmodal-b">
        <label>現在のパスワード</label>
        <input id="z-c0" type="password" spellcheck="false">
        <label>新しいパスワード</label>
        <input id="z-c1" type="password" spellcheck="false">
        <label>確認（もう一度）</label>
        <input id="z-c2" type="password" spellcheck="false">
        <div class="zhint" id="z-cerr"></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-ccancel" class="zbtn-ghost">キャンセル</button>
        <button id="z-cok" class="zbtn-primary">変更</button>
      </div>
    </div>`)
  const err = ov.querySelector('#z-cerr') as HTMLElement
  ;(ov.querySelector('#z-ccancel') as HTMLElement).addEventListener('click', close)
  ;(ov.querySelector('#z-cok') as HTMLElement).addEventListener('click', async () => {
    const c0 = (ov.querySelector('#z-c0') as HTMLInputElement).value
    const c1 = (ov.querySelector('#z-c1') as HTMLInputElement).value
    const c2 = (ov.querySelector('#z-c2') as HTMLInputElement).value
    if (c1.length < 4) { err.textContent = '新しいパスワードは4文字以上にしてください。'; return }
    if (c1 !== c2) { err.textContent = '新しいパスワードが一致しません。'; return }
    try {
      await vault.changePassword(c0, c1)
      close()
    } catch (e: any) {
      err.textContent = e && e.message ? e.message : String(e)
    }
  })
}

// ---- Settings form (requires access first) ----
export async function openSettings(onSaved?: () => void) {
  if (!(await ensureAccess())) return
  openSettingsForm(onSaved)
}

function openSettingsForm(onSaved?: () => void) {
  const cfg = vault.getConfig() || { provider: 'openai' as AiProvider, baseUrl: '', apiKey: '', model: '' }
  const { ov, close } = overlay(`
    <div class="zmodal">
      <div class="zmodal-h">AI 接続設定（自前API・保護済み）</div>
      <div class="zmodal-b">
        <p class="znote">標準では AI に一切接続しません。ここで登録したときだけ、あなたが指定したAPIに接続します。キーはこの端末でパスワード暗号化して保存され、ロック解除した間だけ使えます。</p>
        <label>プロバイダ</label>
        <select id="z-provider">
          <option value="openai">OpenAI互換（OpenAI / ローカル / ゲートウェイ）</option>
          <option value="anthropic">Anthropic（Claude 公式API）</option>
        </select>
        <label>エンドポイント</label>
        <input id="z-base" type="text" spellcheck="false" value="${esc(cfg.baseUrl)}">
        <div class="zhint" id="z-basehint"></div>
        <label>API キー</label>
        <input id="z-key" type="password" spellcheck="false" placeholder="sk-... / sk-ant-..." value="${esc(cfg.apiKey)}">
        <label>モデル</label>
        <input id="z-model" type="text" spellcheck="false" value="${esc(cfg.model)}">
        <div class="zhint" id="z-modelhint"></div>
      </div>
      <div class="zmodal-f">
        <button id="z-chpw" class="zbtn-ghost">パスワード変更</button>
        <button id="z-lock" class="zbtn-ghost">ロック</button>
        <span style="flex:1"></span>
        <button id="z-cancel" class="zbtn-ghost">キャンセル</button>
        <button id="z-save" class="zbtn-primary">保存</button>
      </div>
    </div>`)
  const q = (s: string) => ov.querySelector(s) as HTMLInputElement
  const provider = ov.querySelector('#z-provider') as HTMLSelectElement
  const baseEl = q('#z-base')
  const baseHint = ov.querySelector('#z-basehint') as HTMLElement
  const modelEl = q('#z-model')
  const modelHint = ov.querySelector('#z-modelhint') as HTMLElement
  provider.value = cfg.provider || 'openai'

  const applyProviderUi = () => {
    if (provider.value === 'anthropic') {
      baseEl.placeholder = '空欄で既定: https://api.anthropic.com'
      baseHint.textContent = '空欄なら https://api.anthropic.com に接続します（独自プロキシを使う場合のみ入力）。'
      modelEl.placeholder = '例: claude-sonnet-4-5 / claude-opus-4-8'
      modelHint.textContent = 'Claude のモデル名を入力してください。'
    } else {
      baseEl.placeholder = '例: https://api.openai.com/v1 / http://localhost:11434/v1'
      baseHint.textContent = 'OpenAI互換の /v1 エンドポイントを入力してください。'
      modelEl.placeholder = '例: gpt-4o-mini / 任意のモデル名'
      modelHint.textContent = ''
    }
  }
  applyProviderUi()
  provider.addEventListener('change', applyProviderUi)

  ov.addEventListener('click', (e) => { if (e.target === ov) close() })
  ;(ov.querySelector('#z-cancel') as HTMLElement).addEventListener('click', close)
  ;(ov.querySelector('#z-chpw') as HTMLElement).addEventListener('click', () => { close(); showChangePassword() })
  ;(ov.querySelector('#z-lock') as HTMLElement).addEventListener('click', () => {
    vault.lock()
    close()
    if (onSaved) onSaved()
  })
  ;(ov.querySelector('#z-save') as HTMLElement).addEventListener('click', async () => {
    try {
      await vault.saveConfig({
        provider: (provider.value as AiProvider) || 'openai',
        baseUrl: baseEl.value.trim().replace(/\/+$/, ''),
        apiKey: q('#z-key').value.trim(),
        model: modelEl.value.trim(),
      })
      if (onSaved) onSaved()
      close()
    } catch (e: any) {
      console.error('[ZENOS Sheets] save config failed:', e)
    }
  })
}

// ---- gather sheet context ----
function gatherContext(univerAPI: any): string {
  try {
    const wb = univerAPI.getActiveWorkbook()
    const ws = wb.getActiveSheet()
    const range = ws.getDataRange()
    const vals: any[][] = range.getValues()
    const rows = vals
      .slice(0, 60)
      .map((r) => r.slice(0, 20).map((c) => (c === null || c === undefined ? '' : String(c))).join('\t'))
    let name = ''
    try { name = ws.getSheetName ? ws.getSheetName() : (ws.getName ? ws.getName() : '') } catch {}
    return 'シート名: ' + name + '\n現在の表（先頭部分・タブ区切り）:\n' + rows.join('\n')
  } catch {
    return ''
  }
}

async function callAI(prompt: string, ctx: string): Promise<string> {
  const cfg = vault.getConfig()
  if (!cfg) throw new Error('ロックされています')
  const sys =
    'あなたはZENOSの表計算アシスタントです。日本語で簡潔に答えます。' +
    '数式を提案するときは、そのままセルに貼れる形（先頭に=）で書いてください。'
  const user = ctx ? prompt + '\n\n---\n' + ctx : prompt
  const res = await fetch('/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: cfg.provider || 'openai',
      baseUrl: cfg.baseUrl,
      apiKey: cfg.apiKey,
      model: cfg.model,
      temperature: 0.2,
      messages: [
        { role: 'system', content: sys },
        { role: 'user', content: user },
      ],
    }),
  })
  const text = await res.text()
  if (!res.ok) {
    let msg = text
    try { msg = JSON.parse(text).error || text } catch {}
    throw new Error(res.status + ' ' + String(msg).slice(0, 400))
  }
  let data: any
  try { data = JSON.parse(text) } catch { return text.slice(0, 1000) }
  if (typeof data.text === 'string') return data.text
  const oc = data && data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content
  if (oc) return oc
  return JSON.stringify(data).slice(0, 1000)
}

// ---- AI panel (requires access first) ----
export async function openAiPanel(univerAPI: any) {
  if (!(await ensureAccess())) return
  openAiPanelUi(univerAPI)
}

function openAiPanelUi(univerAPI: any) {
  if (document.getElementById('z-aipanel')) return
  const d = document.createElement('div')
  d.id = 'z-aipanel'
  d.className = 'zpanel'
  d.innerHTML = `
    <div class="zpanel-h"><span>AI アシスタント</span>
      <button id="z-ailock" class="zx" title="ロック">🔒</button>
      <button id="z-aiclose" class="zx" title="閉じる">×</button>
    </div>
    <div class="zpanel-note" id="z-ainote"></div>
    <div class="zpanel-log" id="z-ailog"></div>
    <div class="zpanel-in">
      <label class="zchk"><input type="checkbox" id="z-ctx" checked> 使用中の表を文脈に含める</label>
      <textarea id="z-prompt" rows="3" placeholder="例: この表のジャンル別の曲数を数える数式を作って"></textarea>
      <div class="zpanel-row">
        <button id="z-setfromhere" class="zbtn-ghost">接続設定</button>
        <span style="flex:1"></span>
        <button id="z-send" class="zbtn-primary">送信</button>
      </div>
    </div>`
  document.body.appendChild(d)

  const note = d.querySelector('#z-ainote') as HTMLElement
  const log = d.querySelector('#z-ailog') as HTMLElement
  const promptEl = d.querySelector('#z-prompt') as HTMLTextAreaElement

  const refreshNote = () => {
    const c = vault.getConfig()
    if (isConfigured() && c) {
      const where = c.provider === 'anthropic' ? (c.baseUrl || 'Anthropic (api.anthropic.com)') : c.baseUrl
      const label = c.provider === 'anthropic' ? 'Claude' : 'OpenAI互換'
      note.textContent = '接続: ' + label + '  /  ' + where + '  /  ' + (c.model || '(モデル未指定)')
      note.className = 'zpanel-note ok'
    } else if (vault.isUnlocked()) {
      note.textContent = '解除済み：下の「接続設定」からあなたのAPIを登録してください。'
      note.className = 'zpanel-note warn'
    } else {
      note.textContent = 'ロック中：操作するにはパスワードが必要です。'
      note.className = 'zpanel-note warn'
    }
  }
  refreshNote()

  const add = (role: string, text: string) => {
    const b = document.createElement('div')
    b.className = 'zmsg ' + role
    b.textContent = text
    log.appendChild(b)
    log.scrollTop = log.scrollHeight
    return b
  }

  ;(d.querySelector('#z-aiclose') as HTMLElement).addEventListener('click', () => d.remove())
  ;(d.querySelector('#z-ailock') as HTMLElement).addEventListener('click', () => {
    vault.lock()
    d.remove()
  })
  ;(d.querySelector('#z-setfromhere') as HTMLElement).addEventListener('click', () => openSettings(refreshNote))

  const send = async () => {
    if (!vault.isUnlocked()) { if (!(await ensureAccess())) return }
    if (!isConfigured()) { refreshNote(); return }
    const pr = promptEl.value.trim()
    if (!pr) return
    add('user', pr)
    promptEl.value = ''
    const thinking = add('ai', '…')
    const ctx = (d.querySelector('#z-ctx') as HTMLInputElement).checked ? gatherContext(univerAPI) : ''
    try {
      thinking.textContent = await callAI(pr, ctx)
    } catch (e: any) {
      thinking.textContent = 'エラー: ' + (e && e.message ? e.message : String(e))
      thinking.classList.add('err')
    }
  }
  ;(d.querySelector('#z-send') as HTMLElement).addEventListener('click', send)
  promptEl.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send() }
  })
}

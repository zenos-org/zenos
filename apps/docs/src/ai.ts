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
      <div class="zmodal-h">Set an AI password</div>
      <div class="zmodal-b">
        <p class="znote">Choose a password for using AI (your API key) on this device. The key is stored encrypted with this password, so anyone who does not know it can neither use the AI nor see the key.</p>
        <label>New password</label>
        <input id="z-p1" type="password" spellcheck="false" autocomplete="new-password">
        <label>Confirm password</label>
        <input id="z-p2" type="password" spellcheck="false" autocomplete="new-password">
        <div class="zhint" id="z-perr"></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-pcancel" class="zbtn-ghost">Cancel</button>
        <button id="z-pok" class="zbtn-primary">Set</button>
      </div>
    </div>`)
  const p1 = ov.querySelector('#z-p1') as HTMLInputElement
  const p2 = ov.querySelector('#z-p2') as HTMLInputElement
  const err = ov.querySelector('#z-perr') as HTMLElement
  const done = (ok: boolean) => { close(); resolve(ok) }
  ;(ov.querySelector('#z-pcancel') as HTMLElement).addEventListener('click', () => done(false))
  ;(ov.querySelector('#z-pok') as HTMLElement).addEventListener('click', async () => {
    const a = p1.value, b = p2.value
    if (a.length < 4) { err.textContent = 'Use at least 4 characters.'; return }
    if (a !== b) { err.textContent = 'The passwords do not match.'; return }
    try {
      await vault.createVault(a, { provider: 'openai', baseUrl: '', apiKey: '', model: '' })
      done(true)
    } catch (e: any) {
      err.textContent = 'Could not save: ' + (e && e.message ? e.message : String(e))
    }
  })
  setTimeout(() => p1.focus(), 50)
}

function showUnlock(resolve: (ok: boolean) => void) {
  const { ov, close } = overlay(`
    <div class="zmodal">
      <div class="zmodal-h">Unlock</div>
      <div class="zmodal-b">
        <p class="znote">A password is needed to use AI. To stop others from using it without permission, AI stays off until the right password is entered.</p>
        <label>Password</label>
        <input id="z-up" type="password" spellcheck="false" autocomplete="current-password">
        <div class="zhint" id="z-uerr"></div>
        <div class="zhint"><a href="#" id="z-reset" style="color:#8a7bff">Forgot the password? Reset</a></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-ucancel" class="zbtn-ghost">Cancel</button>
        <button id="z-uok" class="zbtn-primary">Unlock</button>
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
    if (confirm('Resetting deletes the saved API connection. Continue?')) {
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
    alert('Encryption (WebCrypto) is not available here, so protected AI cannot be turned on.')
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
      <div class="zmodal-h">Change password</div>
      <div class="zmodal-b">
        <label>Current password</label>
        <input id="z-c0" type="password" spellcheck="false">
        <label>New password</label>
        <input id="z-c1" type="password" spellcheck="false">
        <label>Confirm password</label>
        <input id="z-c2" type="password" spellcheck="false">
        <div class="zhint" id="z-cerr"></div>
      </div>
      <div class="zmodal-f">
        <span style="flex:1"></span>
        <button id="z-ccancel" class="zbtn-ghost">Cancel</button>
        <button id="z-cok" class="zbtn-primary">Change</button>
      </div>
    </div>`)
  const err = ov.querySelector('#z-cerr') as HTMLElement
  ;(ov.querySelector('#z-ccancel') as HTMLElement).addEventListener('click', close)
  ;(ov.querySelector('#z-cok') as HTMLElement).addEventListener('click', async () => {
    const c0 = (ov.querySelector('#z-c0') as HTMLInputElement).value
    const c1 = (ov.querySelector('#z-c1') as HTMLInputElement).value
    const c2 = (ov.querySelector('#z-c2') as HTMLInputElement).value
    if (c1.length < 4) { err.textContent = 'The new password must be at least 4 characters.'; return }
    if (c1 !== c2) { err.textContent = 'The new passwords do not match.'; return }
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
      <div class="zmodal-h">AI connection (your own API, protected)</div>
      <div class="zmodal-b">
        <p class="znote">By default ZENOS connects to no AI at all. Only when you register one here does it connect, to the API you choose. The key is stored on this device encrypted with your password and can be used only while unlocked.</p>
        <label>Provider</label>
        <select id="z-provider">
          <option value="openai">OpenAI-compatible (OpenAI / local / gateway)</option>
          <option value="anthropic">Anthropic (Claude API)</option>
        </select>
        <label>Endpoint</label>
        <input id="z-base" type="text" spellcheck="false" value="${esc(cfg.baseUrl)}">
        <div class="zhint" id="z-basehint"></div>
        <label>API key</label>
        <input id="z-key" type="password" spellcheck="false" placeholder="sk-... / sk-ant-..." value="${esc(cfg.apiKey)}">
        <label>Model</label>
        <input id="z-model" type="text" spellcheck="false" value="${esc(cfg.model)}">
        <div class="zhint" id="z-modelhint"></div>
      </div>
      <div class="zmodal-f">
        <button id="z-chpw" class="zbtn-ghost">Change password</button>
        <button id="z-lock" class="zbtn-ghost">Lock</button>
        <span style="flex:1"></span>
        <button id="z-cancel" class="zbtn-ghost">Cancel</button>
        <button id="z-save" class="zbtn-primary">Save</button>
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
      baseEl.placeholder = 'Blank for the default: https://api.anthropic.com'
      baseHint.textContent = 'Leave blank to use https://api.anthropic.com (fill in only for your own proxy).'
      modelEl.placeholder = 'e.g. claude-sonnet-4-5 / claude-opus-4-8'
      modelHint.textContent = 'Enter a Claude model name.'
    } else {
      baseEl.placeholder = 'e.g. https://api.openai.com/v1 / http://localhost:11434/v1'
      baseHint.textContent = 'Enter an OpenAI-compatible /v1 endpoint.'
      modelEl.placeholder = 'e.g. gpt-4o-mini / any model name'
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
    const doc = univerAPI.getActiveDocument()
    let raw = ''
    try {
      const body = doc && doc.getBody ? doc.getBody() : null
      raw = body && body.dataStream ? body.dataStream : ''
    } catch {}
    let text = String(raw || '').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '').replace(/\r/g, '\n')
    if (text.length > 6000) text = text.slice(0, 6000) + '… (truncated)'
    return 'Current document (beginning of the text):\n' + text
  } catch {
    return ''
  }
}

async function callAI(prompt: string, ctx: string): Promise<string> {
  const cfg = vault.getConfig()
  if (!cfg) throw new Error('Locked')
  const sys =
    'You are the ZENOS writing assistant. Answer concisely, in the language the user writes in. ' +
    'Return edits, summaries, continuations and rewordings in a form that can go straight into the document.'
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
    <div class="zpanel-h"><span>AI assistant</span>
      <button id="z-ailock" class="zx" title="Lock">🔒</button>
      <button id="z-aiclose" class="zx" title="Close">×</button>
    </div>
    <div class="zpanel-note" id="z-ainote"></div>
    <div class="zpanel-log" id="z-ailog"></div>
    <div class="zpanel-in">
      <label class="zchk"><input type="checkbox" id="z-ctx" checked> Include the document as context</label>
      <textarea id="z-prompt" rows="3" placeholder="e.g. Make this more formal / Continue the text / Summarize in 3 lines"></textarea>
      <div class="zpanel-row">
        <button id="z-setfromhere" class="zbtn-ghost">Connection</button>
        <span style="flex:1"></span>
        <button id="z-send" class="zbtn-primary">Send</button>
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
      const label = c.provider === 'anthropic' ? 'Claude' : 'OpenAI-compatible'
      note.textContent = 'Connected: ' + label + '  /  ' + where + '  /  ' + (c.model || '(no model set)')
      note.className = 'zpanel-note ok'
    } else if (vault.isUnlocked()) {
      note.textContent = 'Unlocked. Register your API under Connection below.'
      note.className = 'zpanel-note warn'
    } else {
      note.textContent = 'Locked. Enter the password to use AI.'
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
      thinking.textContent = 'Error: ' + (e && e.message ? e.message : String(e))
      thinking.classList.add('err')
    }
  }
  ;(d.querySelector('#z-send') as HTMLElement).addEventListener('click', send)
  promptEl.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send() }
  })
}

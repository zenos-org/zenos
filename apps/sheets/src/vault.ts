// ZENOS Sheets - password-protected vault for the user's AI credentials.
// The API key is encrypted at rest with a key derived from the user's password
// (PBKDF2 -> AES-GCM). Without the password it cannot be decrypted or used.
export type AiProvider = 'openai' | 'anthropic'
export interface AiConfig {
  provider: AiProvider
  baseUrl: string
  apiKey: string
  model: string
}

const VKEY = 'zenos.ai.vault.v1'
const ITER = 210000

let memKey: CryptoKey | null = null
let memSalt: Uint8Array | null = null
let memConfig: AiConfig | null = null

function b64(buf: ArrayBuffer | Uint8Array): string {
  const u = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let s = ''
  for (let i = 0; i < u.length; i++) s += String.fromCharCode(u[i])
  return btoa(s)
}
function unb64(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
}

async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: ITER, hash: 'SHA-256' },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

async function persist(config: AiConfig, key: CryptoKey, salt: Uint8Array) {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const data = new TextEncoder().encode(JSON.stringify(config))
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, data)
  localStorage.setItem(VKEY, JSON.stringify({ v: 1, salt: b64(salt), iv: b64(iv), ct: b64(ct) }))
}

export function hasVault(): boolean {
  try { return !!localStorage.getItem(VKEY) } catch { return false }
}
export function isUnlocked(): boolean {
  return !!memConfig && !!memKey
}
export function lock(): void {
  memKey = null
  memSalt = null
  memConfig = null
}
export function getConfig(): AiConfig | null {
  return memConfig
}

export async function createVault(password: string, config: AiConfig): Promise<void> {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const key = await deriveKey(password, salt)
  await persist(config, key, salt)
  memKey = key
  memSalt = salt
  memConfig = config
}

export async function unlock(password: string): Promise<void> {
  const raw = localStorage.getItem(VKEY)
  if (!raw) throw new Error('金庫がありません')
  const v = JSON.parse(raw)
  const salt = unb64(v.salt)
  const iv = unb64(v.iv)
  const ct = unb64(v.ct)
  const key = await deriveKey(password, salt)
  let plain: ArrayBuffer
  try {
    plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct)
  } catch {
    throw new Error('パスワードが違います')
  }
  memConfig = JSON.parse(new TextDecoder().decode(plain))
  memKey = key
  memSalt = salt
}

export async function saveConfig(config: AiConfig): Promise<void> {
  if (!memKey || !memSalt) throw new Error('ロックされています')
  await persist(config, memKey, memSalt)
  memConfig = config
}

export async function changePassword(oldPw: string, newPw: string): Promise<void> {
  await unlock(oldPw) // verifies old password; throws on mismatch
  const cfg = memConfig as AiConfig
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const key = await deriveKey(newPw, salt)
  await persist(cfg, key, salt)
  memKey = key
  memSalt = salt
}

export function destroyVault(): void {
  try { localStorage.removeItem(VKEY) } catch {}
  lock()
}

export function cryptoAvailable(): boolean {
  return typeof crypto !== 'undefined' && !!crypto.subtle
}

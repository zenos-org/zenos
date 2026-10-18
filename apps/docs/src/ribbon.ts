// Move the Univer ribbon tabs (Start / Formulas / View ...) up into the ZENOS top
// bar so they no longer consume a full vertical row. The original tab row is
// hidden; the ZENOS tabs click through to the original buttons to switch toolbars.
// A MutationObserver keeps the lifted tabs in sync with tabs that render late and
// with the active-tab state.
export function liftRibbonTabs(retries = 60) {
  const header = document.querySelector('#app header')
  const row = header ? (header.querySelector('.univer-select-none') as HTMLElement | null) : null
  const bar = document.getElementById('bar')
  if (!header || !row || !bar || row.querySelectorAll('button').length === 0) {
    if (retries > 0) setTimeout(() => liftRibbonTabs(retries - 1), 150)
    return
  }
  if ((row as any)._zenosLifted) {
    row.style.display = 'none'
    return
  }
  ;(row as any)._zenosLifted = true
  row.style.display = 'none'

  let container = document.querySelector('#bar .ztabs') as HTMLElement | null
  if (!container) {
    container = document.createElement('div')
    container.className = 'ztabs'
    const save = document.getElementById('btn-save')
    if (save) save.insertAdjacentElement('afterend', container)
    else bar.appendChild(container)
  }

  let obs: HTMLButtonElement[] = []
  let zbtns: HTMLButtonElement[] = []
  const sync = () => {
    obs.forEach((ob, i) => {
      if (zbtns[i]) zbtns[i].classList.toggle('ztab-active', ob.getAttribute('aria-selected') === 'true')
    })
  }
  const rebuild = () => {
    obs = Array.from(row.querySelectorAll('button')) as HTMLButtonElement[]
    container!.innerHTML = ''
    zbtns = obs.map((ob) => {
      const b = document.createElement('button')
      b.type = 'button'
      b.textContent = (ob.textContent || '').trim()
      b.className = 'ztab'
      b.addEventListener('click', () => {
        ob.click()
        setTimeout(sync, 60)
      })
      container!.appendChild(b)
      return b
    })
    row.style.display = 'none'
    sync()
  }
  rebuild()

  const mo = new MutationObserver((muts) => {
    if (muts.some((m) => m.type === 'childList')) rebuild()
    else sync()
  })
  mo.observe(row, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-selected'] })
}

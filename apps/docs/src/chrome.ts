// Keep the Univer canvas in light mode (white page, black text) while making the
// top chrome (toolbar/ribbon + status bar) dark, by scoping Univer's `univer-dark`
// class to the chrome DOM only (its Tailwind `dark:` variants then apply there).
export function applyDarkChrome(retries = 25) {
  const header = document.querySelector('#app header') as HTMLElement | null
  if (!header) {
    if (retries > 0) setTimeout(() => applyDarkChrome(retries - 1), 150)
    return
  }
  const column = header.parentElement || header
  column.classList.add('univer-dark', 'zenos-dark-chrome')
  // make sure the page background itself is not pulled dark
  document.documentElement.classList.remove('univer-dark')
}

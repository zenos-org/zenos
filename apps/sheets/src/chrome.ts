// Keep the Univer canvas in light mode (white cells + white formula bar, black
// text) while making the top ribbon/toolbar AND the bottom status/sheet bar dark,
// by scoping Univer's `univer-dark` class to those chrome elements. The formula
// bar (a separate <header>) and the cells stay light.
export function applyDarkChrome(retries = 30) {
  const toolbar = document.querySelector('#app header') as HTMLElement | null // first header = toolbar
  const footer = document.querySelector('#app footer') as HTMLElement | null
  if (!toolbar) {
    if (retries > 0) setTimeout(() => applyDarkChrome(retries - 1), 150)
    return
  }
  toolbar.classList.add('univer-dark', 'zenos-dark-chrome')
  if (footer) footer.classList.add('univer-dark', 'zenos-dark-chrome')
  else if (retries > 0) setTimeout(() => applyDarkChrome(retries - 1), 150)
  document.documentElement.classList.remove('univer-dark')
}

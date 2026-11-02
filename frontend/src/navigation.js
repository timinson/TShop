export const NAVIGATION_EVENT = 'shop:navigate'

const serverPath = /^\/(?:admin|api|static|media|assets|cgi-bin)(?:\/|$)/

export function isShopPath(pathname) {
  return pathname.startsWith('/') && !pathname.startsWith('//') && !serverPath.test(pathname)
}

export function navigate(to, { replace = false } = {}) {
  const url = new URL(to, window.location.origin)
  if (url.origin !== window.location.origin || !isShopPath(url.pathname)) return
  window.history[replace ? 'replaceState' : 'pushState'](null, '', url.pathname + url.search + url.hash)
  window.dispatchEvent(new Event(NAVIGATION_EVENT))
}

export function installNavigation() {
  const migrateHash = () => {
    const legacy = window.location.hash.slice(1)
    if (legacy.startsWith('/') && !legacy.startsWith('//')) navigate(legacy, { replace: true })
    else if (window.location.hash === '#') navigate('/', { replace: true })
  }
  migrateHash()
  window.addEventListener('hashchange', migrateHash)
  const back = () => window.dispatchEvent(new Event(NAVIGATION_EVENT))
  window.addEventListener('popstate', back)
  const click = event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    const anchor = event.target.closest('a[href]')
    if (!anchor || anchor.hasAttribute('download') || anchor.target && anchor.target !== '_self') return
    const url = new URL(anchor.href)
    if (url.origin !== window.location.origin || !isShopPath(url.pathname) || url.hash) return
    event.preventDefault()
    navigate(url.pathname + url.search)
  }
  document.addEventListener('click', click)
  return () => {
    window.removeEventListener('hashchange', migrateHash)
    window.removeEventListener('popstate', back)
    document.removeEventListener('click', click)
  }
}

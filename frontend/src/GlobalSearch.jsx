import { navigate, NAVIGATION_EVENT } from './navigation'
import Arrow from './Arrow'
import { useEffect, useRef, useState } from 'react'

const money = value => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value)

export default function GlobalSearch() {
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [open, setOpen] = useState(false)
  const [state, setState] = useState({ query: '', items: [], count: 0, error: '' })
  const root = useRef(null)
  useEffect(() => { if (expanded) root.current?.querySelector('input')?.focus() }, [expanded])
  const trimmed = query.trim()
  const busy = state.query !== trimmed
  const resultsUrl = `/catalog?q=${encodeURIComponent(trimmed)}`
  useEffect(() => {
    if (!trimmed) return
    const controller = new AbortController()
    let active = true
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`/api/products/?q=${encodeURIComponent(trimmed)}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Не удалось выполнить поиск. Попробуйте ещё раз.')
        const data = await response.json()
        if (active) setState({ query: trimmed, items: data.results.slice(0, 6), count: data.count, error: '' })
      } catch (error) {
        if (active && error.name !== 'AbortError') setState({ query: trimmed, items: [], count: 0, error: 'Не удалось выполнить поиск. Измените запрос или повторите позже.' })
      }
    }, 300)
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [trimmed])
  useEffect(() => {
    const close = event => { if (!root.current?.contains(event.target)) { setOpen(false); setExpanded(false) } }
    const closeOnNavigation = () => { setOpen(false); setExpanded(false) }
    document.addEventListener('pointerdown', close)
    window.addEventListener(NAVIGATION_EVENT, closeOnNavigation)
    return () => { document.removeEventListener('pointerdown', close); window.removeEventListener(NAVIGATION_EVENT, closeOnNavigation) }
  }, [])
  return <div className={`search-control${expanded ? ' is-expanded' : ''}`} ref={root} onBlur={event => { /* Touch browsers may blur with no relatedTarget before a link receives its click. */ if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <button type="button" className="manager-link search-toggle" aria-label={expanded ? 'Закрыть поиск' : 'Открыть поиск'} title="Поиск" aria-expanded={expanded} aria-controls={expanded ? 'header-search-panel' : undefined} onClick={() => { setExpanded(value => !value); setOpen(true) }}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg></button>
    <div className="search-panel" id="header-search-panel" inert={!expanded} aria-hidden={!expanded}><div className="global-search">
    <form role="search" onSubmit={event => { event.preventDefault(); if (trimmed) { navigate(resultsUrl); setOpen(false) } }}>
      <input type="search" aria-label="Поиск по всем категориям" placeholder="Найти среди всей техники" value={query} onChange={event => { setQuery(event.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={event => { if (event.key === 'Escape') { setOpen(false); setExpanded(false); root.current.querySelector('.search-toggle').focus() }; if (event.key === 'ArrowDown') { const first = root.current.querySelector('.search-result'); if (first) { event.preventDefault(); first.focus() } } }} aria-expanded={open && !!trimmed} aria-controls={open && trimmed ? 'global-search-results' : undefined} />
      {query && <button className="search-clear" type="button" aria-label="Очистить поиск" onClick={() => { setQuery(''); root.current.querySelector('input').focus() }}>×</button>}
    </form>
    {expanded && open && trimmed && <div className="search-dropdown" id="global-search-results" onKeyDown={event => { if (event.key === 'Escape') { root.current.querySelector('.search-toggle').focus(); setOpen(false); setExpanded(false) } }}>
      <p className="search-caption" role="status">{busy ? 'Ищем по всем категориям…' : state.error || (state.count ? `Найдено товаров: ${state.count}` : 'Ничего не найдено')}</p>
      {!busy && !state.error && <><ul>{state.items.map(product => <li key={product.id}><a className="search-result" href={`/products/${product.slug}`} onClick={event => { event.preventDefault(); navigate(`/products/${product.slug}`); setOpen(false) }}>{product.image_url && <img src={product.image_url} alt="" />}<span><strong>{product.name}</strong><small>{product.category.name}</small></span><span className="search-price">{product.min_price !== null ? `от ${money(product.min_price)}` : 'Цена уточняется'}</span></a></li>)}</ul>{state.count > 0 && <a className="search-all" href={resultsUrl} onClick={event => { event.preventDefault(); navigate(resultsUrl); setOpen(false) }}>Все результаты <Arrow /></a>}</>}
    </div>}
    </div></div>
  </div>
}

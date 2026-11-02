import shopLogo from './assets/shop-logo.png'
import { navigate, NAVIGATION_EVENT } from './navigation'
import Arrow from './Arrow'
import ChatPreview from './ChatPreview'
import OrderStatus from './OrderStatus'
import { useEffect, useState } from 'react'
import './App.css'
import GlobalSearch from './GlobalSearch'
import ThemeToggle from './ThemeToggle'
import QuickAdd from './QuickAdd'
import { FavoritesProvider, FavoriteButton, Heart } from './Favorites'
import { useFavorites } from './favoritesState'
import { AddToCart, CartPage, CartProvider, CheckoutPage } from './Cart'
import { useCart } from './cartState'
import { PrivacyPage, ConsentPage } from './Privacy'

const money = value => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(value)
const productCount = count => {
  const forms = { one: 'товар', few: 'товара', many: 'товаров', other: 'товара' }
  return `${count} ${forms[new Intl.PluralRules('ru-RU').select(count)]}`
}
const emptyFilters = { q: '', category: '', color: '', memory: '', min_price: '', max_price: '', in_stock: false, ordering: '' }

function useApi(url, retry) {
  const key = `${url}:${retry}`
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  useEffect(() => {
    if (url === null) return
    const controller = new AbortController()
    let active = true
    const timer = setTimeout(() => controller.abort(), 10000)
    fetch(url, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw Object.assign(new Error(response.status === 503 ? 'Сайт обновляется. Пожалуйста, попробуйте через несколько минут.' : response.status === 404 ? 'Товар не найден.' : 'Не удалось загрузить данные. Проверьте соединение и попробуйте снова.'), { status: response.status })
        return response.json()
      })
      .then(data => { if (active) setState({ key, loading: false, data, error: '' }) })
      .catch(error => { if (active) setState({ key, loading: false, data: null, status: error.status, error: error.name === 'AbortError' ? 'Сервер не ответил вовремя. Попробуйте снова.' : error.message }) })
      .finally(() => clearTimeout(timer))
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [url, retry, key])
  if (url === null) return { loading: false, data: { count: 0, results: [], previous: null, next: null }, error: '' }
  return state.key === key ? state : { loading: true, data: null, error: '' }
}

function ProductVisual({ product }) {
  const [broken, setBroken] = useState(false)
  return <div className={`product-visual visual-${product.category.slug}`}>
    {product.image_url && !broken ? <img src={product.image_url} alt={product.name} onError={() => setBroken(true)} /> : <div className="placeholder"><span>{product.category.name}</span><small>Изображение скоро появится</small></div>}
  </div>
}

function NotFound() {
  return <section className="not-found" aria-labelledby="not-found-title"><p className="not-found-code" aria-hidden="true">404</p><p className="eyebrow">СТРАНИЦА НЕ НАЙДЕНА</p><h1 id="not-found-title">Кажется, здесь ничего нет.</h1><p className="intro">Возможно, ссылка устарела или в адресе опечатка.<br />Вернитесь к выбору техники — там всё на месте.</p><div className="not-found-actions"><a className="not-found-home" href="/"><Arrow direction="left" /> На главную</a><a href="/catalog">Все товары <Arrow /></a></div></section>
}

function ErrorMessage({ message, onRetry }) {
  return <div className="empty" role="alert"><p>{message}</p><button onClick={onRetry}>Повторить</button></div>
}

function Price({ value, original, discount = 0, from = false }) {
  return <div className="price-block">{original && discount > 0 && <div className="price-before"><del>{from ? 'от ' : ''}{money(original)}</del><span className="discount-badge">−{Math.round(discount)}%</span></div>}<p className="price">{value !== null && value !== undefined ? `${from ? 'от ' : ''}${money(value)}` : 'Цена уточняется'}</p></div>
}

function ProductCard({ product, filters }) {
  const matched = product.variants.filter(item => (!filters.color || item.color === filters.color)
    && (!filters.memory || item.memory === filters.memory)
    && (!filters.in_stock || item.stock > 0)
    && (filters.min_price === '' || Number(item.price) >= Number(filters.min_price))
    && (filters.max_price === '' || Number(item.price) <= Number(filters.max_price)))
  const cheapest = [...matched].sort((a, b) => Number(a.price) - Number(b.price))[0]
  const displayProduct = cheapest ? { ...product, min_price: cheapest.price, min_original_price: cheapest.original_price } : product
  return <article className="product-card"><a href={`/products/${product.slug}`}><ProductVisual product={product} /><div className="card-info"><p className="eyebrow">{product.category.name}</p><h3>{product.name}</h3><Price value={displayProduct.min_price} original={displayProduct.min_original_price} discount={product.discount_percent} from /></div></a><QuickAdd product={displayProduct} filters={filters} favorite={<FavoriteButton product={product} />} /></article>
}

const categoryTiles = [
  ['', 'Все товары', 'Весь каталог'], ['iphone', 'iPhone', 'Смартфоны'],
  ['ipad', 'iPad', 'Планшеты'], ['macbook', 'MacBook', 'Ноутбуки'],
  ['apple-watch', 'Apple Watch', 'Часы'], ['airpods', 'AirPods', 'Наушники'],
]
function CategoryTiles({ selected, onSelect }) {
  return <section className="category-tiles" aria-label="Категории техники">{categoryTiles.map(([slug, name, label]) => <button key={slug} type="button" className={`category-tile tile-${slug}${selected === slug ? ' selected' : ''}`} aria-pressed={selected === slug} onClick={() => onSelect(slug)}><span className="tile-top">{label}</span><svg viewBox="0 0 100 70" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">{slug === '' ? <><rect x="18" y="8" width="25" height="22" rx="3" /><rect x="55" y="8" width="25" height="22" rx="3" /><rect x="18" y="40" width="25" height="22" rx="3" /><rect x="55" y="40" width="25" height="22" rx="3" /></> : slug === 'iphone' ? <><rect x="34" y="5" width="32" height="59" rx="7" /><path d="M44 11h12M46 58h8" /></> : slug === 'ipad' ? <><rect x="20" y="6" width="60" height="56" rx="5" /><path d="M45 57h10" /></> : slug === 'macbook' ? <><rect x="20" y="9" width="60" height="42" rx="3" /><path d="M12 57h76l-5 5H17Z" /></> : slug === 'apple-watch' ? <><path d="m38 5-2 12m26-12 2 12M36 53l2 12m26-12-2 12" /><rect x="30" y="16" width="40" height="38" rx="11" /><path d="M50 25v11l8 5m14-15v9" /></> : <><path d="M29 11c-12 0-12 18 0 18h5V16c0-3-2-5-5-5Zm5 14v31c0 5-7 5-7 0V29M71 11c12 0 12 18 0 18h-5V16c0-3 2-5 5-5Zm-5 14v31c0 5 7 5 7 0V29" /></>}</svg><span className="tile-name">{name}<span><Arrow direction="up-right" /></span></span></button>)}</section>
}

function ProductDetail({ slug, backTo }) {
  const [retry, setRetry] = useState(0)
  const { data: product, loading, error, status } = useApi(`/api/products/${encodeURIComponent(slug)}/`, retry)
  const [variantId, setVariantId] = useState(null)
  if (loading) return <p className="empty" role="status">Загружаем товар…</p>
  if (status === 404) return <NotFound />
  if (error) return <><a className="back" href={backTo}><Arrow direction="left" /> В каталог</a><ErrorMessage message={error} onRetry={() => setRetry(value => value + 1)} /></>
  const variant = product.variants.find(item => item.id === variantId) || product.variants.find(item => item.stock > 0) || product.variants[0]
  return <>
    <a className="back" href={backTo}><Arrow direction="left" /> В каталог</a>
    <article className="detail">
      <ProductVisual product={product} />
      <div className="detail-info"><div className="detail-title"><h1>{product.name}</h1><span className="eyebrow">{product.category.name}</span></div><p className="description">{product.description}</p>
        {variant ? <><Price value={variant.price} original={variant.original_price} discount={product.discount_percent} /><p className={variant.stock > 0 ? 'stock' : 'muted'}>{variant.stock > 0 ? 'В наличии' : 'Нет в наличии'}</p>
          <label className="variant-label" htmlFor="variant">Цвет и комплектация</label><select id="variant" value={variant.id} onChange={event => setVariantId(Number(event.target.value))}>{product.variants.map(item => <option value={item.id} key={item.id}>{[item.color, item.memory].filter(Boolean).join(' · ')}{item.stock === 0 ? ' — нет в наличии' : ''}</option>)}</select>
          <p className="muted selected">Выбрано: {[variant.color, variant.memory].filter(Boolean).join(' / ')}</p></> : <p className="muted">Пока нет доступных вариантов.</p>}
        {variant ? <AddToCart key={variant.id} variant={variant} favorite={<FavoriteButton product={product} />} /> : <FavoriteButton product={product} />}
        {product.specifications && Object.keys(product.specifications).length > 0 && <section className="specifications"><h2>Характеристики</h2><dl>{Object.entries(product.specifications).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl></section>}
      </div>
    </article>
  </>
}

function catalogRoute() {
  const query = new URLSearchParams(window.location.search)
  return { ...emptyFilters, category: query.get('category') || '', q: query.get('q') || '' }
}
function Catalog({ mode = 'catalog' }) {
  const { ids } = useFavorites()
  const [draft, setDraft] = useState(catalogRoute)
  const [filters, setFilters] = useState(catalogRoute)
  const [filtersOpen, setFiltersOpen] = useState(() => !window.matchMedia('(max-width: 760px)').matches)
  const [catalogOpen, setCatalogOpen] = useState(() => window.location.pathname === '/catalog')
  const expanded = mode !== 'catalog' || catalogOpen
  const [page, setPage] = useState(1)
  useEffect(() => {
    const sync = () => {
      setCatalogOpen(window.location.pathname === '/catalog')
      const next = catalogRoute()
      setDraft(next); setFilters(next); setPage(1)
    }
    window.addEventListener(NAVIGATION_EVENT, sync)
    return () => window.removeEventListener(NAVIGATION_EVENT, sync)
  }, [])
  const [retry, setRetry] = useState(0)
  const visiblePage = mode === 'favorites' ? Math.min(page, Math.max(1, Math.ceil(ids.length / 12))) : page
  const invalidPrice = [draft.min_price, draft.max_price].some(value => value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 9999999999.99))
  const validation = invalidPrice ? 'Укажите неотрицательную цену до 9 999 999 999,99 ₽.' : draft.min_price && draft.max_price && Number(draft.min_price) > Number(draft.max_price) ? 'Цена «от» не может превышать цену «до».' : ''
  useEffect(() => {
    if (validation) return
    const timer = setTimeout(() => {
      setFilters({ ...draft, q: draft.q.trim() })
      setPage(1)
    }, 350)
    return () => clearTimeout(timer)
  }, [draft, validation])
  const categories = useApi('/api/categories/', retry)
  const bestsellers = useApi('/api/products/?page=1', retry)
  const options = useApi(`/api/catalog-options/${filters.category ? `?category=${encodeURIComponent(filters.category)}` : ''}`, retry)
  const params = new URLSearchParams({ page: visiblePage })
  if (mode === 'discounts') params.set('discounted', 'true')
  if (mode === 'favorites') params.set('ids', ids.length ? ids.join(',') : '0')
  Object.entries(filters).forEach(([key, value]) => { if (value !== '' && value !== false) params.set(key, String(value)) })
  const { data, loading, error } = useApi(!expanded || mode === 'favorites' && !ids.length ? null : `/api/products/?${params}`, retry)
  function openCatalog(category = '', q = '') {
    const query = new URLSearchParams()
    if (category) query.set('category', category)
    if (q.trim()) query.set('q', q.trim())
    navigate(`/catalog${query.size ? `?${query}` : ''}`)
  }
  function reset() { setDraft(emptyFilters); setFilters(emptyFilters); setPage(1); if (mode === 'catalog') openCatalog() }
  function applySelection(key, value) {
    if (key === 'category' && mode === 'catalog') { openCatalog(value, draft.q); return }
    const update = current => ({ ...current, ...(key === 'category' ? { color: '', memory: '' } : {}), [key]: value })
    setDraft(update)
    setFilters(update)
    setPage(1)
  }
  return <>
    {<div className={`home-intro${expanded ? ' collapsed' : ''}`} aria-hidden={expanded} inert={expanded}><div><section className="hero"><p className="eyebrow">ТЕХНИКА APPLE</p><h1>Ваш следующий<br /><span>большой шаг.</span></h1><p className="intro">Для работы, вдохновения и всего, что вы любите.</p></section></div></div>}
    <div className={`landing-section${expanded ? ' collapsed' : ''}`} aria-hidden={expanded} inert={expanded}><div><CategoryTiles selected={null} onSelect={value => openCatalog(value)} /></div></div>
    <div className={`landing-section${expanded ? ' collapsed' : ''}`} aria-hidden={expanded} inert={expanded}><div><section className="bestsellers" aria-labelledby="bestsellers-title"><div className="catalog-heading"><h2 id="bestsellers-title">Бестселлеры</h2><span className="muted">Самые новые модели</span></div>{bestsellers.loading ? <p className="empty" role="status">Загружаем товары…</p> : bestsellers.error ? <ErrorMessage message={bestsellers.error} onRetry={() => setRetry(value => value + 1)} /> : <div className="product-grid bestsellers-grid">{bestsellers.data.results.slice(0, 5).map(product => <ProductCard key={product.id} product={product} filters={emptyFilters} />)}</div>}</section></div></div>
    {expanded && <nav className="catalog-tabs" aria-label="Разделы каталога"><a href="/"><Arrow direction="left" /> Вернуться к категориям</a><a href="/catalog" aria-current={mode === 'catalog' ? 'page' : undefined}>Все товары</a><a href="/discounts" aria-current={mode === 'discounts' ? 'page' : undefined}>Скидки</a></nav>}
    <div className={`catalog-reveal${expanded ? ' expanded' : ''}`} aria-hidden={!expanded} inert={!expanded}><div className="catalog-reveal-inner"><div className="catalog-heading"><h2>{mode === 'discounts' ? 'Скидки' : mode === 'favorites' ? 'Избранное' : 'Каталог'}</h2><span className="muted">{!loading && data ? productCount(data.count) : 'Подбираем технику'}</span></div>
    <div className="catalog-layout">
    <aside className="catalog-sidebar" aria-label="Фильтры каталога">
    <details className="filters-panel" open={filtersOpen} onToggle={event => setFiltersOpen(event.currentTarget.open)}><summary>Фильтры<span className="filters-count">{Object.entries(draft).filter(([key, value]) => key !== 'q' && value !== '' && value !== false).length || ''}</span><svg className="filters-chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg></summary>
    <form className="filters" onSubmit={event => event.preventDefault()}>
      <label>Категория<select value={draft.category} onChange={event => applySelection('category', event.target.value)}><option value="">Вся техника</option>{[...(categories.data || []), ...(!categories.data?.some(category => category.slug === 'ipad') ? [{ id: 'ipad', slug: 'ipad', name: 'iPad' }] : [])].map(category => <option key={category.id} value={category.slug}>{category.name}</option>)}</select></label>
      <label>Цвет<select value={draft.color} onChange={event => applySelection('color', event.target.value)} disabled={options.loading}><option value="">Все цвета</option>{options.data?.colors?.map(color => <option value={color} key={color}>{color}</option>)}</select></label>
      <label>Объём памяти<select value={draft.memory} onChange={event => applySelection('memory', event.target.value)} disabled={options.loading}><option value="">Любой объём</option>{options.data?.memories?.map(memory => <option value={memory} key={memory}>{memory}</option>)}</select></label>
      <label>Сортировка<select value={draft.ordering} onChange={event => applySelection('ordering', event.target.value)}><option value="">Сначала новинки</option><option value="price">Сначала дешевле</option><option value="-price">Сначала дороже</option><option value="name">Модель: А–Я</option><option value="-name">Модель: Я–А</option></select></label>
      <label>Цена от, ₽<input type="number" min="0" step="0.01" placeholder="0" value={draft.min_price} onChange={event => setDraft({ ...draft, min_price: event.target.value })} /></label>
      <label>Цена до, ₽<input type="number" min="0" step="0.01" placeholder="Любая" value={draft.max_price} onChange={event => setDraft({ ...draft, max_price: event.target.value })} /></label>
      <label className="checkbox"><input type="checkbox" checked={draft.in_stock} onChange={event => applySelection('in_stock', event.target.checked)} />В наличии</label>
      <button type="button" className="text-button" onClick={reset}>Сбросить</button>
    </form>
    </details>
    {validation && <p role="alert" className="validation">{validation}</p>}
    {options.error && <p role="alert">Не удалось загрузить цвета и память. <button className="text-button" onClick={() => setRetry(value => value + 1)}>Повторить</button></p>}
    {categories.error && <p role="alert">Категории не загрузились. <button className="text-button" onClick={() => setRetry(value => value + 1)}>Повторить</button></p>}
    </aside>
    <div className="catalog-results">
    {loading ? <p className="empty" role="status">Загружаем каталог…</p> : error ? <ErrorMessage message={error} onRetry={() => setRetry(value => value + 1)} /> : data.results.length === 0 ? <div className="empty"><h2>{mode === 'favorites' && !ids.length ? 'В избранном пока пусто' : 'Ничего не найдено'}</h2><p>{mode === 'favorites' && !ids.length ? 'Нажмите сердечко на понравившемся товаре.' : 'Попробуйте изменить запрос или сбросить фильтры.'}</p><button onClick={reset}>Сбросить фильтры</button></div> : <>
      <div className="product-grid">{data.results.map(product => <ProductCard key={`${product.id}:${filters.color}:${filters.memory}:${filters.min_price}:${filters.max_price}`} product={product} filters={filters} />)}</div>
      <nav className="pagination" aria-label="Страницы каталога"><button disabled={!data.previous} onClick={() => setPage(visiblePage - 1)}><Arrow direction="left" /> Назад</button><span>Страница {visiblePage}</span><button disabled={!data.next} onClick={() => setPage(visiblePage + 1)}>Далее <Arrow /></button></nav>
    </>}
    </div>
    </div>
    </div></div>
  </>
}

function Shop() {
  const { cart, loading } = useCart()
  const { ids } = useFavorites()
  const [location, setLocation] = useState(window.location.pathname + window.location.search)
  const [lastCatalog, setLastCatalog] = useState(() => window.location.pathname === '/catalog' ? window.location.pathname + window.location.search : '/catalog')
  useEffect(() => { const navigate = () => { setLocation(window.location.pathname + window.location.search); if (window.location.pathname === '/catalog') setLastCatalog(window.location.pathname + window.location.search); window.scrollTo(0, 0) }; window.addEventListener(NAVIGATION_EVENT, navigate); return () => window.removeEventListener(NAVIGATION_EVENT, navigate) }, [])
  const route = location.split('?')[0].replace(/\/+$/, '') || '/'
  useEffect(() => {
    const category = new URLSearchParams(location.split('?')[1] || '').get('category')
    const categoryTitles = { iphone: 'iPhone', ipad: 'iPad', macbook: 'MacBook', 'apple-watch': 'Apple Watch', airpods: 'AirPods' }
    if (route === '/catalog') document.title = categoryTitles[category] ? `${categoryTitles[category]} — shop` : 'Каталог товаров — shop'
    else if (route === '/discounts') document.title = 'Скидки — shop'
    else if (route === '/cart') document.title = 'Корзина — shop'
    else document.title = 'shop — техника Apple'
  }, [location, route])
  const slug = /^\/products\/[^/?#]+$/.test(route) ? route.slice('/products/'.length) : null
  const orderToken = /^\/orders\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(route)?.[1]?.toLowerCase()
  const knownRoute = ['/', '/catalog', '/favorites', '/discounts', '/privacy', '/consent', '/cart', '/checkout'].includes(route)
  return <div className="page"><header><a className="brand" href="/" aria-label="shop — на главную"><svg className="brand-mark" width="56" height="44" viewBox="200 280 860 650" aria-hidden="true"><image href={shopLogo} width="1254" height="1254" /></svg><strong className="brand-name">shop</strong></a><nav className="header-links"><GlobalSearch /><a className="manager-link favorites-link" href="/favorites" aria-label={`Избранное (${ids.length})`} title="Избранное"><Heart />{ids.length > 0 && <span className="favorites-count">{ids.length}</span>}</a><ThemeToggle /><a className="manager-link" href="/admin/" aria-label="Для менеджера" title="Для менеджера"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></svg></a><a className="manager-link cart-icon" href="/cart" aria-label={`Корзина${!loading ? ` (${cart.count})` : ''}`} title="Корзина"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m8 4-4 6m12-6 4 6M3 10h18l-2 10H5L3 10ZM9 14v3m6-3v3" /></svg>{!loading && cart.count > 0 && <span className="favorites-count">{cart.count}</span>}</a></nav></header><main>{orderToken ? <OrderStatus key={orderToken} token={orderToken} /> : !slug && !knownRoute ? <NotFound /> : slug ? <ProductDetail key={slug} slug={slug} backTo={lastCatalog} /> : route === '/privacy' ? <PrivacyPage /> : route === '/consent' ? <ConsentPage /> : route === '/cart' ? <CartPage renderProduct={product => <ProductCard key={product.id} product={product} filters={emptyFilters} />} /> : route === '/checkout' ? <CheckoutPage /> : <Catalog mode={route === '/favorites' ? 'favorites' : route === '/discounts' ? 'discounts' : 'catalog'} />}</main><ChatPreview /><footer><span>shop / Техника Apple</span><a href="/privacy">Политика обработки персональных данных</a></footer></div>
}
function App() { return <FavoritesProvider><CartProvider><Shop /></CartProvider></FavoritesProvider> }
export default App

import Arrow from './Arrow'
import { OrderLink } from './OrderStatus'
import { useEffect, useState } from 'react'
import { apiRequest } from './api'
import { CartContext, money, useCart } from './cartState'
import { PRIVACY_POLICY_VERSION } from './privacyVersion'

const emptyCart = { items: [], count: 0, total: '0.00' }

export function CartProvider({ children }) {
  const [cart, setCart] = useState(emptyCart)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    apiRequest('/api/cart/').then(data => { if (active) setCart(data) }).catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  async function refresh() {
    setError(''); setBusy(true)
    try { const data = await apiRequest('/api/cart/'); setCart(data); return data } catch (err) { setError(err.message); throw err } finally { setBusy(false) }
  }
  async function mutate(url, method, body) {
    setBusy(true); setError('')
    try {
      const data = await apiRequest(url, { method, body })
      setCart(data); sessionStorage.removeItem('shop-checkout-token'); return data
    } catch (err) { setError(err.message); throw err } finally { setBusy(false) }
  }
  return <CartContext.Provider value={{ cart, loading, busy, error, refresh, mutate, setCart }}>{children}</CartContext.Provider>
}

export function AddToCart({ variant, favorite }) {
  const { mutate, busy, loading } = useCart()
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function add() {
    setMessage(''); setError('')
    try { await mutate('/api/cart/', 'POST', { variant_id: variant.id, quantity: 1 }); setMessage('Добавлено в корзину') } catch (err) { setError(err.message) }
  }
  return <div className="purchase"><div className="purchase-buttons"><button disabled={loading || busy || variant.stock < 1} onClick={add}>{busy ? 'Добавляем…' : variant.stock < 1 ? 'Нет в наличии' : 'В корзину'}</button>{favorite}</div>{message && <p className="stock" role="status">{message} · <a href="/cart">Перейти <Arrow /></a></p>}{error && <p className="validation" role="alert">{error}</p>}</div>
}

function ConsentCheckbox({ privacyConsent, setPrivacyConsent }) {
  return <div className="consent-block"><label className="consent-label"><input type="checkbox" checked={privacyConsent} onChange={event => setPrivacyConsent(event.target.checked)} /><span>Даю <a href="/consent" target="_blank" rel="noopener noreferrer">согласие на обработку персональных данных</a></span></label><div className="consent-links"><a href="/privacy" target="_blank" rel="noopener noreferrer">Политика обработки персональных данных <Arrow direction="up-right" /></a></div></div>
}

function CartImage({ item }) {
  const [broken, setBroken] = useState(false)
  return <a className="basket-image" href={item.product_slug ? `/products/${item.product_slug}` : '/catalog'} aria-label={item.product_name}>{item.image_url && !broken ? <img src={item.image_url} alt={item.product_name} onError={() => setBroken(true)} /> : <span>Нет фото</span>}</a>
}

function CartRecommendations({ items, renderProduct }) {
  const [products, setProducts] = useState([])
  const [page, setPage] = useState(0)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const pool = []
        let url = '/api/products/?in_stock=true'
        while (url && pool.length < 120) {
          const data = await apiRequest(url)
          pool.push(...data.results)
          // Keep pagination on our own origin (API may return absolute links).
          const next = data.next ? new URL(data.next, window.location.origin) : null
          url = next ? next.pathname + next.search : null
        }
        for (let i = pool.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1))
          ;[pool[i], pool[j]] = [pool[j], pool[i]]
        }
        if (active) { setProducts(pool); setError(false) }
      } catch { if (active) setError(true) }
    }
    load()
    return () => { active = false }
  }, [retry])
  const eligible = products.filter(product => !items.some(item => item.product_slug === product.slug))
  const pages = Math.ceil(eligible.length / 5)
  const current = pages ? page % pages : 0
  if (!eligible.length && !error) return null
  return <section className="cart-recommendations" aria-labelledby="cart-recommendations-title"><div className="recommendations-heading"><h2 id="cart-recommendations-title">Вам может понравиться</h2></div>{error ? <p role="status">Не удалось загрузить рекомендации. <button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>Повторить</button></p> : <div className="recommendations-carousel"><button type="button" className="recommendations-arrow" aria-label="Предыдущие рекомендуемые товары" disabled={pages <= 1} onClick={() => setPage((current - 1 + pages) % pages)}><Arrow direction="left" /></button><div className="product-grid recommendations-grid">{eligible.slice(current * 5, current * 5 + 5).map(product => renderProduct(product))}</div><button type="button" className="recommendations-arrow" aria-label="Следующие рекомендуемые товары" disabled={pages <= 1} onClick={() => setPage((current + 1) % pages)}><Arrow /></button></div>}</section>
}

export function CartPage({ renderProduct }) {
  const { cart, loading, busy, error, refresh, mutate } = useCart()
  async function change(item, quantity) { try { await mutate(`/api/cart/items/${item.variant_id}/`, 'PATCH', { quantity: Math.min(quantity, item.stock) }) } catch { /* context displays validation */ } }
  async function remove(item) { try { await mutate(`/api/cart/items/${item.variant_id}/`, 'DELETE') } catch { /* context displays validation */ } }
  return <><a className="back" href="/"><Arrow direction="left" /> В каталог</a><h1 className="page-title">Корзина</h1>
    {error && <div role="alert" className="validation"><p>{error}</p><button onClick={() => { refresh().catch(() => {}) }} disabled={busy}>Обновить корзину</button></div>}
    {loading ? <p className="empty" role="status">Загружаем корзину…</p> : cart.items.length === 0 ? <div className="empty"><h2>Ваша корзина пока пуста</h2><p>Выберите технику в каталоге.</p><a className="button-link" href="/">В каталог <Arrow /></a></div> : <div className="basket-layout"><div>{cart.items.map(item => <article className="basket-item" key={item.variant_id}><div className="basket-product"><CartImage key={item.image_url} item={item} /><div className="basket-product-info"><a className="item-name" href={`/products/${item.product_slug}`}>{item.product_name}</a><p className="muted">{[item.color, item.memory].filter(Boolean).join(' / ')}</p><p>{money(item.price)}</p>{!item.is_available && <p className="validation">Недоступно в выбранном количестве. Уменьшите количество или удалите товар.</p>}</div></div><div className="item-controls"><strong className="item-total">{money(item.line_total)}</strong><div className="quantity"><button aria-label={`Уменьшить количество ${item.product_name}`} disabled={busy || item.quantity <= 1 || item.stock < 1} onClick={() => change(item, item.quantity - 1)}>−</button><span>{item.quantity}</span><button aria-label={`Увеличить количество ${item.product_name}`} disabled={busy || item.quantity >= item.stock || item.quantity >= 99} onClick={() => change(item, item.quantity + 1)}>+</button><button className="remove-item" aria-label={`Удалить ${item.product_name} из корзины`} title="Удалить из корзины" disabled={busy} onClick={() => remove(item)}><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg></button></div></div></article>)}</div><aside className="summary"><h2>Ваш заказ</h2><p>Товаров <span>{cart.count}</span></p><p className="summary-total">Итого <strong>{money(cart.total)}</strong></p>{cart.items.every(item => item.is_available) && !busy ? <a className="button-link" href="/checkout">Оформить заказ <Arrow /></a> : <p className="muted">Проверьте доступность товаров перед оформлением.</p>}<p className="muted">Демонстрационный заказ без оплаты и доставки.</p></aside></div>}
    <CartRecommendations items={cart.items} renderProduct={renderProduct} />
  </>
}

function checkoutToken() {
  let token = sessionStorage.getItem('shop-checkout-token')
  if (!token) { token = crypto.randomUUID(); sessionStorage.setItem('shop-checkout-token', token) }
  return token
}

export function CheckoutPage() {
  const { cart, loading, busy, setCart, refresh } = useCart()
  const [privacyConsent, setPrivacyConsent] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '8000000000', email: 'test@test.ru', address: 'Адрес кв. тестовая дом. тестовый', comment: 'Тестовый комментарий' })
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [order, setOrder] = useState(null)
  async function submit(event) {
    event.preventDefault(); if (sending) return
    if (!privacyConsent) { setError('Для оформления заказа необходимо согласие на обработку персональных данных.'); return }
    setSending(true); setError('')
    try {
      const result = await apiRequest('/api/orders/', { method: 'POST', body: { ...form, checkout_token: checkoutToken(), privacy_consent: privacyConsent, privacy_policy_version: PRIVACY_POLICY_VERSION } })
      setOrder(result); setCart(emptyCart); setPrivacyConsent(false); sessionStorage.removeItem('shop-checkout-token')
    } catch (err) {
      setError(err.message)
      // Keep the basket and token for retry when the order response was lost.
      if (err.status === 400 || err.status === 409) await refresh().catch(() => {})
    } finally { setSending(false) }
  }
  if (order) return <section className="order-success"><p className="eyebrow">СПАСИБО ЗА ПОКУПКУ</p><h1 className="page-title">Заказ № {order.number || order.id} оформлен</h1><p>Сумма заказа: <strong>{money(order.total)}</strong></p><p>Демонстрационный заказ сохранён. Оплата и доставка не выполняются.</p><OrderLink token={order.tracking_token} /><a className="button-link" href="/">Вернуться в каталог <Arrow /></a></section>
  if (loading) return <p role="status" className="empty">Загружаем корзину…</p>
  if (!cart.items.length) return <div className="empty"><h2>Нет товаров для оформления</h2><a className="back" href="/cart">Вернуться в корзину <Arrow /></a></div>
  const fields = [{ key: 'name', label: 'Никнейм', autoComplete: 'off', maxLength: 150 }, { key: 'phone', label: 'Телефон', type: 'tel', autoComplete: 'tel', maxLength: 30 }, { key: 'email', label: 'Email', type: 'email', autoComplete: 'email', maxLength: 254 }, { key: 'address', label: 'Адрес доставки', autoComplete: 'street-address', maxLength: 2000 }]
  return <><a className="back" href="/cart"><Arrow direction="left" /> В корзину</a><h1 className="page-title">Оформление заказа</h1><div className="basket-layout"><form className="checkout-form" autoComplete="off" onSubmit={submit}><div className="legal-notice demo-notice">Демонстрационный заказ. Используйте вымышленный никнейм; телефон, почта, адрес и комментарий заполнены тестовыми значениями.</div>{fields.map(field => <label key={field.key}>{field.label}<input required type={field.type || 'text'} autoComplete={field.key === 'name' ? 'off' : field.autoComplete} readOnly={field.key !== 'name'} maxLength={field.maxLength} value={form[field.key]} onChange={event => setForm({ ...form, [field.key]: event.target.value })} disabled={sending} /></label>)}<label>Комментарий<textarea readOnly maxLength={2000} rows="4" value={form.comment} onChange={event => setForm({ ...form, comment: event.target.value })} disabled={sending} /></label><ConsentCheckbox privacyConsent={privacyConsent} setPrivacyConsent={setPrivacyConsent} /><div className="checkout-actions"><button type="submit" disabled={sending || busy || !cart.items.every(item => item.is_available)}>{sending ? 'Оформляем…' : 'Подтвердить заказ'}</button><div className="checkout-feedback validation" role="alert">{error}</div></div><p className="muted">Онлайн-оплата не требуется.</p></form><aside className="summary"><h2>В заказе</h2>{cart.items.map(item => <p key={item.variant_id}>{item.product_name} × {item.quantity}<span>{money(item.line_total)}</span></p>)}<p className="summary-total">Итого <strong>{money(cart.total)}</strong></p><p className="muted">Окончательные цены и наличие проверяются при оформлении.</p></aside></div></>
}


import { useEffect, useRef, useState } from 'react'
import Arrow from './Arrow'
import { fetchOrderStatus, ORDER_REFRESH_INTERVAL } from './orderPolling'
import { money } from './cartState'

const descriptions = {
  new: 'Заказ сохранён и ожидает обработки.',
  processing: 'Менеджер обрабатывает заказ.',
  completed: 'Обработка заказа завершена.',
  cancelled: 'Заказ отменён.',
}

export function OrderLink({ token }) {
  const [message, setMessage] = useState('')
  const path = `/orders/${token}`
  const url = new URL(path, window.location.origin).href
  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setMessage('Ссылка скопирована')
    } catch {
      setMessage('Не удалось скопировать автоматически. Скопируйте адрес через меню ссылки.')
    }
  }
  return <div className="order-link"><p>Сохраните ссылку, чтобы вернуться к заказу без регистрации. Любой, у кого есть ссылка, сможет увидеть его состав и статус.</p><div className="order-link-row"><a className="order-tracking-link" href={path} aria-label={`Открыть статус заказа: ${url}`}>{url}</a><button className="copy-order-link" type="button" onClick={copy} aria-label="Копировать ссылку на заказ" title="Копировать ссылку"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg></button></div><p role="status">{message}</p></div>
}

export default function OrderStatus({ token }) {
  const [state, setState] = useState({ order: null, loading: true, fetching: false, error: '', updated: null })
  const [remaining, setRemaining] = useState(0)
  const refresh = useRef(null)
  useEffect(() => {
    let active = true
    let fetching = false
    let nextAllowed = 0
    let terminal = false
    async function load() {
      if (!active || fetching || Date.now() < nextAllowed) return
      fetching = true
      setState(previous => ({ ...previous, fetching: true }))
      try {
        const order = await fetchOrderStatus(token)
        terminal = ['completed', 'cancelled'].includes(order.status)
        if (active) setState({ order, loading: false, fetching: false, error: '', updated: new Date() })
      } catch (error) {
        if (active) setState(previous => ({ ...previous, loading: false, fetching: false, error: error.status === 404 ? 'Заказ не найден. Проверьте, что ссылка скопирована полностью.' : error.message }))
      } finally {
        fetching = false
        nextAllowed = Date.now() + ORDER_REFRESH_INTERVAL
        if (active) setRemaining(ORDER_REFRESH_INTERVAL / 1000)
      }
    }
    refresh.current = load
    load()
    const timer = window.setInterval(() => {
      if (!active) return
      setRemaining(Math.max(0, Math.ceil((nextAllowed - Date.now()) / 1000)))
      if (!terminal && document.visibilityState === 'visible') load()
    }, 1000)
    return () => { active = false; refresh.current = null; window.clearInterval(timer) }
  }, [token])
  const { order, loading, fetching, error, updated } = state
  const terminal = order && ['completed', 'cancelled'].includes(order.status)
  const refreshLabel = fetching ? 'Обновляем статус…' : remaining > 0 ? `Обновить статус можно через ${remaining} с` : 'Обновить статус заказа'
  return <section className="order-status">
    <a className="back" href="/catalog"><Arrow direction="left" /> В каталог</a>
    <div className="order-heading">
      <h1 className="page-title">{order ? `Заказ № ${order.number}` : 'Статус заказа'}</h1>
      <div className="order-heading-actions">
        {order && <span className={`order-status-badge status-${order.status}`} role="status" title={descriptions[order.status]}>{order.status_label}</span>}
        <button className="refresh-order-status" type="button" onClick={() => refresh.current?.()} disabled={fetching || remaining > 0} aria-label={refreshLabel} title={refreshLabel} aria-busy={fetching}><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d="M3 12a9 9 0 0 1 15.36-6.36L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.36 6.36L3 16M8 16H3v5" /></svg></button>
      </div>
    </div>
    {loading && <p role="status">Загружаем заказ…</p>}
    {error && <p className="validation" role="alert">{error}</p>}
    {updated && <p className="muted order-updated">Проверено в {updated.toLocaleTimeString('ru-RU')}. {terminal ? 'Заказ закрыт. Автообновление остановлено.' : 'Автообновление раз в 30 секунд, пока вкладка открыта.'}</p>}
    {!loading && <p className="muted order-refresh-hint">{fetching ? 'Обновляем статус…' : remaining > 0 ? `Следующее обновление доступно через ${remaining} с.` : 'Можно обновить статус.'}</p>}
    {order && <><p className="muted">Оформлен {new Date(order.created_at).toLocaleString('ru-RU')}</p><div className="basket-layout"><div><h2>Состав заказа</h2>{order.items.map((item, index) => <article className="basket-item" key={index}><div><h3 className="item-name">{item.product_name}</h3><p className="muted">{[item.color, item.memory].filter(Boolean).join(' / ')}</p><p>{money(item.unit_price)} × {item.quantity}</p></div><strong className="item-total">{money(item.line_total)}</strong></article>)}</div><aside className="summary"><h2>Ваш заказ</h2><p className="summary-total">Итого <strong>{money(order.total)}</strong></p><p className="muted">Демонстрационный заказ. Оплата и доставка не выполняются.</p></aside></div><OrderLink token={token} /></>}
  </section>
}

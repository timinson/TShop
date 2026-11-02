import Arrow from './Arrow'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { money, useCart } from './cartState'

export default function QuickAdd({ product, filters, favorite = null }) {
  const { cart, loading, busy, mutate } = useCart()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const dialog = useRef(null)
  const trigger = useRef(null)
  const titleId = useId()
  useEffect(() => {
    if (!open || !dialog.current) return
    const element = dialog.current
    const opener = trigger.current
    element.showModal()
    return () => { element.close(); if (opener?.isConnected) opener.focus() }
  }, [open])
  const variants = product.variants.filter(item => item.stock > 0
    && (!filters.color || item.color === filters.color)
    && (!filters.memory || item.memory === filters.memory)
    && (filters.min_price === '' || Number(item.price) >= Number(filters.min_price))
    && (filters.max_price === '' || Number(item.price) <= Number(filters.max_price)))
  const quantity = id => cart.items.find(item => item.variant_id === id)?.quantity || 0
  const full = item => quantity(item.id) >= Math.min(item.stock, 99)
  const variant = variants.find(item => item.id === selected) || variants.find(item => !full(item)) || variants[0]
  const needsChoice = variants.length > 1 || (variant && Number(variant.price) !== Number(product.min_price))
  const disabled = loading || busy || !variants.length || variants.every(full)
  async function add(item) {
    setError(''); setMessage('')
    try {
      await mutate('/api/cart/', 'POST', { variant_id: item.id, quantity: 1 })
      setMessage(`Добавлено: ${[item.color, item.memory].filter(Boolean).join(' / ')}`)
      setOpen(false)
    } catch (err) { setError(err.message) }
  }
  return <div className="quick-add">
    <div className="quick-add-toolbar"><span className={variants.length ? 'stock' : 'muted'}>{variants.length ? 'В наличии' : 'Нет в наличии'}</span><div className="quick-add-buttons">{favorite}<button ref={trigger} type="button" className="quick-add-icon" aria-label={`В корзину: ${product.name}`} title={!variants.length ? 'Нет доступных вариантов' : variants.every(full) ? 'Доступное количество уже в корзине' : 'В корзину'} disabled={disabled} aria-expanded={needsChoice ? open : undefined} onClick={() => { if (!needsChoice) add(variants[0]); else { setOpen(value => !value); setError(''); setMessage('') } }}><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m8 4-4 6m12-6 4 6M3 10h18l-2 10H5L3 10ZM9 14v3m6-3v3" /></svg></button></div></div>
    {open && variant && createPortal(<dialog ref={dialog} className="variant-dialog" aria-labelledby={titleId} onCancel={() => setOpen(false)} onClose={() => setOpen(false)} onClick={event => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) setOpen(false)
    }}>
      <div className="variant-dialog-heading"><div><p className="eyebrow">ВЫБЕРИТЕ ВАРИАНТ</p><h2 id={titleId}>{product.name}</h2></div><button type="button" className="variant-dialog-close" aria-label="Закрыть выбор варианта" onClick={() => setOpen(false)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div>
      <div className="quick-add-panel">
      <label>Вариант товара<select aria-label={`Вариант для ${product.name}`} value={variant.id} onChange={event => setSelected(Number(event.target.value))}>{variants.map(item => <option key={item.id} value={item.id} disabled={full(item)}>{[item.color, item.memory].filter(Boolean).join(' / ')} — {money(item.price)}{full(item) ? ' — уже в корзине' : ''}</option>)}</select></label>
      <div className="quick-add-actions"><button type="button" disabled={busy || loading || full(variant)} onClick={() => add(variant)}>Добавить</button><button type="button" className="text-button" onClick={() => setOpen(false)}>Закрыть</button></div>
      {error && <p className="quick-add-message validation" role="alert">{error}</p>}
      </div>
    </dialog>, document.body)}
    {message && <p className="quick-add-message stock" role="status">{message} · <a href="/cart">В корзину <Arrow /></a></p>}
    {error && !open && <p className="quick-add-message validation" role="alert">{error}</p>}
  </div>
}

import { useEffect, useState } from 'react'
import { FavoritesContext, useFavorites } from './favoritesState'

const key = 'shop:favorites:v1'
function readFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem(key) || '[]')
    return Array.isArray(value) ? [...new Set(value.filter(id => Number.isSafeInteger(id) && id > 0))].slice(0, 200) : []
  } catch { return [] }
}
export function FavoritesProvider({ children }) {
  const [ids, setIds] = useState(readFavorites)
  const [storageError, setStorageError] = useState('')
  useEffect(() => {
    const sync = event => { if (event.key === key || event.key === null) setIds(readFavorites()) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  function toggle(id) {
    const next = ids.includes(id) ? ids.filter(item => item !== id) : [...ids, id].slice(-200)
    setIds(next)
    try { localStorage.setItem(key, JSON.stringify(next)); setStorageError('') }
    catch { setStorageError('Браузер не разрешил сохранить избранное. Оно доступно до перезагрузки страницы.') }
  }
  return <FavoritesContext.Provider value={{ ids, toggle }}>{children}{storageError && <p className="favorites-warning" role="status">{storageError}</p>}</FavoritesContext.Provider>
}
export function Heart({ filled = false }) {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" /></svg>
}
export function FavoriteButton({ product }) {
  const { ids, toggle } = useFavorites()
  const active = ids.includes(product.id)
  return <button type="button" className={`favorite-button${active ? ' active' : ''}`} aria-label={`${active ? 'Убрать из избранного' : 'В избранное'}: ${product.name}`} aria-pressed={active} title={active ? 'Убрать из избранного' : 'В избранное'} onClick={() => toggle(product.id)}><Heart filled={active} /></button>
}

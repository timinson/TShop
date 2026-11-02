import { apiRequest } from './api.js'

export const ORDER_REFRESH_INTERVAL = 30000
const MAX_CACHED_ORDERS = 32

export function createOrderStatusLoader(request, now = Date.now) {
  const cache = new Map()
  return function load(token) {
    const existing = cache.get(token)
    if (existing && now() < existing.expiresAt) return existing.promise

    const entry = { expiresAt: Infinity, promise: null }
    // Assign the entry before invoking the transport, including synchronous errors.
    entry.promise = Promise.resolve().then(() => request(`/api/orders/${token}/`)).then(
      data => {
        entry.expiresAt = now() + ORDER_REFRESH_INTERVAL
        return data
      },
      error => {
        entry.expiresAt = now() + ORDER_REFRESH_INTERVAL
        throw error
      },
    )
    cache.delete(token)
    cache.set(token, entry)
    if (cache.size > MAX_CACHED_ORDERS) cache.delete(cache.keys().next().value)
    return entry.promise
  }
}

export const fetchOrderStatus = createOrderStatusLoader(apiRequest)

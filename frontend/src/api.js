export async function apiRequest(url, { method = 'GET', body } = {}) {
  const headers = {}
  if (method !== 'GET') {
    if (!document.cookie.split('; ').some(cookie => cookie.startsWith('csrftoken='))) {
      const response = await fetch('/api/cart/', { credentials: 'same-origin' })
      if (!response.ok) throw new Error('Не удалось подготовить запрос. Обновите страницу.')
    }
    const token = document.cookie.split('; ').find(cookie => cookie.startsWith('csrftoken='))?.split('=')[1]
    headers['X-CSRFToken'] = decodeURIComponent(token || '')
    headers['Content-Type'] = 'application/json'
  }
  const response = await fetch(url, { method, headers, credentials: 'same-origin', ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  if (response.status === 503) {
    const error = new Error('Сайт обновляется. Пожалуйста, попробуйте через несколько минут.')
    error.status = 503
    throw error
  }
  let data
  try { data = await response.json() } catch { throw new Error('Сервер вернул неожиданный ответ. Обновите страницу и попробуйте снова.') }
  if (!response.ok) {
    const labels = { name: 'Никнейм', phone: 'Телефон', email: 'Email', address: 'Адрес', quantity: 'Количество', privacy_consent: 'Согласие', privacy_policy_version: 'Версия политики', detail: '', non_field_errors: '' }
    const message = typeof data === 'object' ? Object.entries(data).map(([key, value]) => `${labels[key] ?? key}${labels[key] === '' ? '' : ': '}${Array.isArray(value) ? value.join(' ') : typeof value === 'string' ? value : JSON.stringify(value)}`).join(' ') : String(data)
    const error = new Error(message || 'Не удалось выполнить действие.')
    error.status = response.status
    throw error
  }
  return data
}

import { afterEach, beforeEach, test } from 'node:test'
import assert from 'node:assert/strict'
import { installNavigation, isShopPath, navigate, NAVIGATION_EVENT } from './navigation.js'

let cleanup
beforeEach(() => {
  const windowEvents = new EventTarget()
  globalThis.window = Object.assign(windowEvents, {
    location: new URL('http://localhost/'),
    history: {
      pushState(_state, _title, url) { window.location = new URL(url, window.location.origin) },
      replaceState(_state, _title, url) { window.location = new URL(url, window.location.origin) },
    },
  })
  globalThis.document = new EventTarget()
})
afterEach(() => { cleanup?.(); cleanup = undefined; delete globalThis.window; delete globalThis.document })

test('clean navigation keeps query parameters and announces route changes', () => {
  let count = 0
  window.addEventListener(NAVIGATION_EVENT, () => count++)
  navigate('/catalog?category=iphone&q=pro')
  assert.equal(window.location.pathname, '/catalog')
  assert.equal(window.location.search, '?category=iphone&q=pro')
  assert.equal(count, 1)
})
test('old hash links migrate without an extra history entry', () => {
  window.location = new URL('http://localhost/#/catalog?category=iphone')
  window.history.pushState = () => assert.fail('migration must replace history')
  cleanup = installNavigation()
  assert.equal(window.location.href, 'http://localhost/catalog?category=iphone')
})
test('back and forward trigger application navigation', () => {
  cleanup = installNavigation()
  let count = 0
  window.addEventListener(NAVIGATION_EVENT, () => count++)
  window.dispatchEvent(new Event('popstate'))
  assert.equal(count, 1)
})
test('server routes and external destinations are never intercepted', () => {
  for (const path of ['/api/cart/', '/admin/', '/media/photo.jpg', '/static/admin.css', '/assets/app.js', '//example.org/']) assert.equal(isShopPath(path), false)
  navigate('https://example.org/catalog')
  navigate('/admin/')
  assert.equal(window.location.href, 'http://localhost/')
})
test('legacy hashes cannot redirect to a different origin', () => {
  window.location = new URL('http://localhost/#//example.org/catalog')
  cleanup = installNavigation()
  assert.equal(window.location.origin, 'http://localhost')
  assert.equal(window.location.pathname, '/')
})

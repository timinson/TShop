import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createOrderStatusLoader, ORDER_REFRESH_INTERVAL } from './orderPolling.js'

test('simultaneous mounts share one pending request and cooldown starts at completion', async () => {
  let clock = 0
  let finish
  let requests = 0
  const load = createOrderStatusLoader(() => {
    requests++
    return new Promise(resolve => { finish = resolve })
  }, () => clock)
  const first = load('order-a')
  assert.equal(load('order-a'), first)
  await Promise.resolve()
  assert.equal(requests, 1)
  clock = ORDER_REFRESH_INTERVAL * 2
  assert.equal(load('order-a'), first)
  finish({ status: 'new' })
  await first
  clock += ORDER_REFRESH_INTERVAL - 1
  assert.equal(load('order-a'), first)
  clock++
  assert.notEqual(load('order-a'), first)
  await Promise.resolve()
  assert.equal(requests, 2)
  finish({ status: 'processing' })
})

test('failed requests also block repeated transport attempts for 30 seconds', async () => {
  let clock = 0
  let requests = 0
  const error = new Error('offline')
  const load = createOrderStatusLoader(() => {
    requests++
    throw error
  }, () => clock)
  const first = load('order-a')
  await assert.rejects(first, error)
  clock = ORDER_REFRESH_INTERVAL - 1
  assert.equal(load('order-a'), first)
  await assert.rejects(load('order-a'), error)
  assert.equal(requests, 1)
  clock++
  await assert.rejects(load('order-a'), error)
  assert.equal(requests, 2)
})

test('separate orders are isolated and revisiting a recent order reuses its result', async () => {
  const paths = []
  const load = createOrderStatusLoader(path => {
    paths.push(path)
    return path
  }, () => 0)
  const first = load('order-a')
  await first
  await load('order-b')
  assert.equal(load('order-a'), first)
  assert.deepEqual(paths, ['/api/orders/order-a/', '/api/orders/order-b/'])
})

test('order cache retains at most the latest 32 entries', async () => {
  let requests = 0
  const load = createOrderStatusLoader(() => ++requests, () => 0)
  for (let index = 0; index < 33; index++) await load(`order-${index}`)
  await load('order-1')
  assert.equal(requests, 33)
  await load('order-0')
  assert.equal(requests, 34)
})

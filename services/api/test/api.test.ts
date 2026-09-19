import test from 'node:test'
import assert from 'node:assert/strict'
import type { Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { createApp } from '../src/app.js'

let server: Server
let baseUrl: string

test.before(async () => {
  const app = createApp()
  await new Promise<void>((resolve) => {
    server = app.listen(0, () => {
      const addr = server.address() as AddressInfo
      baseUrl = `http://localhost:${addr.port}`
      resolve()
    })
  })
})

test.after(async () => {
  await new Promise<void>((resolve, reject) => {
    server.close((err) => {
      if (err) reject(err)
      else resolve()
    })
  })
})

test('GET /skills returns list containing skill draft', async () => {
  const res = await fetch(`${baseUrl}/skills`)
  assert.strictEqual(res.status, 200)
  const data = await res.json()
  assert.ok(Array.isArray(data))
  assert.strictEqual(data[0].skillId, 'skill-fragile-mug-001')
})

test('GET /skills/:skillId returns 404 with errorResponse for unknown skill', async () => {
  const res = await fetch(`${baseUrl}/skills/skill-nonexistent`)
  assert.strictEqual(res.status, 404)
  const data = await res.json()
  assert.strictEqual(data.schemaVersion, 1)
  assert.strictEqual(data.error.code, 'RESOURCE_NOT_FOUND')
})

test('POST unimplemented routes returns 501 with safe error response', async () => {
  const res = await fetch(`${baseUrl}/skills/skill-fragile-mug-001/analyze`, {
    method: 'POST'
  })
  assert.strictEqual(res.status, 501)
  const data = await res.json()
  assert.strictEqual(data.schemaVersion, 1)
  assert.strictEqual(data.error.code, 'NOT_IMPLEMENTED')
})

test('POST /skills/:skillId/approve transitions draft to approved', async () => {
  const res = await fetch(`${baseUrl}/skills/skill-fragile-mug-001/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approvedBy: 'supervisor-test' })
  })
  assert.strictEqual(res.status, 200)
  const data = await res.json()
  assert.strictEqual(data.status, 'approved')
  assert.strictEqual(data.version, 1)
  assert.strictEqual(data.approvedBy, 'supervisor-test')
})

test('POST /sessions/:sessionId/checkpoints returns checkpoint result', async () => {
  const res = await fetch(`${baseUrl}/sessions/sess-123/checkpoints?mockVerdict=pass`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      schemaVersion: 1,
      sessionId: 'sess-123',
      stepId: 'step-003',
      checkpointImageKey: 'sessions/sess-123/checkpoints/step-003.jpg'
    })
  })
  assert.strictEqual(res.status, 200)
  const data = await res.json()
  assert.strictEqual(data.schemaVersion, 1)
  assert.strictEqual(data.verdict, 'pass')
  assert.strictEqual(data.sessionId, 'sess-123')
})

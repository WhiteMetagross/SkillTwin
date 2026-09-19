import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { PdfExportService } from '../src/index.js'
import type { SkillPackage } from '@skilltwin/contracts'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

function loadFixture(name: string): SkillPackage {
  const fixturePath = path.resolve(dirname, '../../../packages/contracts/fixtures', name)
  return JSON.parse(fs.readFileSync(fixturePath, 'utf8')) as SkillPackage
}

test('PdfExportService rejects draft skill package', () => {
  const draft = loadFixture('skillPackage.valid.json')
  const service = new PdfExportService()

  assert.throws(() => {
    service.exportSop(draft)
  }, /Draft skills cannot be exported to PDF SOP/)
})

test('PdfExportService exports approved skill package', () => {
  const draft = loadFixture('skillPackage.valid.json')
  const approvedSkill: SkillPackage = {
    ...draft,
    status: 'approved',
    version: 1,
    approvedBy: 'supervisor-jane',
    approvedAt: '2026-09-19T10:00:00Z'
  }

  const service = new PdfExportService()
  const result = service.exportSop(approvedSkill)

  assert.strictEqual(result.skillId, approvedSkill.skillId)
  assert.strictEqual(result.version, 1)
  assert.strictEqual(result.exportKey, 'skills/skill-fragile-mug-001/versions/v1/exports/sop.pdf')
  assert.ok(result.pageCount > 0)
})

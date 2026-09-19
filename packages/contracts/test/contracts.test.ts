import test from 'node:test'
import assert from 'node:assert/strict'
import {
  defaultSchemaRegistry,
  validateTimestamps,
  validateActionOrder,
  fragilePackingActions
} from '../src/validators.js'
import { runFixtureValidations } from '../src/validateAllFixtures.js'
import type { SkillStep } from '../src/types.js'

test('all valid and invalid fixtures pass their expectations', () => {
  const result = runFixtureValidations()
  assert.strictEqual(result.failed, 0)
  assert.ok(result.passed >= 13)
})

test('validateTimestamps rejects endMs less than or equal to startMs', () => {
  assert.strictEqual(validateTimestamps(100, 200), true)
  assert.strictEqual(validateTimestamps(200, 100), false)
  assert.strictEqual(validateTimestamps(100, 100), false)
  assert.strictEqual(validateTimestamps(-10, 100), false)
})

test('validateActionOrder verifies exact six step template', () => {
  const validSteps: SkillStep[] = fragilePackingActions.map((actionCode, index) => ({
    stepId: `step-${index + 1}`,
    sequence: index + 1,
    actionCode,
    instruction: `Step ${index + 1}`,
    instructionHi: null,
    sourceVideoId: null,
    startMs: null,
    endMs: null,
    referenceFrameKey: null,
    confidence: null,
    policyStatus: 'needsReview',
    policyCitation: null,
    warning: null,
    checkpointRequired: false,
    audioKey: null,
    evidenceObservationIds: []
  }))

  assert.strictEqual(validateActionOrder(validSteps), true)

  const wrongOrderSteps = [...validSteps]
  wrongOrderSteps[0] = { ...validSteps[1], sequence: 1 }
  wrongOrderSteps[1] = { ...validSteps[0], sequence: 2 }
  assert.strictEqual(validateActionOrder(wrongOrderSteps), false)

  const missingStep = validSteps.slice(0, 5)
  assert.strictEqual(validateActionOrder(missingStep), false)
})

test('schemaRegistry rejects unknown fields on assetManifest', () => {
  const result = defaultSchemaRegistry.validate('assetManifest', {
    schemaVersion: 1,
    skillId: 's1',
    workflowType: 'fragilePackingV1',
    title: 'Test',
    unexpectedField: 'forbidden',
    videos: [],
    referenceImages: [],
    documents: [],
    sourceLanguage: 'auto',
    outputLanguages: ['enIN'],
    expectedObjects: [],
    supervisorNotes: null
  })
  assert.strictEqual(result.valid, false)
})

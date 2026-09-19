import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  defaultSchemaRegistry,
  validateActionOrder,
  validateObservationTimestamps,
  validateStepTimestamps
} from './validators.js'
import type { EvidenceBundle, SkillPackage } from './types.js'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)
const fixturesDir = path.resolve(dirname, '../fixtures')

export function runFixtureValidations(): { passed: number, failed: number } {
  defaultSchemaRegistry.loadSchemas()
  const files = fs.readdirSync(fixturesDir)
  let passed = 0
  let failed = 0

  for (const file of files) {
    if (!file.endsWith('.json')) {
      continue
    }

    const fullPath = path.join(fixturesDir, file)
    const content = fs.readFileSync(fullPath, 'utf8')
    const data = JSON.parse(content)

    // Contract name is the first part of the filename, e.g., assetManifest from assetManifest.valid.json
    const schemaKey = file.split('.')[0]
    const isValidFixture = file.includes('.valid.')
    const result = defaultSchemaRegistry.validate(schemaKey, data)

    if (isValidFixture) {
      if (!result.valid) {
        console.error(`Expected ${file} to be valid but failed:`, result.errors)
        failed += 1
      } else {
        // Run semantic validators if applicable
        if (schemaKey === 'evidenceBundle') {
          const bundle = data as EvidenceBundle
          const allTimestampsValid = bundle.observations.every(validateObservationTimestamps)
          if (!allTimestampsValid) {
            console.error(`Semantic validation failed for ${file}: observation endMs <= startMs`)
            failed += 1
            continue
          }
        }
        if (schemaKey === 'skillPackage') {
          const pkg = data as SkillPackage
          const orderValid = validateActionOrder(pkg.steps)
          const allStepTimestampsValid = pkg.steps.every(validateStepTimestamps)
          if (!orderValid || !allStepTimestampsValid) {
            console.error(`Semantic validation failed for ${file}: steps order or timestamp invalid`)
            failed += 1
            continue
          }
        }
        passed += 1
      }
    } else {
      // Invalid fixture must fail schema validation
      if (result.valid) {
        console.error(`Expected ${file} to fail validation but it passed`)
        failed += 1
      } else {
        passed += 1
      }
    }
  }

  return { passed, failed }
}

if (process.argv[1] && process.argv[1].endsWith('validateAllFixtures.ts')) {
  const result = runFixtureValidations()
  console.log(`Validated fixtures: ${result.passed} passed, ${result.failed} failed`)
  if (result.failed > 0) {
    process.exit(1)
  }
}

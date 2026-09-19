import Ajv2020Import from 'ajv/dist/2020.js'
import addFormatsImport from 'ajv-formats'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { ActionCode, Observation, SkillStep } from './types.js'

const Ajv2020 = (Ajv2020Import as any).default || Ajv2020Import
const addFormats = (addFormatsImport as any).default || addFormatsImport

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

export const fragilePackingActions: readonly ActionCode[] = [
  'selectProduct',
  'selectBox',
  'addProtection',
  'placeProduct',
  'sealBox',
  'attachLabel'
] as const

export function validateTimestamps(startMs: number, endMs: number): boolean {
  return Number.isInteger(startMs) && Number.isInteger(endMs) && startMs >= 0 && endMs > startMs
}

export function validateObservationTimestamps(obs: Observation): boolean {
  return validateTimestamps(obs.startMs, obs.endMs)
}

export function validateStepTimestamps(step: SkillStep): boolean {
  if (step.startMs === null && step.endMs === null) {
    return true
  }
  if (step.startMs !== null && step.endMs !== null) {
    return validateTimestamps(step.startMs, step.endMs)
  }
  return false
}

export function validateActionOrder(steps: Array<{ sequence: number, actionCode: string }>): boolean {
  if (steps.length !== 6) {
    return false
  }
  let i = 0
  while (i < 6) {
    const step = steps[i]
    if (step.sequence !== i + 1) {
      return false
    }
    if (step.actionCode !== fragilePackingActions[i]) {
      return false
    }
    i += 1
  }
  return true
}

export class SchemaRegistry {
  private ajv: any
  private schemasLoaded = false

  constructor() {
    this.ajv = new Ajv2020({ allErrors: true, strict: false })
    addFormats(this.ajv)
  }

  public loadSchemas(schemasDir?: string): void {
    if (this.schemasLoaded) {
      return
    }
    const targetDir = schemasDir ?? path.resolve(dirname, '../schemas')
    const files = fs.readdirSync(targetDir)
    for (const file of files) {
      if (file.endsWith('.schema.json')) {
        const fullPath = path.join(targetDir, file)
        const content = fs.readFileSync(fullPath, 'utf8')
        const parsed = JSON.parse(content)
        const schemaKey = file.replace('.schema.json', '')
        this.ajv.addSchema(parsed, schemaKey)
      }
    }
    this.schemasLoaded = true
  }

  public validate(schemaKey: string, data: unknown): { valid: boolean, errors?: string[] } {
    this.loadSchemas()
    const validator = this.ajv.getSchema(schemaKey)
    if (!validator) {
      return { valid: false, errors: [`Schema ${schemaKey} not found`] }
    }
    const valid = Boolean(validator(data))
    if (valid) {
      return { valid: true }
    }
    const errors = (validator.errors ?? []).map((e: any) => `${e.instancePath} ${e.message}`)
    return { valid: false, errors }
  }
}

export const defaultSchemaRegistry = new SchemaRegistry()

export function validateContract(schemaKey: string, data: unknown) {
  return defaultSchemaRegistry.validate(schemaKey, data)
}

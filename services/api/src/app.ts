import cors from 'cors'
import express from 'express'
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import {
  validateContract,
  type CheckpointRequest,
  type CheckpointResult,
  type JobStatus,
  type SkillPackage,
  type SkillStep
} from '@skilltwin/contracts'
import { InMemorySkillRepository, type SkillRepository } from './repository.js'
import {
  authenticate,
  errorResponse,
  requestContext,
  requireRole,
  type RuntimeMode
} from './runtime.js'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

function loadFixture<T>(fixtureFile: string): T {
  const candidate = path.resolve(dirname, '../../../packages/contracts/fixtures', fixtureFile)
  const content = fs.readFileSync(candidate, 'utf8')
  return JSON.parse(content) as T
}

export interface AppOptions {
  mode?: RuntimeMode
  repository?: SkillRepository
}

function sendSkill(res: express.Response, skill: SkillPackage, status = 200): express.Response {
  const validation = validateContract('skillPackage', skill)
  if (!validation.valid) {
    return errorResponse(
      res,
      500,
      'CONTRACT_VIOLATION',
      `Skill response failed contract validation: ${(validation.errors ?? []).join('; ')}`
    )
  }
  return res.status(status).json(skill)
}

function editableStepPatch(body: unknown): Partial<SkillStep> {
  if (!body || typeof body !== 'object') return {}
  const input = body as Record<string, unknown>
  const patch: Partial<SkillStep> = {}
  if (typeof input.instruction === 'string') patch.instruction = input.instruction
  if (typeof input.warning === 'string' || input.warning === null) patch.warning = input.warning
  if (typeof input.checkpointRequired === 'boolean') {
    patch.checkpointRequired = input.checkpointRequired
  }
  return patch
}

export function createApp(options: AppOptions = {}): express.Application {
  const mode = options.mode ?? 'mock'
  const baseSkill = loadFixture<SkillPackage>('skillPackage.valid.json')
  const repository = options.repository ?? new InMemorySkillRepository([baseSkill])
  const currentJob = loadFixture<JobStatus>('jobStatus.valid.json')

  const app = express()
  app.disable('x-powered-by')
  app.use(cors())
  app.use(express.json({ limit: '1mb' }))
  app.use(requestContext())
  app.use(authenticate(mode))

  const notImplemented = (
    res: express.Response,
    message = 'Endpoint not implemented for the selected runtime mode'
  ) => errorResponse(res, 501, 'NOT_IMPLEMENTED', message)

  app.get('/skills', async (_req, res) => res.json(await repository.list()))

  app.post('/skills', requireRole('supervisor'), async (req, res) => {
    const title = typeof req.body?.title === 'string' && req.body.title.trim()
      ? req.body.title.trim()
      : 'Untitled Skill'
    const skill: SkillPackage = {
      ...structuredClone(baseSkill),
      skillId: `skill-${randomUUID()}`,
      title,
      status: 'reviewRequired',
      version: 0,
      approvedBy: null,
      approvedAt: null
    }
    await repository.save(skill)
    return sendSkill(res, skill, 201)
  })

  app.post('/skills/:skillId/assets/presign', requireRole('supervisor'), (req, res) => {
    if (mode !== 'mock') {
      return notImplemented(res, 'Production S3 presigning is not configured')
    }
    const assetId = randomUUID()
    const storageKey = `skills/${req.params.skillId}/source/${assetId}`
    return res.json({
      assetId,
      uploadUrl: `https://mock-bucket.s3.local/${storageKey}`,
      storageKey,
      fileType: typeof req.body?.fileType === 'string' ? req.body.fileType : 'video/mp4',
      expiresInSeconds: 300
    })
  })

  app.post(
    '/skills/:skillId/assets/complete',
    requireRole('supervisor'),
    (_req, res) => notImplemented(res, 'Asset upload completion is not implemented')
  )

  app.post(
    '/skills/:skillId/analyze',
    requireRole('supervisor'),
    (_req, res) => notImplemented(res, 'Step Functions analysis initiation is not implemented')
  )

  app.get('/skills/:skillId/jobs/latest', (req, res) => {
    return res.json({ ...currentJob, skillId: req.params.skillId })
  })

  app.get('/skills/:skillId', async (req, res) => {
    const skill = await repository.get(req.params.skillId)
    if (!skill) {
      return errorResponse(
        res,
        404,
        'RESOURCE_NOT_FOUND',
        `Skill ${req.params.skillId} not found`
      )
    }
    return sendSkill(res, skill)
  })

  app.patch('/skills/:skillId/steps/:stepId', requireRole('supervisor'), async (req, res) => {
    const skillId = String(req.params.skillId)
    const skill = await repository.get(skillId)
    if (!skill) {
      return errorResponse(
        res,
        404,
        'RESOURCE_NOT_FOUND',
        `Skill ${skillId} not found`
      )
    }
    if (skill.status !== 'reviewRequired') {
      return errorResponse(res, 409, 'IMMUTABLE_VERSION', 'Approved skill versions cannot be edited')
    }

    const stepIndex = skill.steps.findIndex((step) => step.stepId === req.params.stepId)
    if (stepIndex === -1) {
      return errorResponse(res, 404, 'STEP_NOT_FOUND', `Step ${req.params.stepId} not found`)
    }

    const updatedStep = { ...skill.steps[stepIndex], ...editableStepPatch(req.body) }
    skill.steps[stepIndex] = updatedStep
    await repository.save(skill)
    return res.json(updatedStep)
  })

  app.post('/skills/:skillId/approve', requireRole('supervisor'), async (req, res) => {
    const skillId = String(req.params.skillId)
    const skill = await repository.get(skillId)
    if (!skill) {
      return errorResponse(
        res,
        404,
        'RESOURCE_NOT_FOUND',
        `Skill ${skillId} not found`
      )
    }
    const approved: SkillPackage = {
      ...skill,
      status: 'approved',
      version: skill.version > 0 ? skill.version + 1 : 1,
      approvedBy: req.identity!.userId,
      approvedAt: new Date().toISOString()
    }
    await repository.save(approved)
    return sendSkill(res, approved)
  })

  app.post('/skills/:skillId/publish', requireRole('supervisor'), async (req, res) => {
    const skillId = String(req.params.skillId)
    const skill = await repository.get(skillId)
    if (!skill) {
      return errorResponse(
        res,
        404,
        'RESOURCE_NOT_FOUND',
        `Skill ${skillId} not found`
      )
    }
    if (skill.status !== 'approved' || skill.version === 0) {
      return errorResponse(res, 400, 'INVALID_STATE', 'Only approved skills can be published')
    }
    const published: SkillPackage = { ...skill, status: 'published' }
    await repository.save(published)
    return sendSkill(res, published)
  })

  app.get('/skills/:skillId/versions/:version', async (req, res) => {
    const skill = await repository.get(req.params.skillId)
    const targetVersion = Number.parseInt(req.params.version, 10)
    if (skill && skill.version === targetVersion) return sendSkill(res, skill)
    return errorResponse(
      res,
      404,
      'VERSION_NOT_FOUND',
      `Version ${req.params.version} for skill ${req.params.skillId} not found`
    )
  })

  app.get('/skills/:skillId/pdf', async (req, res) => {
    const skill = await repository.get(req.params.skillId)
    if (!skill) {
      return errorResponse(
        res,
        404,
        'RESOURCE_NOT_FOUND',
        `Skill ${req.params.skillId} not found`
      )
    }
    if (skill.status === 'reviewRequired' || skill.version === 0) {
      return errorResponse(res, 400, 'DRAFT_NOT_EXPORTABLE', 'Draft skills cannot be exported')
    }
    return res.json({
      exportKey: `skills/${skill.skillId}/versions/v${skill.version}/exports/sop.pdf`,
      skillId: skill.skillId,
      title: skill.title,
      version: skill.version,
      pageCount: 7,
      generatedAt: new Date().toISOString()
    })
  })

  app.post('/skills/:skillId/sessions', async (req, res) => {
    const skill = await repository.get(req.params.skillId)
    if (!skill || skill.status !== 'published') {
      return errorResponse(res, 409, 'SKILL_NOT_PUBLISHED', 'Worker sessions require a published skill')
    }
    return res.status(201).json({
      sessionId: `sess-${randomUUID()}`,
      skillId: skill.skillId,
      version: skill.version,
      workerId: req.identity!.userId,
      startedAt: new Date().toISOString(),
      activeStepId: skill.steps[0].stepId
    })
  })

  app.post('/sessions/:sessionId/checkpoints', (req, res) => {
    const body = req.body as Partial<CheckpointRequest>
    const stepId = body.stepId || 'step-003'
    const verdict = mode === 'mock' ? String(req.query.mockVerdict || 'pass') : 'pass'
    const fixture = verdict === 'fail'
      ? 'checkpointResult.fail.valid.json'
      : verdict === 'uncertain'
        ? 'checkpointResult.uncertain.valid.json'
        : 'checkpointResult.pass.valid.json'
    const result = loadFixture<CheckpointResult>(fixture)
    return res.json({ ...result, sessionId: req.params.sessionId, stepId })
  })

  app.post('/sessions/:sessionId/complete', (req, res) => {
    return res.json({
      sessionId: req.params.sessionId,
      status: 'completed',
      completedAt: new Date().toISOString(),
      stepsVerified: 6,
      checkpointsPassed: 2
    })
  })

  app.use((_req, res) => notImplemented(res))
  return app
}

import express from 'express'
import cors from 'cors'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type {
  CheckpointRequest,
  CheckpointResult,
  ErrorResponse,
  JobStatus,
  SkillPackage
} from '@skilltwin/contracts'

const filename = fileURLToPath(import.meta.url)
const dirname = path.dirname(filename)

function loadFixture<T>(fixtureFile: string): T {
  const candidate = path.resolve(dirname, '../../../packages/contracts/fixtures', fixtureFile)
  const content = fs.readFileSync(candidate, 'utf8')
  return JSON.parse(content) as T
}

export function createApp(): express.Application {
  const app = express()
  app.use(cors())
  app.use(express.json())

  // In memory state initialized from contracts fixtures
  const baseSkill = loadFixture<SkillPackage>('skillPackage.valid.json')
  let currentSkill: SkillPackage = { ...baseSkill }
  let currentJob = loadFixture<JobStatus>('jobStatus.valid.json')

  const createRequestId = (): string => `req-${Date.now()}`

  const notImplemented = (res: express.Response, message = 'Endpoint not implemented in mock skeleton') => {
    const errorBody: ErrorResponse = {
      schemaVersion: 1,
      requestId: createRequestId(),
      error: {
        code: 'NOT_IMPLEMENTED',
        message
      }
    }
    return res.status(501).json(errorBody)
  }

  app.get('/skills', (_req, res) => {
    return res.json([currentSkill])
  })

  app.post('/skills', (req, res) => {
    const skillId = req.body?.skillId || `skill-${Date.now()}`
    const title = req.body?.title || 'Untitled Skill'
    currentSkill = {
      ...baseSkill,
      skillId,
      title,
      status: 'reviewRequired',
      version: 0,
      approvedBy: null,
      approvedAt: null
    }
    return res.status(201).json(currentSkill)
  })

  app.post('/skills/:skillId/assets/presign', (req, res) => {
    const { skillId } = req.params
    const fileType = req.body?.fileType || 'video/mp4'
    const fileName = req.body?.fileName || 'upload.mp4'
    return res.json({
      uploadUrl: `https://mock-bucket.s3.local/skills/${skillId}/source/${fileName}`,
      storageKey: `skills/${skillId}/source/${fileName}`,
      fileType
    })
  })

  app.post('/skills/:skillId/assets/complete', (_req, res) => {
    return notImplemented(res, 'Asset upload completion trigger not implemented in mock')
  })

  app.post('/skills/:skillId/analyze', (_req, res) => {
    return notImplemented(res, 'Step Functions analysis initiation not implemented in mock')
  })

  app.get('/skills/:skillId/jobs/latest', (req, res) => {
    const { skillId } = req.params
    return res.json({
      ...currentJob,
      skillId
    })
  })

  app.get('/skills/:skillId', (req, res) => {
    const { skillId } = req.params
    if (skillId !== currentSkill.skillId) {
      const error: ErrorResponse = {
        schemaVersion: 1,
        requestId: createRequestId(),
        error: {
          code: 'RESOURCE_NOT_FOUND',
          message: `Skill ${skillId} not found`
        }
      }
      return res.status(404).json(error)
    }
    return res.json(currentSkill)
  })

  app.patch('/skills/:skillId/steps/:stepId', (req, res) => {
    const { skillId, stepId } = req.params
    if (skillId !== currentSkill.skillId) {
      const error: ErrorResponse = {
        schemaVersion: 1,
        requestId: createRequestId(),
        error: {
          code: 'RESOURCE_NOT_FOUND',
          message: `Skill ${skillId} not found`
        }
      }
      return res.status(404).json(error)
    }

    const stepIndex = currentSkill.steps.findIndex((s) => s.stepId === stepId)
    if (stepIndex === -1) {
      const error: ErrorResponse = {
        schemaVersion: 1,
        requestId: createRequestId(),
        error: {
          code: 'STEP_NOT_FOUND',
          message: `Step ${stepId} not found`
        }
      }
      return res.status(404).json(error)
    }

    const updatedStep = {
      ...currentSkill.steps[stepIndex],
      ...req.body,
      stepId,
      sequence: currentSkill.steps[stepIndex].sequence,
      actionCode: currentSkill.steps[stepIndex].actionCode
    }

    currentSkill.steps[stepIndex] = updatedStep
    return res.json(updatedStep)
  })

  app.post('/skills/:skillId/approve', (req, res) => {
    const { skillId } = req.params
    const approver = req.body?.approvedBy || 'supervisor-default'
    currentSkill = {
      ...currentSkill,
      skillId,
      status: 'approved',
      version: currentSkill.version > 0 ? currentSkill.version + 1 : 1,
      approvedBy: approver,
      approvedAt: new Date().toISOString()
    }
    return res.json(currentSkill)
  })

  app.post('/skills/:skillId/publish', (req, res) => {
    const { skillId } = req.params
    if (currentSkill.status !== 'approved' || currentSkill.version === 0) {
      const error: ErrorResponse = {
        schemaVersion: 1,
        requestId: createRequestId(),
        error: {
          code: 'INVALID_STATE',
          message: 'Only approved skills can be published'
        }
      }
      return res.status(400).json(error)
    }
    currentSkill = {
      ...currentSkill,
      skillId,
      status: 'published'
    }
    return res.json(currentSkill)
  })

  app.get('/skills/:skillId/versions/:version', (req, res) => {
    const { skillId, version } = req.params
    const targetVersion = parseInt(version, 10)
    if (currentSkill.skillId === skillId && currentSkill.version === targetVersion) {
      return res.json(currentSkill)
    }
    const error: ErrorResponse = {
      schemaVersion: 1,
      requestId: createRequestId(),
      error: {
        code: 'VERSION_NOT_FOUND',
        message: `Version ${version} for skill ${skillId} not found`
      }
    }
    return res.status(404).json(error)
  })

  app.get('/skills/:skillId/pdf', (req, res) => {
    const { skillId } = req.params
    if (currentSkill.status === 'reviewRequired' || currentSkill.version === 0) {
      const error: ErrorResponse = {
        schemaVersion: 1,
        requestId: createRequestId(),
        error: {
          code: 'DRAFT_NOT_EXPORTABLE',
          message: 'Draft skills cannot be exported to PDF SOP'
        }
      }
      return res.status(400).json(error)
    }
    return res.json({
      exportKey: `skills/${skillId}/versions/v${currentSkill.version}/exports/sop.pdf`,
      skillId,
      title: currentSkill.title,
      version: currentSkill.version,
      pageCount: 7,
      generatedAt: new Date().toISOString()
    })
  })

  app.post('/skills/:skillId/sessions', (req, res) => {
    const { skillId } = req.params
    const sessionId = `sess-${Date.now()}`
    return res.status(201).json({
      sessionId,
      skillId,
      startedAt: new Date().toISOString(),
      activeStepId: currentSkill.steps[0].stepId
    })
  })

  app.post('/sessions/:sessionId/checkpoints', (req, res) => {
    const { sessionId } = req.params
    const body = req.body as Partial<CheckpointRequest>
    const stepId = body.stepId || 'step-003'
    const verdict = req.query.mockVerdict as string || 'pass'

    if (verdict === 'fail') {
      const failResult = loadFixture<CheckpointResult>('checkpointResult.fail.valid.json')
      return res.json({ ...failResult, sessionId, stepId })
    }
    if (verdict === 'uncertain') {
      const uncResult = loadFixture<CheckpointResult>('checkpointResult.uncertain.valid.json')
      return res.json({ ...uncResult, sessionId, stepId })
    }

    const passResult = loadFixture<CheckpointResult>('checkpointResult.pass.valid.json')
    return res.json({ ...passResult, sessionId, stepId })
  })

  app.post('/sessions/:sessionId/complete', (req, res) => {
    const { sessionId } = req.params
    return res.json({
      sessionId,
      status: 'completed',
      completedAt: new Date().toISOString(),
      stepsVerified: 6,
      checkpointsPassed: 2
    })
  })

  app.use((_req, res) => {
    return notImplemented(res)
  })

  return app
}

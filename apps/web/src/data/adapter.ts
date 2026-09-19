import type {
  CheckpointRequest,
  CheckpointResult,
  JobStatus,
  SkillPackage,
  SkillStep
} from '@skilltwin/contracts'
import {
  demoJobStatus,
  failCheckpointResult,
  initialDraftSkill,
  passCheckpointResult,
  uncertainCheckpointResult
} from './fixtureData.js'

export interface SessionCompletionSummary {
  sessionId: string
  status: string
  completedAt: string
  stepsVerified: number
  checkpointsPassed: number
}

class DataAdapter {
  private currentSkill: SkillPackage = { ...initialDraftSkill }
  private currentJob: JobStatus = { ...demoJobStatus }
  private activeSessionId: string = 'sess-worker-001'

  public async getSkills(): Promise<SkillPackage[]> {
    return [this.currentSkill]
  }

  public async getSkill(skillId: string): Promise<SkillPackage | null> {
    if (this.currentSkill.skillId === skillId) {
      return this.currentSkill
    }
    return null
  }

  public async updateStep(
    _skillId: string,
    stepId: string,
    patch: Partial<SkillStep>
  ): Promise<SkillStep> {
    const stepIndex = this.currentSkill.steps.findIndex((s) => s.stepId === stepId)
    if (stepIndex === -1) {
      throw new Error(`Step ${stepId} not found`)
    }
    const updatedStep = {
      ...this.currentSkill.steps[stepIndex],
      ...patch,
      stepId,
      sequence: this.currentSkill.steps[stepIndex].sequence,
      actionCode: this.currentSkill.steps[stepIndex].actionCode
    }
    this.currentSkill.steps[stepIndex] = updatedStep
    return updatedStep
  }

  public async approveSkill(skillId: string, approvedBy: string): Promise<SkillPackage> {
    this.currentSkill = {
      ...this.currentSkill,
      skillId,
      status: 'approved',
      version: this.currentSkill.version === 0 ? 1 : this.currentSkill.version + 1,
      approvedBy,
      approvedAt: new Date().toISOString()
    }
    return this.currentSkill
  }

  public async publishSkill(skillId: string): Promise<SkillPackage> {
    if (this.currentSkill.status !== 'approved') {
      throw new Error('Skill must be approved before publishing')
    }
    this.currentSkill = {
      ...this.currentSkill,
      skillId,
      status: 'published'
    }
    return this.currentSkill
  }

  public async getJobStatus(skillId: string): Promise<JobStatus> {
    return {
      ...this.currentJob,
      skillId
    }
  }

  public async createSession(_skillId: string): Promise<string> {
    this.activeSessionId = `sess-${Date.now()}`
    return this.activeSessionId
  }

  public async submitCheckpoint(
    request: CheckpointRequest,
    verdictChoice: 'pass' | 'fail' | 'uncertain' = 'pass'
  ): Promise<CheckpointResult> {
    if (verdictChoice === 'fail') {
      return {
        ...failCheckpointResult,
        sessionId: request.sessionId,
        stepId: request.stepId
      }
    }
    if (verdictChoice === 'uncertain') {
      return {
        ...uncertainCheckpointResult,
        sessionId: request.sessionId,
        stepId: request.stepId
      }
    }
    return {
      ...passCheckpointResult,
      sessionId: request.sessionId,
      stepId: request.stepId
    }
  }

  public async completeSession(sessionId: string): Promise<SessionCompletionSummary> {
    return {
      sessionId,
      status: 'completed',
      completedAt: new Date().toISOString(),
      stepsVerified: 6,
      checkpointsPassed: 2
    }
  }

  public async getExportPdfInfo(skillId: string): Promise<{ exportKey: string, pageCount: number }> {
    if (this.currentSkill.status === 'reviewRequired' || this.currentSkill.version === 0) {
      throw new Error('Draft skills cannot be exported to PDF SOP')
    }
    return {
      exportKey: `skills/${skillId}/versions/v${this.currentSkill.version}/exports/sop.pdf`,
      pageCount: 7
    }
  }
}

export const defaultDataAdapter = new DataAdapter()

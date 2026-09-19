export type WorkflowType = 'fragilePackingV1'

export type SourceLanguage = 'auto' | 'enIN' | 'hiIN'
export type OutputLanguage = 'enIN' | 'hiIN'

export type ActionCode =
  | 'selectProduct'
  | 'selectBox'
  | 'addProtection'
  | 'placeProduct'
  | 'sealBox'
  | 'attachLabel'

export type PolicyStatus = 'supported' | 'conflict' | 'notFound' | 'needsReview'

export type SkillStatus = 'reviewRequired' | 'approved' | 'published'

export type CheckpointVerdict = 'pass' | 'fail' | 'uncertain'

export type JobState = 'queued' | 'running' | 'reviewRequired' | 'completed' | 'failed'

export type JobStage =
  | 'uploading'
  | 'analyzingMedia'
  | 'extractingDocuments'
  | 'composingSkill'
  | 'checkingPolicy'
  | 'readyForReview'
  | 'publishing'

export interface VideoSource {
  videoId: string
  sourceKey: string
  mimeType: string
}

export interface ImageSource {
  imageId: string
  sourceKey: string
  mimeType: string
}

export interface DocumentSource {
  documentId: string
  sourceKey: string
  mimeType: string
}

export interface AssetManifest {
  schemaVersion: 1
  skillId: string
  workflowType: WorkflowType
  title: string
  videos: VideoSource[]
  referenceImages: ImageSource[]
  documents: DocumentSource[]
  sourceLanguage: SourceLanguage
  outputLanguages: OutputLanguage[]
  expectedObjects: string[]
  supervisorNotes: string | null
}

export interface EvidenceVideo {
  videoId: string
  hasNarration: boolean
  transcriptKey: string | null
}

export interface Observation {
  observationId: string
  videoId: string
  startMs: number
  endMs: number
  beforeState: string
  action: string
  afterState: string
  visibleObjects: string[]
  spokenEvidence: string | null
  candidateAction: ActionCode
  referenceFrameKey: string
  confidence: number
}

export interface EvidenceBundle {
  schemaVersion: 1
  skillId: string
  videos: EvidenceVideo[]
  observations: Observation[]
}

export interface PolicyCitation {
  documentId: string
  page: number
  section: string
  excerpt: string
}

export interface SkillStep {
  stepId: string
  sequence: number
  actionCode: ActionCode
  instruction: string
  instructionHi: string | null
  sourceVideoId: string | null
  startMs: number | null
  endMs: number | null
  referenceFrameKey: string | null
  confidence: number | null
  policyStatus: PolicyStatus
  policyCitation: PolicyCitation | null
  warning: string | null
  checkpointRequired: boolean
  audioKey: string | null
  evidenceObservationIds: string[]
}

export interface SkillPackage {
  schemaVersion: 1
  skillId: string
  title: string
  workflowType: WorkflowType
  status: SkillStatus
  version: number
  materials: string[]
  prerequisites: string[]
  steps: SkillStep[]
  approvedBy: string | null
  approvedAt: string | null
}

export interface CheckpointRequest {
  schemaVersion: 1
  sessionId: string
  stepId: string
  checkpointImageKey: string
}

export interface CheckpointResult {
  schemaVersion: 1
  checkpointId: string
  sessionId: string
  stepId: string
  verdict: CheckpointVerdict
  confidence: number
  observed: string[]
  missing: string[]
  message: string
  correction: string | null
}

export interface JobError {
  code: string
  message: string
}

export interface JobStatus {
  schemaVersion: 1
  jobId: string
  skillId: string
  status: JobState
  stage: JobStage
  progressPercent: number
  message: string
  error: JobError | null
}

export interface ErrorResponse {
  schemaVersion: 1
  requestId: string
  error: {
    code: string
    message: string
  }
}

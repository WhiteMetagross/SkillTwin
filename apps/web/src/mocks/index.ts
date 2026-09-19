import {
  demoJobStatus,
  demoManifest,
  failCheckpointResult,
  initialDraftSkill,
  passCheckpointResult,
  uncertainCheckpointResult
} from '../data/fixtureData.js'

export const mockFixtures = {
  manifest: demoManifest,
  draftSkill: initialDraftSkill,
  jobStatus: demoJobStatus,
  checkpoints: {
    pass: passCheckpointResult,
    fail: failCheckpointResult,
    uncertain: uncertainCheckpointResult
  }
}

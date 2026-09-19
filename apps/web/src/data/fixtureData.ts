import type {
  AssetManifest,
  CheckpointResult,
  JobStatus,
  SkillPackage
} from '@skilltwin/contracts'

export const demoManifest: AssetManifest = {
  schemaVersion: 1,
  skillId: 'skill-fragile-mug-001',
  workflowType: 'fragilePackingV1',
  title: 'Pack fragile ceramic mug',
  videos: [
    {
      videoId: 'video-001',
      sourceKey: 'skills/skill-fragile-mug-001/source/videos/video-001.mp4',
      mimeType: 'video/mp4'
    },
    {
      videoId: 'video-002',
      sourceKey: 'skills/skill-fragile-mug-001/source/videos/video-002.mp4',
      mimeType: 'video/mp4'
    }
  ],
  referenceImages: [
    {
      imageId: 'image-001',
      sourceKey: 'skills/skill-fragile-mug-001/source/images/image-001.jpg',
      mimeType: 'image/jpeg'
    }
  ],
  documents: [
    {
      documentId: 'doc-packing-policy-001',
      sourceKey: 'skills/skill-fragile-mug-001/source/documents/doc-packing-policy-001.pdf',
      mimeType: 'application/pdf'
    }
  ],
  sourceLanguage: 'enIN',
  outputLanguages: ['enIN', 'hiIN'],
  expectedObjects: ['ceramic mug', 'bubble wrap', 'cardboard box', 'tape', 'fragile label'],
  supervisorNotes: 'Ensure double layer bubble wrap before boxing'
}

export const initialDraftSkill: SkillPackage = {
  schemaVersion: 1,
  skillId: 'skill-fragile-mug-001',
  title: 'Pack fragile ceramic mug',
  workflowType: 'fragilePackingV1',
  status: 'reviewRequired',
  version: 0,
  materials: [
    'ceramic mug',
    'bubble wrap sheet',
    'corrugated box',
    'packing tape',
    'fragile label'
  ],
  prerequisites: ['clean packing bench', 'protective gloves'],
  steps: [
    {
      stepId: 'step-001',
      sequence: 1,
      actionCode: 'selectProduct',
      instruction: 'Inspect the ceramic mug for surface cracks and defects.',
      instructionHi: 'सिरेमिक मग की सतह पर दरारें और खामियां जांचें।',
      sourceVideoId: 'video-001',
      startMs: 1000,
      endMs: 4500,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/2000.jpg',
      confidence: 0.95,
      policyStatus: 'supported',
      policyCitation: {
        documentId: 'doc-packing-policy-001',
        page: 2,
        section: 'Item inspection',
        excerpt: 'Inspect fragile items for surface flaws before handling.'
      },
      warning: null,
      checkpointRequired: false,
      audioKey: null,
      evidenceObservationIds: ['obs-001']
    },
    {
      stepId: 'step-002',
      sequence: 2,
      actionCode: 'selectBox',
      instruction: 'Assemble the small standard corrugated carton.',
      instructionHi: 'छोटे मानक नालीदार कार्टन को इकट्ठा करें।',
      sourceVideoId: 'video-001',
      startMs: 5000,
      endMs: 8200,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/6000.jpg',
      confidence: 0.92,
      policyStatus: 'supported',
      policyCitation: {
        documentId: 'doc-packing-policy-001',
        page: 3,
        section: 'Box sizing',
        excerpt: 'Select a box that provides at least two inches of clearance on all sides.'
      },
      warning: null,
      checkpointRequired: false,
      audioKey: null,
      evidenceObservationIds: ['obs-002']
    },
    {
      stepId: 'step-003',
      sequence: 3,
      actionCode: 'addProtection',
      instruction: 'Wrap the ceramic mug completely with bubble wrap cushioning.',
      instructionHi: 'सिरेमिक मग को पूरी तरह से बबल रैप से लपेटें।',
      sourceVideoId: 'video-001',
      startMs: 9000,
      endMs: 15500,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/12000.jpg',
      confidence: 0.88,
      policyStatus: 'conflict',
      policyCitation: {
        documentId: 'doc-packing-policy-001',
        page: 4,
        section: 'Cushioning',
        excerpt: 'Fragile ceramics require two complete layers of bubble wrap.'
      },
      warning: 'Demonstration shows single wrap but policy requires two layers',
      checkpointRequired: true,
      audioKey: null,
      evidenceObservationIds: ['obs-003']
    },
    {
      stepId: 'step-004',
      sequence: 4,
      actionCode: 'placeProduct',
      instruction: 'Place the wrapped ceramic mug upright in the center of the box.',
      instructionHi: 'लपेटे गए मग को बॉक्स के केंद्र में सीधा रखें।',
      sourceVideoId: 'video-001',
      startMs: 16000,
      endMs: 20000,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/18000.jpg',
      confidence: 0.94,
      policyStatus: 'supported',
      policyCitation: null,
      warning: null,
      checkpointRequired: false,
      audioKey: null,
      evidenceObservationIds: ['obs-004']
    },
    {
      stepId: 'step-005',
      sequence: 5,
      actionCode: 'sealBox',
      instruction: 'Close box flaps and seal center seam and edges using H tape method.',
      instructionHi: 'बॉक्स के फ्लैप बंद करें और एच टेप विधि से सील करें।',
      sourceVideoId: 'video-001',
      startMs: 21000,
      endMs: 26000,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/23000.jpg',
      confidence: 0.96,
      policyStatus: 'supported',
      policyCitation: {
        documentId: 'doc-packing-policy-001',
        page: 5,
        section: 'Sealing',
        excerpt: 'Seal center flap and edges using H tape method.'
      },
      warning: null,
      checkpointRequired: false,
      audioKey: null,
      evidenceObservationIds: ['obs-005']
    },
    {
      stepId: 'step-006',
      sequence: 6,
      actionCode: 'attachLabel',
      instruction: 'Affix fragile shipping label visibly on the top face of the sealed box.',
      instructionHi: 'सील किए गए बॉक्स के शीर्ष पर नाजुक शिपिंग लेबल चिपकाएं।',
      sourceVideoId: 'video-001',
      startMs: 27000,
      endMs: 31000,
      referenceFrameKey: 'skills/skill-fragile-mug-001/derived/frames/video-001/29000.jpg',
      confidence: 0.98,
      policyStatus: 'supported',
      policyCitation: {
        documentId: 'doc-packing-policy-001',
        page: 6,
        section: 'Labeling',
        excerpt: 'Affix fragile shipping label visibly on top flap.'
      },
      warning: null,
      checkpointRequired: true,
      audioKey: null,
      evidenceObservationIds: ['obs-006']
    }
  ],
  approvedBy: null,
  approvedAt: null
}

export const demoJobStatus: JobStatus = {
  schemaVersion: 1,
  jobId: 'job-pack-991',
  skillId: 'skill-fragile-mug-001',
  status: 'reviewRequired',
  stage: 'readyForReview',
  progressPercent: 100,
  message: 'Skill draft composed and ready for supervisor review',
  error: null
}

export const passCheckpointResult: CheckpointResult = {
  schemaVersion: 1,
  checkpointId: 'chk-pass-001',
  sessionId: 'sess-worker-001',
  stepId: 'step-003',
  verdict: 'pass',
  confidence: 0.94,
  observed: ['ceramic mug', 'double bubble wrap'],
  missing: [],
  message: 'Protection verified with double layer cushioning',
  correction: null
}

export const failCheckpointResult: CheckpointResult = {
  schemaVersion: 1,
  checkpointId: 'chk-fail-002',
  sessionId: 'sess-worker-001',
  stepId: 'step-003',
  verdict: 'fail',
  confidence: 0.91,
  observed: ['ceramic mug', 'single bubble wrap'],
  missing: ['second bubble wrap layer'],
  message: 'Only single layer bubble wrap detected',
  correction: 'Add a second complete layer of bubble wrap before boxing'
}

export const uncertainCheckpointResult: CheckpointResult = {
  schemaVersion: 1,
  checkpointId: 'chk-unc-003',
  sessionId: 'sess-worker-001',
  stepId: 'step-003',
  verdict: 'uncertain',
  confidence: 0.42,
  observed: ['ceramic mug'],
  missing: [],
  message: 'Image is blurry or obstructed, please capture another photo',
  correction: 'Hold camera steady with proper lighting and retake'
}

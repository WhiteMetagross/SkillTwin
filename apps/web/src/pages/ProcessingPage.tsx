import React from 'react'
import type { JobStatus } from '@skilltwin/contracts'

interface ProcessingPageProps {
  job: JobStatus
  onNavigateToReview: () => void
}

export const ProcessingPage: React.FC<ProcessingPageProps> = ({ job, onNavigateToReview }) => {
  const stages = [
    { key: 'uploading', label: 'Uploading media and policy assets' },
    { key: 'analyzingMedia', label: 'Media intelligence observation extraction' },
    { key: 'extractingDocuments', label: 'Document policy citation parsing' },
    { key: 'composingSkill', label: 'Composing six step draft package' },
    { key: 'checkingPolicy', label: 'Policy conflict and rule verification' },
    { key: 'readyForReview', label: 'Skill draft ready for supervisor review' }
  ]

  const currentStageIndex = stages.findIndex((s) => s.key === job.stage)
  const isFinished = job.status === 'reviewRequired' || job.status === 'completed'

  return (
    <div>
      <div className="pageHeader">
        <h1 className="pageTitle">Analysis Job Status</h1>
        <p className="pageDescription">
          Pipeline execution progress for job {job.jobId}
        </p>
      </div>

      <div className="card" style={{ maxWidth: '760px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Status</div>
            <div style={{ fontSize: '18px', fontWeight: 600 }}>{job.status}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Progress</div>
            <div style={{ fontSize: '18px', fontWeight: 600, color: 'var(--accent-secondary)' }}>
              {job.progressPercent}%
            </div>
          </div>
        </div>

        <div
          style={{
            height: '8px',
            background: 'rgba(255, 255, 255, 0.08)',
            borderRadius: '999px',
            overflow: 'hidden',
            marginBottom: '24px'
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${job.progressPercent}%`,
              background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))',
              transition: 'width 0.4s ease'
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {stages.map((st, idx) => {
            const isCompleted = idx <= (currentStageIndex === -1 ? stages.length - 1 : currentStageIndex)
            return (
              <div
                key={st.key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-sm)',
                  background: isCompleted ? 'rgba(99, 102, 241, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  border: `1px solid ${isCompleted ? 'rgba(99, 102, 241, 0.2)' : 'var(--border-subtle)'}`
                }}
              >
                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '11px',
                    fontWeight: 700,
                    background: isCompleted ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.1)',
                    color: '#ffffff'
                  }}
                >
                  {idx + 1}
                </div>
                <div style={{ flex: 1, fontSize: '14px', fontWeight: isCompleted ? 600 : 400 }}>
                  {st.label}
                </div>
                {isCompleted && <span className="badge badgeSuccess">Done</span>}
              </div>
            )
          })}
        </div>

        {isFinished && (
          <div style={{ marginTop: '24px', textAlign: 'right' }}>
            <button
              id="btn-proceed-review"
              className="btn"
              onClick={onNavigateToReview}
            >
              Open Supervisor Review
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

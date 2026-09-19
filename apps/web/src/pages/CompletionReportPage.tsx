import React from 'react'
import type { SessionCompletionSummary } from '../data/adapter.js'

interface CompletionReportPageProps {
  summary: SessionCompletionSummary
  onReturnToDashboard: () => void
}

export const CompletionReportPage: React.FC<CompletionReportPageProps> = ({
  summary,
  onReturnToDashboard
}) => {
  return (
    <div>
      <div className="pageHeader">
        <h1 className="pageTitle">Worker Session Completion Report</h1>
        <p className="pageDescription">
          Summary of execution results and quality verification for packing session
        </p>
      </div>

      <div className="card" style={{ maxWidth: '640px' }}>
        <div style={{ textAlign: 'center', padding: '24px 0 16px' }}>
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'rgba(16, 185, 129, 0.15)',
              border: '2px solid var(--status-success)',
              color: 'var(--status-success)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              fontWeight: 700,
              margin: '0 auto 16px'
            }}
          >
            OK
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '6px' }}>
            Work Instructions Completed Successfully
          </h2>
          <span className="badge badgeSuccess">Quality Standard Compliant</span>
        </div>

        <div
          style={{
            background: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '20px',
            margin: '20px 0',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            fontSize: '14px'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Session ID</span>
            <span style={{ fontWeight: 600 }}>{summary.sessionId}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Status</span>
            <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{summary.status}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Steps Completed</span>
            <span style={{ fontWeight: 600 }}>{summary.stepsVerified} of 6 steps</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Checkpoints Verified</span>
            <span style={{ fontWeight: 600 }}>{summary.checkpointsPassed} checkpoints passed</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Timestamp</span>
            <span style={{ fontWeight: 600 }}>{new Date(summary.completedAt).toLocaleString()}</span>
          </div>
        </div>

        <button
          id="btn-return-dashboard"
          className="btn"
          style={{ width: '100%' }}
          onClick={onReturnToDashboard}
        >
          Return to Dashboard
        </button>
      </div>
    </div>
  )
}

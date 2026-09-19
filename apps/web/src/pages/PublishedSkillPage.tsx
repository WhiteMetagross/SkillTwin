import React, { useState } from 'react'
import type { SkillPackage } from '@skilltwin/contracts'

interface PublishedSkillPageProps {
  skill: SkillPackage
  onPublish: () => Promise<void>
  onNavigateToGuided: () => void
}

export const PublishedSkillPage: React.FC<PublishedSkillPageProps> = ({
  skill,
  onPublish,
  onNavigateToGuided
}) => {
  const [selectedLanguage, setSelectedLanguage] = useState<'en' | 'hi'>('en')
  const [pdfDownloaded, setPdfDownloaded] = useState<boolean>(false)

  const isApproved = skill.status === 'approved' || skill.status === 'published'

  const handleDownloadPdf = () => {
    setPdfDownloaded(true)
    setTimeout(() => setPdfDownloaded(false), 3000)
  }

  return (
    <div>
      <div className="pageHeader">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span className="badge badgeSuccess">{skill.status}</span>
              <span className="badge badgeInfo">v{skill.version}</span>
            </div>
            <h1 className="pageTitle">{skill.title}</h1>
            <p className="pageDescription">
              Published standard operating procedure ready for floor execution
            </p>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            {skill.status === 'approved' && (
              <button id="btn-publish-skill" className="btn" onClick={onPublish}>
                Publish to Floor
              </button>
            )}
            <button
              id="btn-export-pdf"
              className="btn btnSecondary"
              onClick={handleDownloadPdf}
              disabled={!isApproved}
            >
              {pdfDownloaded ? 'PDF SOP Exported' : 'Export PDF SOP'}
            </button>
            <button id="btn-start-worker-session" className="btn" onClick={onNavigateToGuided}>
              Start Worker Session
            </button>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Standard Operating Procedure Steps</h2>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Language:</span>
            <button
              id="btn-lang-en"
              className={`btn btnSecondary ${selectedLanguage === 'en' ? 'navLinkActive' : ''}`}
              style={{ padding: '4px 12px', fontSize: '12px' }}
              onClick={() => setSelectedLanguage('en')}
            >
              English
            </button>
            <button
              id="btn-lang-hi"
              className={`btn btnSecondary ${selectedLanguage === 'hi' ? 'navLinkActive' : ''}`}
              style={{ padding: '4px 12px', fontSize: '12px' }}
              onClick={() => setSelectedLanguage('hi')}
            >
              Hindi (हिन्दी)
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {skill.steps.map((step) => (
            <div
              key={step.stepId}
              style={{
                padding: '16px',
                borderRadius: 'var(--radius-sm)',
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                gap: '16px',
                alignItems: 'flex-start'
              }}
            >
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: 'var(--accent-primary)',
                  color: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '14px',
                  flexShrink: 0
                }}
              >
                {step.sequence}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                  <div style={{ fontWeight: 600, fontSize: '16px' }}>{step.actionCode}</div>
                  {step.checkpointRequired && (
                    <span className="badge badgeInfo">Verification Checkpoint</span>
                  )}
                </div>
                <div style={{ color: 'var(--text-primary)', fontSize: '15px' }}>
                  {selectedLanguage === 'hi' && step.instructionHi
                    ? step.instructionHi
                    : step.instruction}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px' }}>Required Materials</h3>
        <ul style={{ listStyleType: 'disc', paddingLeft: '20px', color: 'var(--text-secondary)' }}>
          {skill.materials.map((m, idx) => (
            <li key={idx}>{m}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

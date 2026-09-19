import React, { useState } from 'react'

interface UploadPageProps {
  onStartProcessing: () => void
}

export const UploadPage: React.FC<UploadPageProps> = ({ onStartProcessing }) => {
  const [title, setTitle] = useState('Pack fragile ceramic mug')
  const [notes, setNotes] = useState('Ensure double layer bubble wrap before boxing')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onStartProcessing()
  }

  return (
    <div>
      <div className="pageHeader">
        <h1 className="pageTitle">Upload Demonstration Media and Policy</h1>
        <p className="pageDescription">
          Provide worker demonstration videos, reference images, and packaging policy documents
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card" style={{ maxWidth: '720px' }}>
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600, fontSize: '14px' }}>
            Skill Title
          </label>
          <input
            id="input-skill-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{ width: '100%' }}
            required
          />
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600, fontSize: '14px' }}>
            Workflow Template
          </label>
          <input
            type="text"
            value="fragilePackingV1 (Fixed 6 step template)"
            disabled
            style={{ width: '100%', opacity: 0.7 }}
          />
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600, fontSize: '14px' }}>
            Demonstration Videos (1 to 3 videos)
          </label>
          <div
            style={{
              border: '2px dashed var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '24px',
              textAlign: 'center',
              background: 'rgba(255, 255, 255, 0.02)'
            }}
          >
            <div style={{ color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '14px' }}>
              Attached fixture videos: video-001.mp4 (narrated), video-002.mp4
            </div>
            <span className="badge badgeInfo">Mock Files Attached</span>
          </div>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600, fontSize: '14px' }}>
            Policy PDF Documents
          </label>
          <div
            style={{
              border: '2px dashed var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '24px',
              textAlign: 'center',
              background: 'rgba(255, 255, 255, 0.02)'
            }}
          >
            <div style={{ color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '14px' }}>
              Attached policy document: doc-packing-policy-001.pdf
            </div>
            <span className="badge badgeInfo">Mock Policy Attached</span>
          </div>
        </div>

        <div style={{ marginBottom: '24px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontWeight: 600, fontSize: '14px' }}>
            Supervisor Guidance Notes
          </label>
          <textarea
            id="input-supervisor-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            style={{ width: '100%', resize: 'vertical' }}
          />
        </div>

        <button id="btn-start-analysis" type="submit" className="btn" style={{ width: '100%' }}>
          Start Analysis and Skill Composition
        </button>
      </form>
    </div>
  )
}

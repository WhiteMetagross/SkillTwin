import React from 'react'
import type { SkillPackage } from '@skilltwin/contracts'

interface DashboardPageProps {
  skills: SkillPackage[]
  onNavigate: (tab: string) => void
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ skills, onNavigate }) => {
  return (
    <div>
      <div className="pageHeader">
        <h1 className="pageTitle">Standard Operating Procedure Skills</h1>
        <p className="pageDescription">
          Review generated packing skills and monitor worker adherence across packing stations
        </p>
      </div>

      <div className="grid grid2" style={{ marginBottom: '32px' }}>
        {skills.map((skill) => (
          <div key={skill.skillId} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
              <div>
                <span className="badge badgeInfo" style={{ marginBottom: '8px' }}>
                  {skill.workflowType}
                </span>
                <h2 style={{ fontSize: '20px', fontWeight: 600, marginTop: '4px' }}>
                  {skill.title}
                </h2>
              </div>
              <span
                className={`badge ${
                  skill.status === 'approved' || skill.status === 'published'
                    ? 'badgeSuccess'
                    : 'badgeWarning'
                }`}
              >
                {skill.status}
              </span>
            </div>

            <div style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
              <div>Version: v{skill.version}</div>
              <div>Steps: {skill.steps.length} sequential actions</div>
              <div>Skill ID: {skill.skillId}</div>
            </div>

            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                id="btn-goto-review"
                className="btn"
                onClick={() => onNavigate('review')}
              >
                Review Draft
              </button>
              <button
                id="btn-goto-guided"
                className="btn btnSecondary"
                onClick={() => onNavigate('guided')}
              >
                Launch Guided Coach
              </button>
              <button
                id="btn-goto-published"
                className="btn btnSecondary"
                onClick={() => onNavigate('published')}
              >
                View SOP
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '12px' }}>
          Workflow Pipeline Overview
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
          SkillTwin enforces the six action template for fragile packing operations:
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
          {[
            { num: 1, name: 'selectProduct', desc: 'Inspect product' },
            { num: 2, name: 'selectBox', desc: 'Assemble box' },
            { num: 3, name: 'addProtection', desc: 'Wrap bubble sheet' },
            { num: 4, name: 'placeProduct', desc: 'Center product' },
            { num: 5, name: 'sealBox', desc: 'Tape seams' },
            { num: 6, name: 'attachLabel', desc: 'Apply fragile label' }
          ].map((item) => (
            <div
              key={item.num}
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '12px',
                textAlign: 'center'
              }}
            >
              <div style={{ color: 'var(--accent-secondary)', fontSize: '12px', fontWeight: 700 }}>
                STEP {item.num}
              </div>
              <div style={{ fontWeight: 600, fontSize: '14px', margin: '4px 0' }}>{item.name}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{item.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

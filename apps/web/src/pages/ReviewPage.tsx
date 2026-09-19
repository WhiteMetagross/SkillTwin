import React, { useState } from 'react'
import type { SkillPackage, SkillStep } from '@skilltwin/contracts'

interface ReviewPageProps {
  skill: SkillPackage
  onUpdateStep: (stepId: string, patch: Partial<SkillStep>) => Promise<void>
  onApproveSkill: () => Promise<void>
  onNavigateToPublished: () => void
}

export const ReviewPage: React.FC<ReviewPageProps> = ({
  skill,
  onUpdateStep,
  onApproveSkill,
  onNavigateToPublished
}) => {
  const [editingStepId, setEditingStepId] = useState<string | null>(null)
  const [editedInstruction, setEditedInstruction] = useState<string>('')
  const [isApproving, setIsApproving] = useState<boolean>(false)

  const handleStartEdit = (step: SkillStep) => {
    setEditingStepId(step.stepId)
    setEditedInstruction(step.instruction)
  }

  const handleSaveEdit = async (stepId: string) => {
    await onUpdateStep(stepId, { instruction: editedInstruction })
    setEditingStepId(null)
  }

  const handleApprove = async () => {
    setIsApproving(true)
    try {
      await onApproveSkill()
      onNavigateToPublished()
    } finally {
      setIsApproving(false)
    }
  }

  const conflictStep = skill.steps.find((s) => s.policyStatus === 'conflict')

  return (
    <div>
      <div className="pageHeader">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 className="pageTitle">Supervisor Review: {skill.title}</h1>
            <p className="pageDescription">
              Review model composed actions against video evidence and policy documentation
            </p>
          </div>
          <button
            id="btn-approve-skill"
            className="btn"
            onClick={handleApprove}
            disabled={isApproving}
          >
            {isApproving ? 'Approving...' : 'Approve Draft SOP'}
          </button>
        </div>
      </div>

      {conflictStep && (
        <div id="alert-policy-conflict" className="alertBox alertWarning">
          <div style={{ fontWeight: 700, fontSize: '15px', marginBottom: '4px' }}>
            Policy Conflict Flagged on Step {conflictStep.sequence} ({conflictStep.actionCode})
          </div>
          <div>{conflictStep.warning}</div>
          {conflictStep.policyCitation && (
            <div
              style={{
                marginTop: '10px',
                padding: '10px',
                background: 'rgba(0, 0, 0, 0.2)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '13px'
              }}
            >
              <div>
                <strong>Policy Document:</strong> {conflictStep.policyCitation.documentId} (Page{' '}
                {conflictStep.policyCitation.page}, Section {conflictStep.policyCitation.section})
              </div>
              <div style={{ fontStyle: 'italic', marginTop: '4px' }}>
                "{conflictStep.policyCitation.excerpt}"
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {skill.steps.map((step) => {
          const isConflict = step.policyStatus === 'conflict'
          return (
            <div
              key={step.stepId}
              id={`review-step-${step.stepId}`}
              className="card"
              style={{
                borderColor: isConflict ? 'rgba(245, 158, 11, 0.5)' : undefined,
                background: isConflict ? 'rgba(245, 158, 11, 0.03)' : undefined
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '12px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      background: 'var(--accent-primary)',
                      color: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 700,
                      fontSize: '13px'
                    }}
                  >
                    {step.sequence}
                  </div>
                  <h3 style={{ fontSize: '17px', fontWeight: 600 }}>{step.actionCode}</h3>
                  {step.checkpointRequired && (
                    <span className="badge badgeInfo">Checkpoint Required</span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <span
                    className={`badge ${
                      step.policyStatus === 'conflict'
                        ? 'badgeWarning'
                        : step.policyStatus === 'supported'
                          ? 'badgeSuccess'
                          : 'badgeInfo'
                    }`}
                  >
                    Policy: {step.policyStatus}
                  </span>
                  {step.confidence !== null && (
                    <span className="badge badgeInfo">
                      Confidence: {Math.round(step.confidence * 100)}%
                    </span>
                  )}
                </div>
              </div>

              {editingStepId === step.stepId ? (
                <div style={{ marginTop: '10px', marginBottom: '14px' }}>
                  <textarea
                    value={editedInstruction}
                    onChange={(e) => setEditedInstruction(e.target.value)}
                    rows={2}
                    style={{ width: '100%', marginBottom: '8px' }}
                  />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="btn"
                      style={{ padding: '6px 14px', fontSize: '12px' }}
                      onClick={() => handleSaveEdit(step.stepId)}
                    >
                      Save
                    </button>
                    <button
                      className="btn btnSecondary"
                      style={{ padding: '6px 14px', fontSize: '12px' }}
                      onClick={() => setEditingStepId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', margin: '8px 0 16px' }}>
                  <div style={{ fontSize: '15px', color: 'var(--text-primary)' }}>
                    {step.instruction}
                  </div>
                  <button
                    className="btn btnSecondary"
                    style={{ padding: '4px 10px', fontSize: '12px', marginLeft: '12px' }}
                    onClick={() => handleStartEdit(step)}
                  >
                    Edit
                  </button>
                </div>
              )}

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                  gap: '12px',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                  borderTop: '1px solid var(--border-subtle)',
                  paddingTop: '12px'
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Evidence Frame: </span>
                  {step.referenceFrameKey ? step.referenceFrameKey.split('/').pop() : 'None'}
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Timing: </span>
                  {step.startMs !== null && step.endMs !== null
                    ? `${step.startMs}ms to ${step.endMs}ms`
                    : 'Unassigned'}
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Observation: </span>
                  {step.evidenceObservationIds.join(', ') || 'No linked observation'}
                </div>
              </div>

              {step.policyCitation && (
                <div
                  style={{
                    marginTop: '12px',
                    padding: '8px 12px',
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '12px',
                    color: 'var(--text-secondary)'
                  }}
                >
                  <strong style={{ color: 'var(--text-primary)' }}>Citation: </strong>
                  Doc {step.policyCitation.documentId}, Page {step.policyCitation.page}, {step.policyCitation.section}: "{step.policyCitation.excerpt}"
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

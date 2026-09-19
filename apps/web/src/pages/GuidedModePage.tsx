import React, { useState } from 'react'
import type { CheckpointResult, SkillPackage } from '@skilltwin/contracts'

interface GuidedModePageProps {
  skill: SkillPackage
  onSubmitCheckpoint: (
    stepId: string,
    verdictChoice: 'pass' | 'fail' | 'uncertain'
  ) => Promise<CheckpointResult>
  onFinishSession: () => void
}

export const GuidedModePage: React.FC<GuidedModePageProps> = ({
  skill,
  onSubmitCheckpoint,
  onFinishSession
}) => {
  const [activeStepIndex, setActiveStepIndex] = useState<number>(0)
  const [mockVerdictChoice, setMockVerdictChoice] = useState<'pass' | 'fail' | 'uncertain'>('pass')
  const [lastResult, setLastResult] = useState<CheckpointResult | null>(null)
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false)

  const activeStep = skill.steps[activeStepIndex]
  const isLastStep = activeStepIndex === skill.steps.length - 1

  const handleEvaluateCheckpoint = async () => {
    setIsEvaluating(true)
    try {
      const result = await onSubmitCheckpoint(activeStep.stepId, mockVerdictChoice)
      setLastResult(result)
    } finally {
      setIsEvaluating(false)
    }
  }

  const handleNextStep = () => {
    setLastResult(null)
    if (isLastStep) {
      onFinishSession()
    } else {
      setActiveStepIndex((prev) => prev + 1)
    }
  }

  return (
    <div>
      <div className="pageHeader">
        <h1 className="pageTitle">Worker Coach: Interactive Execution</h1>
        <p className="pageDescription">
          Follow digital work instructions and complete required visual quality verification checkpoints
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <span className="badge badgeInfo">
              Step {activeStep.sequence} of {skill.steps.length}
            </span>
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
              Action: {activeStep.actionCode}
            </div>
          </div>

          <div style={{ fontSize: '20px', fontWeight: 600, marginBottom: '16px', color: 'var(--text-primary)' }}>
            {activeStep.instruction}
          </div>

          {activeStep.instructionHi && (
            <div style={{ fontSize: '16px', color: 'var(--text-secondary)', marginBottom: '24px', fontStyle: 'italic' }}>
              {activeStep.instructionHi}
            </div>
          )}

          {activeStep.checkpointRequired ? (
            <div
              style={{
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
                background: 'rgba(255, 255, 255, 0.02)',
                marginBottom: '24px'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Visual Quality Checkpoint</h3>
                <span className="badge badgeWarning">Photo Verification Required</span>
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginBottom: '16px' }}>
                Capture a clear photo of the packed item on the bench to verify adherence with quality standards.
              </p>

              <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '16px' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Simulate Verdict:</span>
                <select
                  id="select-mock-verdict"
                  value={mockVerdictChoice}
                  onChange={(e) => setMockVerdictChoice(e.target.value as 'pass' | 'fail' | 'uncertain')}
                  style={{ fontSize: '13px', padding: '6px 10px' }}
                >
                  <option value="pass">Pass (Double layer detected)</option>
                  <option value="fail">Fail (Single layer detected)</option>
                  <option value="uncertain">Uncertain (Blurry photo)</option>
                </select>
              </div>

              <button
                id="btn-evaluate-checkpoint"
                className="btn"
                onClick={handleEvaluateCheckpoint}
                disabled={isEvaluating}
              >
                {isEvaluating ? 'Evaluating Image...' : 'Capture and Verify Checkpoint Photo'}
              </button>

              {lastResult && (
                <div
                  id="checkpoint-result-box"
                  style={{
                    marginTop: '16px',
                    padding: '14px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid',
                    background:
                      lastResult.verdict === 'pass'
                        ? 'rgba(16, 185, 129, 0.1)'
                        : lastResult.verdict === 'fail'
                          ? 'rgba(244, 63, 94, 0.1)'
                          : 'rgba(245, 158, 11, 0.1)',
                    borderColor:
                      lastResult.verdict === 'pass'
                        ? 'rgba(16, 185, 129, 0.4)'
                        : lastResult.verdict === 'fail'
                          ? 'rgba(244, 63, 94, 0.4)'
                          : 'rgba(245, 158, 11, 0.4)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span
                      className={`badge ${
                        lastResult.verdict === 'pass'
                          ? 'badgeSuccess'
                          : lastResult.verdict === 'fail'
                            ? 'badgeDanger'
                            : 'badgeWarning'
                      }`}
                    >
                      Verdict: {lastResult.verdict.toUpperCase()}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      Confidence: {Math.round(lastResult.confidence * 100)}%
                    </span>
                  </div>
                  <div style={{ fontSize: '14px', fontWeight: 500 }}>{lastResult.message}</div>
                  {lastResult.correction && (
                    <div style={{ fontSize: '13px', marginTop: '6px', color: '#fde68a' }}>
                      Correction: {lastResult.correction}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <button
              className="btn btnSecondary"
              disabled={activeStepIndex === 0}
              onClick={() => setActiveStepIndex((prev) => prev - 1)}
            >
              Previous Step
            </button>
            <button
              id="btn-next-step"
              className="btn"
              disabled={activeStep.checkpointRequired && (!lastResult || lastResult.verdict === 'fail')}
              onClick={handleNextStep}
            >
              {isLastStep ? 'Finish Session' : 'Next Step'}
            </button>
          </div>
        </div>

        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '16px' }}>Step Progress</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {skill.steps.map((step, idx) => (
              <div
                key={step.stepId}
                onClick={() => {
                  setActiveStepIndex(idx)
                  setLastResult(null)
                }}
                style={{
                  padding: '10px 12px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  background:
                    idx === activeStepIndex
                      ? 'rgba(99, 102, 241, 0.15)'
                      : 'rgba(255, 255, 255, 0.02)',
                  border:
                    idx === activeStepIndex
                      ? '1px solid rgba(99, 102, 241, 0.4)'
                      : '1px solid transparent',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: '13px'
                }}
              >
                <div
                  style={{
                    width: '20px',
                    height: '20px',
                    borderRadius: '50%',
                    background: idx === activeStepIndex ? 'var(--accent-primary)' : 'rgba(255, 255, 255, 0.1)',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '11px',
                    fontWeight: 700
                  }}
                >
                  {step.sequence}
                </div>
                <div style={{ flex: 1, fontWeight: idx === activeStepIndex ? 600 : 400 }}>
                  {step.actionCode}
                </div>
                {step.checkpointRequired && (
                  <span style={{ fontSize: '10px', color: 'var(--status-warning)' }}>CHECK</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

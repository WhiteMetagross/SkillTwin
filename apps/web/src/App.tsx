import React, { useEffect, useState } from 'react'
import type { JobStatus, SkillPackage, SkillStep } from '@skilltwin/contracts'
import { defaultDataAdapter, type SessionCompletionSummary } from './data/adapter.js'
import { Header } from './components/Header.js'
import { DashboardPage } from './pages/DashboardPage.js'
import { UploadPage } from './pages/UploadPage.js'
import { ProcessingPage } from './pages/ProcessingPage.js'
import { ReviewPage } from './pages/ReviewPage.js'
import { PublishedSkillPage } from './pages/PublishedSkillPage.js'
import { GuidedModePage } from './pages/GuidedModePage.js'
import { CompletionReportPage } from './pages/CompletionReportPage.js'

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('dashboard')
  const [skills, setSkills] = useState<SkillPackage[]>([])
  const [currentSkill, setCurrentSkill] = useState<SkillPackage | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [completionSummary, setCompletionSummary] = useState<SessionCompletionSummary | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    const initData = async () => {
      const loadedSkills = await defaultDataAdapter.getSkills()
      setSkills(loadedSkills)
      if (loadedSkills.length > 0) {
        setCurrentSkill(loadedSkills[0])
        const job = await defaultDataAdapter.getJobStatus(loadedSkills[0].skillId)
        setJobStatus(job)
      }
      setLoading(false)
    }
    initData()
  }, [])

  const handleUpdateStep = async (stepId: string, patch: Partial<SkillStep>) => {
    if (!currentSkill) return
    await defaultDataAdapter.updateStep(currentSkill.skillId, stepId, patch)
    const updated = await defaultDataAdapter.getSkill(currentSkill.skillId)
    if (updated) {
      setCurrentSkill({ ...updated })
      setSkills([{ ...updated }])
    }
  }

  const handleApproveSkill = async () => {
    if (!currentSkill) return
    const approved = await defaultDataAdapter.approveSkill(currentSkill.skillId, 'supervisor-default')
    setCurrentSkill({ ...approved })
    setSkills([{ ...approved }])
  }

  const handlePublishSkill = async () => {
    if (!currentSkill) return
    const published = await defaultDataAdapter.publishSkill(currentSkill.skillId)
    setCurrentSkill({ ...published })
    setSkills([{ ...published }])
  }

  const handleSubmitCheckpoint = async (
    stepId: string,
    verdictChoice: 'pass' | 'fail' | 'uncertain'
  ) => {
    return defaultDataAdapter.submitCheckpoint(
      {
        schemaVersion: 1,
        sessionId: 'sess-worker-001',
        stepId,
        checkpointImageKey: `sessions/sess-worker-001/checkpoints/${stepId}.jpg`
      },
      verdictChoice
    )
  }

  const handleFinishSession = async () => {
    const summary = await defaultDataAdapter.completeSession('sess-worker-001')
    setCompletionSummary(summary)
    setCurrentTab('completion')
  }

  if (loading || !currentSkill || !jobStatus) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading SkillTwin platform...
      </div>
    )
  }

  return (
    <div className="appContainer">
      <Header currentTab={currentTab} onTabChange={setCurrentTab} />

      <main className="mainContent">
        {currentTab === 'dashboard' && (
          <DashboardPage skills={skills} onNavigate={setCurrentTab} />
        )}

        {currentTab === 'upload' && (
          <UploadPage onStartProcessing={() => setCurrentTab('processing')} />
        )}

        {currentTab === 'processing' && (
          <ProcessingPage job={jobStatus} onNavigateToReview={() => setCurrentTab('review')} />
        )}

        {currentTab === 'review' && (
          <ReviewPage
            skill={currentSkill}
            onUpdateStep={handleUpdateStep}
            onApproveSkill={handleApproveSkill}
            onNavigateToPublished={() => setCurrentTab('published')}
          />
        )}

        {currentTab === 'published' && (
          <PublishedSkillPage
            skill={currentSkill}
            onPublish={handlePublishSkill}
            onNavigateToGuided={() => setCurrentTab('guided')}
          />
        )}

        {currentTab === 'guided' && (
          <GuidedModePage
            skill={currentSkill}
            onSubmitCheckpoint={handleSubmitCheckpoint}
            onFinishSession={handleFinishSession}
          />
        )}

        {currentTab === 'completion' && completionSummary && (
          <CompletionReportPage
            summary={completionSummary}
            onReturnToDashboard={() => setCurrentTab('dashboard')}
          />
        )}
      </main>
    </div>
  )
}

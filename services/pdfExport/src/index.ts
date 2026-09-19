import type { SkillPackage } from '@skilltwin/contracts'

export interface PdfExportResult {
  exportKey: string
  skillId: string
  title: string
  version: number
  pageCount: number
  generatedAt: string
}

export class PdfExportService {
  public exportSop(skill: SkillPackage): PdfExportResult {
    if (skill.status === 'reviewRequired' || skill.version === 0 || !skill.approvedBy) {
      throw new Error('Draft skills cannot be exported to PDF SOP')
    }

    const exportKey = `skills/${skill.skillId}/versions/v${skill.version}/exports/sop.pdf`
    return {
      exportKey,
      skillId: skill.skillId,
      title: skill.title,
      version: skill.version,
      pageCount: skill.steps.length + 1,
      generatedAt: new Date().toISOString()
    }
  }
}

export const defaultPdfExportService = new PdfExportService()

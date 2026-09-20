import type { SkillPackage } from '@skilltwin/contracts'

export interface SkillRepository {
  list(): Promise<SkillPackage[]>
  get(skillId: string): Promise<SkillPackage | null>
  save(skill: SkillPackage): Promise<SkillPackage>
}

export class InMemorySkillRepository implements SkillRepository {
  private readonly skills = new Map<string, SkillPackage>()

  constructor(initialSkills: SkillPackage[] = []) {
    for (const skill of initialSkills) {
      this.skills.set(skill.skillId, structuredClone(skill))
    }
  }

  async list(): Promise<SkillPackage[]> {
    return Array.from(this.skills.values(), (skill) => structuredClone(skill))
  }

  async get(skillId: string): Promise<SkillPackage | null> {
    const skill = this.skills.get(skillId)
    return skill ? structuredClone(skill) : null
  }

  async save(skill: SkillPackage): Promise<SkillPackage> {
    const stored = structuredClone(skill)
    this.skills.set(stored.skillId, stored)
    return structuredClone(stored)
  }
}

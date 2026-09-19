import React from 'react'
import { DemoBadge } from './DemoBadge.js'

interface HeaderProps {
  currentTab: string
  onTabChange: (tab: string) => void
}

export const Header: React.FC<HeaderProps> = ({ currentTab, onTabChange }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'upload', label: 'Upload' },
    { id: 'processing', label: 'Processing' },
    { id: 'review', label: 'Review' },
    { id: 'published', label: 'Published Skill' },
    { id: 'guided', label: 'Guided Mode' },
    { id: 'completion', label: 'Completion Report' }
  ]

  return (
    <header className="navBar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div
          onClick={() => onTabChange('dashboard')}
          style={{
            cursor: 'pointer',
            fontSize: '20px',
            fontWeight: 700,
            background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '-0.02em'
          }}
        >
          SkillTwin
        </div>
        <DemoBadge />
      </div>

      <nav className="navLinks">
        {navItems.map((item) => (
          <button
            key={item.id}
            id={`nav-tab-${item.id}`}
            className={`navLink ${currentTab === item.id ? 'navLinkActive' : ''}`}
            onClick={() => onTabChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  )
}

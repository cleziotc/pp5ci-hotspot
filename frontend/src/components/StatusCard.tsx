import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

type Props = {
  icon: LucideIcon
  title: string
  state: string
  line1: string
  line2: string
  tone?: 'good' | 'warn' | 'danger' | 'info'
  extra?: ReactNode
}

export default function StatusCard({ icon: Icon, title, state, line1, line2, tone = 'good', extra }: Props) {
  return (
    <div className="status-card">
      <Icon className="status-icon" size={36} strokeWidth={1.8} />
      <div className="status-card-copy">
        <strong className="status-title">{title}</strong>
        <div className="status-state-row">
          <div className={'status-state ' + tone}><span>●</span> {state}</div>
          {extra ? <div className="status-card-extra">{extra}</div> : null}
        </div>
        <small>{line1}</small>
        <small>{line2}</small>
      </div>
    </div>
  )
}

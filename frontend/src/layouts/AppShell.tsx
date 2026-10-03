import type { PropsWithChildren } from 'react'
import { useEffect, useState } from 'react'
import { Activity, BarChart3, Info, LayoutDashboard, RadioTower, RefreshCw, Settings } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { getStatus, type HotspotStatus } from '../api/client'

const nav = [
  ['/', 'Dashboard', LayoutDashboard],
  ['/statistics', 'Estatísticas', BarChart3],
  ['/diagnostics', 'Diagnósticos', Activity],
  ['/settings', 'Configurações', Settings],
  ['/updates', 'Atualizações', RefreshCw],
  ['/about', 'Sobre', Info],
] as const

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div className="header-clock">
      <small>{now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' })}</small>
      <strong>{now.toLocaleTimeString('pt-BR')}</strong>
    </div>
  )
}

export default function AppShell({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<HotspotStatus | null>(null)

  useEffect(() => {
    let mounted = true
    const refresh = async () => {
      try {
        const next = await getStatus()
        if (mounted) setStatus(next)
      } catch {
        if (mounted) setStatus(null)
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => {
      mounted = false
      window.clearInterval(timer)
    }
  }, [])

  const online = Boolean(
    status?.modem.online &&
    status.services.mmdvmhost.active === 'active' &&
    status.services.dstargateway.active === 'active',
  )
  const title = status?.hotspot.callsign
    ? `${status.hotspot.callsign} ${status.hotspot.name || 'PP5CI Hotspot'}`
    : 'PP5CI Hotspot'

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><span className="brand-mark"><RadioTower size={19} /></span><div><strong>{title}</strong><small>D-STAR / Linux Gateway · PP5CI-Hotspot</small></div></div>
        <nav className="top-nav">
          {nav.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === '/'}><Icon size={18} /><span>{label}</span></NavLink>
          ))}
        </nav>
        <div className="header-right">
          <div className={'online-pill ' + (online ? '' : 'offline')}><span>●</span> {online ? 'HOTSPOT ONLINE' : 'HOTSPOT OFFLINE'}</div>
          <Clock />
        </div>
      </header>
      <main className="app-page">{children}</main>
    </div>
  )
}

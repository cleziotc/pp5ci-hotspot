import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, Clock3, Cpu, Network, RadioTower, Usb } from 'lucide-react'
import { getDiagnostics, restartDiagnosticService, runDstarCheck, runSerialCheck, type DiagnosticsState } from '../api/client'
import Panel from '../components/Panel'
import StatusCard from '../components/StatusCard'

function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  const total = Math.max(0, Math.round(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  if (minutes) return `${minutes}m`
  return `${total}s`
}

function ago(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '—'
  if (seconds < 1) return 'agora'
  if (seconds < 60) return `${Math.round(seconds)}s atrás`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m atrás`
  return `${Math.round(seconds / 3600)}h atrás`
}

function shortSince(value: string | null): string {
  if (!value || value === 'n/a') return '—'
  return value.replace(/^[A-Za-z]{3}\s+/, '').replace(/\s+[A-Z]{2,5}$/, '')
}

function firmwareShort(value: string | null): string {
  if (!value) return '—'
  const match = value.match(/v\d+(?:\.\d+)+/i)
  return match?.[0] || value.slice(0, 22)
}

export default function DiagnosticsPage() {
  const [data, setData] = useState<DiagnosticsState | null>(null)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const logsRef = useRef<HTMLPreElement | null>(null)
  const logsStickToBottom = useRef(true)

  const refresh = useCallback(async () => {
    try {
      setData(await getDiagnostics())
    } catch (error) {
      setNotice({ ok: false, text: error instanceof Error ? error.message : 'Falha ao atualizar diagnósticos' })
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    const element = logsRef.current
    if (!element || !data?.logs.length || !logsStickToBottom.current) return
    element.scrollTop = element.scrollHeight
  }, [data?.logs])

  const onLogsScroll = () => {
    const element = logsRef.current
    if (!element) return
    logsStickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24
  }

  const serviceMap = useMemo(() => new Map((data?.services ?? []).map((service) => [service.unit, service])), [data])
  const host = serviceMap.get('pp5ci-hotspot-host.service')
  const gateway = serviceMap.get('polar-dstargateway.service')
  const serialHealthy = Boolean(data?.serial.present && host?.active === 'active')
  const portsHealthy = Boolean(data?.ports.length && data.ports.every((port) => port.listening))
  const adminToken = sessionStorage.getItem('polar-admin-token') || ''

  const action = async (name: string, fn: () => Promise<{ ok: boolean; message?: string }>) => {
    setBusy(name)
    setNotice(null)
    try {
      const result = await fn()
      setNotice({ ok: result.ok, text: result.message || (result.ok ? 'Operação concluída.' : 'Operação retornou falha.') })
      await refresh()
    } catch (error) {
      setNotice({ ok: false, text: error instanceof Error ? error.message : 'Falha na operação' })
    } finally {
      setBusy(null)
    }
  }

  const restart = async (target: 'mmdvmhost' | 'dstargateway') => {
    if (!adminToken) {
      setNotice({ ok: false, text: 'Habilite o modo administrador em Settings antes de reiniciar serviços.' })
      return
    }
    const label = target === 'mmdvmhost' ? 'MMDVMHost' : 'DStarGateway'
    if (!window.confirm(`Reiniciar ${label} agora?`)) return
    setBusy(target)
    setNotice(null)
    try {
      const result = await restartDiagnosticService(target, adminToken)
      setNotice({ ok: result.ok, text: `${label}: ${result.active}/${result.sub}, PID ${result.pid}` })
      window.setTimeout(() => void refresh(), 1200)
    } catch (error) {
      setNotice({ ok: false, text: error instanceof Error ? error.message : `Falha ao reiniciar ${label}` })
    } finally {
      setBusy(null)
    }
  }

  const exportLogs = async () => {
    if (!adminToken) {
      setNotice({ ok: false, text: 'Habilite o modo administrador em Settings antes de exportar logs.' })
      return
    }
    setBusy('logs')
    try {
      const response = await fetch('/api/v1/diagnostics/logs/export', { headers: { 'X-Polar-Admin-Token': adminToken } })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'pp5ci-hotspot-diagnostics.log'
      anchor.click()
      URL.revokeObjectURL(url)
      setNotice({ ok: true, text: 'Logs exportados.' })
    } catch (error) {
      setNotice({ ok: false, text: error instanceof Error ? error.message : 'Falha ao exportar logs' })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="standard-page diagnostics-page diagnostics-live">
      {notice ? <div className={'diag-notice ' + (notice.ok ? 'ok' : 'bad')}>{notice.text}</div> : null}

      <div className="status-grid six">
        <StatusCard icon={Cpu} title="MMDVM Modem" state={serialHealthy ? 'ONLINE' : 'OFFLINE'} line1={data ? `FW ${firmwareShort(data.serial.firmware)}` : 'Carregando…'} line2={data?.serial.usb_chip || '—'} />
        <StatusCard icon={Activity} title="MMDVMHost" state={host?.active === 'active' ? 'ONLINE' : (host?.active || 'UNKNOWN').toUpperCase()} line1="D-STAR" line2={data ? `UART ${data.serial.baud}` : '—'} />
        <StatusCard icon={RadioTower} title="DStarGateway" state={gateway?.active === 'active' ? 'CONNECTED' : (gateway?.active || 'UNKNOWN').toUpperCase()} line1={gateway?.sub || '—'} line2={data ? `Last activity: ${ago(data.metrics.last_activity_seconds)}` : '—'} />
        <StatusCard icon={Usb} title="Serial / USB" state={serialHealthy ? 'HEALTHY' : 'CHECK'} line1={data?.serial.device || '—'} line2={data ? `${data.serial.usb_chip} @ ${data.serial.baud}` : '—'} />
        <StatusCard icon={Network} title="Network" state={portsHealthy ? 'HEALTHY' : 'CHECK'} line1={data?.ports[0]?.address || '—'} line2={data ? `UDP ${data.ports.map((port) => port.port).join(' / ')}` : '—'} />
        <StatusCard icon={Clock3} title="Scheduler" state={data?.timer.active === 'active' ? 'HEALTHY' : 'CHECK'} line1={data ? `Next run ${data.timer.schedule}` : '—'} line2={data ? `Timer ${data.timer.active}/${data.timer.sub}` : '—'} />
      </div>

      <div className="diag-middle">
        <Panel title="⌁ Service Health">
          <div className="diag-table-scroll">
            <table className="data-table">
              <thead><tr><th>SERVICE</th><th>STATE</th><th>PID</th><th>UPTIME</th><th>SINCE</th></tr></thead>
              <tbody>
                {(data?.services ?? []).map((service) => (
                  <tr key={service.unit}>
                    <td><b>{service.label}</b></td>
                    <td className={service.active === 'active' ? 'good-text' : 'warn-text'}>● {service.active.toUpperCase()} / {service.sub}</td>
                    <td>{service.pid || '—'}</td>
                    <td>{formatDuration(service.uptime_seconds)}</td>
                    <td>{shortSince(service.since)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="USB Serial / Diagnostics">
          <div className="info-list diag-info-list">
            <p><span>Configured</span><b title={data?.serial.configured_device}>{data?.serial.configured_device || '—'}</b></p>
            <p><span>Resolved Device</span><b>{data?.serial.device || '—'}</b></p>
            <p><span>USB Chip</span><b>{data?.serial.usb_chip || '—'}</b></p>
            <p><span>VID:PID</span><b>{data?.serial.vendor_id && data?.serial.product_id ? `${data.serial.vendor_id}:${data.serial.product_id}` : '—'}</b></p>
            <p><span>Baud Rate</span><b>{data?.serial.baud || '—'}</b></p>
            <p><span>Format</span><b>{data?.serial.format || '—'}</b></p>
            <p><span>Firmware</span><b className="diag-firmware" title={data?.serial.firmware || ''}>{data?.serial.firmware || '—'}</b></p>
            <p><span>Status</span><b className={serialHealthy ? 'good-text' : 'warn-text'}>● {serialHealthy ? 'OK - Serial link active' : 'Serial check required'}</b></p>
          </div>
        </Panel>

        <div className="diag-right-stack">
          <Panel title="UDP / Ports">
            <table className="data-table compact">
              <thead><tr><th>PORT</th><th>ENDPOINT</th><th>ADDRESS</th><th>STATUS</th></tr></thead>
              <tbody>{(data?.ports ?? []).map((port) => <tr key={port.port}><td><b>{port.port}</b></td><td>{port.protocol}</td><td>{port.address}</td><td className={port.listening ? 'good-text' : 'warn-text'}>● {port.listening ? 'BOUND' : 'NOT BOUND'}</td></tr>)}</tbody>
            </table>
          </Panel>
          <Panel title="RF / Modem Metrics">
            <div className="metric-columns">
              <div className="info-list small">
                <p><span>BER (last)</span><b>{data?.metrics.ber_percent === null || data?.metrics.ber_percent === undefined ? '—' : `${data.metrics.ber_percent}%`}</b></p>
                <p><span>RSSI (last)</span><b>{data?.metrics.rssi_dbm === null || data?.metrics.rssi_dbm === undefined ? '—' : `${data.metrics.rssi_dbm} dBm`}</b></p>
                <p><span>RF Level</span><b>{data ? `${data.metrics.rf_level_percent}%` : '—'}</b></p>
                <p><span>RX Level</span><b>{data ? `${data.metrics.rx_level_percent}%` : '—'}</b></p>
              </div>
              <div className="info-list small">
                <p><span>D-Star TX</span><b>{data ? `${data.metrics.dstar_tx_level_percent}%` : '—'}</b></p>
                <p><span>Last activity</span><b>{data ? ago(data.metrics.last_activity_seconds) : '—'}</b></p>
                <p><span>QSOs stored</span><b>{data?.metrics.total_transmissions.toLocaleString('pt-BR') ?? '—'}</b></p>
                <p><span>System load</span><b>{data?.system.load.load_1m ?? '—'}</b></p>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <div className="diag-bottom">
        <Panel title="Recent Logs" className="log-panel"><pre ref={logsRef} onScroll={onLogsScroll}>{data?.logs.length ? data.logs.join('\n') : 'Nenhum log disponível.'}</pre></Panel>
        <Panel title="Last Checks">
          <table className="data-table compact">
            <thead><tr><th>CHECK</th><th>RESULT</th><th>DETAIL</th></tr></thead>
            <tbody>{(data?.checks ?? []).map((check) => <tr key={check.name}><td>{check.name}</td><td className={check.ok ? 'good-text' : 'warn-text'}>● {check.ok ? 'OK' : 'CHECK'}</td><td>{check.detail}</td></tr>)}</tbody>
          </table>
        </Panel>
        <Panel title="Actions / Tools" className="actions-panel">
          <button disabled={Boolean(busy)} onClick={() => void restart('mmdvmhost')}>↻ Restart MMDVMHost</button>
          <button disabled={Boolean(busy)} onClick={() => void restart('dstargateway')}>↻ Restart DStarGateway</button>
          <button disabled={Boolean(busy)} onClick={() => void exportLogs()}>▤ Export Logs</button>
          <button className="good-action" disabled={Boolean(busy)} onClick={() => void action('dstar', runDstarCheck)}>▶ Run D-Star Path Check</button>
          <button disabled={Boolean(busy)} onClick={() => void action('serial', runSerialCheck)}>⚙ Run Serial Check</button>
          <small className="diag-admin-hint">{adminToken ? 'Admin session available for restart/export.' : 'Restart/export require admin session from Settings.'}</small>
        </Panel>
      </div>
    </div>
  )
}

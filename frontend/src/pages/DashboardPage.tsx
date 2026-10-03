import { useEffect, useMemo, useRef, useState } from 'react'
import { Cpu, Globe2, Radio, RadioTower, Server, SquareStack } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getStatistics, getStatus, getTransmissions, type HotspotStatus, type Statistics, type Transmission } from '../api/client'
import { getNetworkQuality, type NetworkQuality } from '../api/network'
import LiveMetricChart from '../components/LiveMetricChart'
import NetworkQualityPanel from '../components/NetworkQualityPanel'
import Panel from '../components/Panel'
import StatusCard from '../components/StatusCard'
import TransmissionQuality from '../components/TransmissionQuality'

function formatDuration(value: number | null | undefined): string {
  const seconds = Math.max(0, Number(value || 0))
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = Math.floor(seconds % 60)
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m ${rest}s`
}

function formatTrafficDuration(value: number | null | undefined): string {
  const seconds = Math.max(0, Number(value || 0))
  const tenths = Math.floor((seconds * 10) % 10)
  const whole = Math.floor(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = whole % 60
  if (hours > 0) return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`
}

function formatClock(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('pt-BR', { hour12: false })
}

function formatFrequency(hz: number | null | undefined): string {
  return hz ? `${(hz / 1_000_000).toFixed(6)} MHz` : '—'
}

function directionLabel(value: string | null | undefined): string {
  if (value === 'RF_TO_NET') return 'RF → NET'
  if (value === 'NET_TO_RF') return 'NET → RF'
  return '—'
}

function serviceOnline(status: HotspotStatus | null, key: 'mmdvmhost' | 'dstargateway'): boolean {
  return status?.services[key].active === 'active'
}

function appendSample(current: number[], value: number, limit = 72): number[] {
  return [...current.slice(-(limit - 1)), value]
}

function networkStateLabel(state: string | undefined): string {
  if (state === 'good') return 'BOA'
  if (state === 'degraded') return 'ATENÇÃO'
  if (state === 'poor') return 'RUIM'
  return 'MEDINDO'
}

function networkTone(state: string | undefined): 'good' | 'warn' | 'danger' | 'info' {
  if (state === 'good') return 'good'
  if (state === 'degraded') return 'warn'
  if (state === 'poor') return 'danger'
  return 'info'
}

function metric(value: number | null | undefined, suffix: string, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toFixed(digits)} ${suffix}`
}

function reflectorHealthLabel(state: string | undefined): string {
  if (state === 'good') return 'Normal'
  if (state === 'degraded') return 'Atenção'
  if (state === 'poor') return 'Ruim'
  return 'Medindo'
}

function StatusSparkBars({ samples }: { samples: Array<{ success: boolean; rtt_ms: number | null }> }) {
  const values = samples.slice(-8)
  const valid = values.flatMap((sample) => sample.success && typeof sample.rtt_ms === 'number' ? [sample.rtt_ms] : [])
  const max = Math.max(1, ...valid)
  return (
    <span className="status-mini-bars" aria-hidden="true">
      {values.map((sample, index) => {
        const height = sample.success && typeof sample.rtt_ms === 'number'
          ? Math.max(4, Math.min(18, (sample.rtt_ms / max) * 18))
          : 18
        const cls = !sample.success
          ? 'lost'
          : typeof sample.rtt_ms === 'number' && sample.rtt_ms > 260
            ? 'poor'
            : typeof sample.rtt_ms === 'number' && sample.rtt_ms > 100
              ? 'degraded'
              : 'good'
        return <i key={index} className={cls} style={{ height }} />
      })}
    </span>
  )
}

export default function DashboardPage() {
  const [status, setStatus] = useState<HotspotStatus | null>(null)
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [transmissions, setTransmissions] = useState<Transmission[]>([])
  const [networkQuality, setNetworkQuality] = useState<NetworkQuality | null>(null)
  const [berSamples, setBerSamples] = useState<number[]>([])
  const [rssiSamples, setRssiSamples] = useState<number[]>([])
  const [now, setNow] = useState(Date.now())
  const scopeRef = useRef<{ reflector: string | null; callsign: string | null }>({ reflector: null, callsign: null })

  useEffect(() => {
    let mounted = true
    let lastTrafficState = 'idle'
    let fallbackPoll: number | null = null
    let rfSessionKey: string | null = null
    let lastBerMarker: string | null = null
    let lastRssiMarker: string | null = null

    const ingestLiveMetrics = (traffic: HotspotStatus['traffic']) => {
      const rfLive = traffic.state === 'active' && traffic.direction === 'RF_TO_NET'
      if (!rfLive) return
      const sessionKey = traffic.started_at || 'rf-session'
      if (sessionKey !== rfSessionKey) {
        rfSessionKey = sessionKey
        lastBerMarker = null
        lastRssiMarker = null
        setBerSamples([])
        setRssiSamples([])
      }
      if (typeof traffic.ber_percent === 'number') {
        const marker = traffic.ber_updated_at || `ber:${traffic.updated_at || ''}`
        if (marker !== lastBerMarker) {
          lastBerMarker = marker
          setBerSamples((values) => appendSample(values, traffic.ber_percent as number))
        }
      }
      if (typeof traffic.rssi_dbm === 'number') {
        const marker = traffic.rssi_updated_at || `rssi:${traffic.updated_at || ''}`
        if (marker !== lastRssiMarker) {
          lastRssiMarker = marker
          setRssiSamples((values) => appendSample(values, traffic.rssi_dbm as number))
        }
      }
    }

    const refreshSummary = async (scope = scopeRef.current) => {
      const [statsResult, txResult] = await Promise.allSettled([
        getStatistics(scope.reflector, scope.callsign),
        getTransmissions(8),
      ])
      if (!mounted) return
      if (statsResult.status === 'fulfilled') setStatistics(statsResult.value)
      if (txResult.status === 'fulfilled') setTransmissions(txResult.value.items)
    }

    const scopeForStatus = (nextStatus: HotspotStatus) => {
      const direct = nextStatus.traffic.state === 'active'
        && nextStatus.traffic.route_type === 'callsign'
        && nextStatus.traffic.contact_callsign
      return direct
        ? { reflector: null, callsign: nextStatus.traffic.contact_callsign || null }
        : { reflector: nextStatus.link.reflector || null, callsign: null }
    }

    const refreshStatus = async (): Promise<boolean> => {
      try {
        const nextStatus = await getStatus()
        if (!mounted) return false
        const previous = scopeRef.current
        const nextScope = scopeForStatus(nextStatus)
        scopeRef.current = nextScope
        lastTrafficState = nextStatus.traffic.state
        setStatus(nextStatus)
        ingestLiveMetrics(nextStatus.traffic)
        return previous.reflector !== nextScope.reflector || previous.callsign !== nextScope.callsign
      } catch {
        // Preserva o último snapshot válido.
        return false
      }
    }

    const refreshNetwork = async () => {
      try {
        const next = await getNetworkQuality()
        if (mounted) setNetworkQuality(next)
      } catch {
        // Preserva a última medição válida; rede não interfere na cadeia RF.
      }
    }

    const stopFallback = () => {
      if (fallbackPoll !== null) {
        window.clearInterval(fallbackPoll)
        fallbackPoll = null
      }
    }
    const startFallback = () => {
      if (fallbackPoll !== null) return
      fallbackPoll = window.setInterval(() => void refreshStatus(), 500)
    }

    void (async () => {
      await refreshStatus()
      await refreshSummary(scopeRef.current)
    })()
    void refreshNetwork()
    const statusPoll = window.setInterval(() => {
      void refreshStatus().then((changed) => {
        if (changed) void refreshSummary(scopeRef.current)
      })
    }, 10_000)
    const summaryPoll = window.setInterval(() => void refreshSummary(), 10_000)
    const networkPoll = window.setInterval(() => void refreshNetwork(), 5_000)
    const clock = window.setInterval(() => setNow(Date.now()), 100)

    const stream = new EventSource('/api/v1/events')
    stream.onopen = () => stopFallback()
    stream.onerror = () => startFallback()
    stream.addEventListener('traffic', (rawEvent) => {
      if (!mounted) return
      try {
        const traffic = JSON.parse((rawEvent as MessageEvent).data) as HotspotStatus['traffic']
        const ended = lastTrafficState === 'active' && traffic.state === 'idle'
        lastTrafficState = traffic.state
        ingestLiveMetrics(traffic)
        setStatus((current) => {
          if (!current) return current
          const nextStatus = { ...current, traffic }
          const previous = scopeRef.current
          const direct = traffic.state === 'active' && traffic.route_type === 'callsign' && traffic.contact_callsign
          const nextScope = direct
            ? { reflector: null, callsign: traffic.contact_callsign || null }
            : { reflector: nextStatus.link.reflector || null, callsign: null }
          scopeRef.current = nextScope
          if (previous.reflector !== nextScope.reflector || previous.callsign !== nextScope.callsign) {
            void refreshSummary(nextScope)
          }
          return nextStatus
        })
        if (ended) {
          void refreshStatus().then(() => void refreshSummary(scopeRef.current))
          void refreshNetwork()
        }
      } catch {
        // Preserva o estado atual.
      }
    })

    return () => {
      mounted = false
      stream.close()
      stopFallback()
      window.clearInterval(statusPoll)
      window.clearInterval(summaryPoll)
      window.clearInterval(networkPoll)
      window.clearInterval(clock)
    }
  }, [])

  const trafficDuration = useMemo(() => {
    if (status?.traffic.state !== 'active' || !status.traffic.started_at) return 0
    const start = new Date(status.traffic.started_at).getTime()
    return Number.isFinite(start) ? Math.max(0, (now - start) / 1000) : 0
  }, [status, now])

  const hostOnline = serviceOnline(status, 'mmdvmhost')
  const gatewayOnline = serviceOnline(status, 'dstargateway')
  const systemHealthy = Boolean(status?.modem.online && hostOnline && gatewayOnline)
  const active = status?.traffic.state === 'active'
  const trafficDirection = status?.traffic.direction
  const rfLive = active && trafficDirection === 'RF_TO_NET'
  const rfState = active ? (trafficDirection === 'RF_TO_NET' ? 'RX' : 'TX') : status ? 'PRONTO' : 'SEM DADOS'
  const flowClass = active ? (trafficDirection === 'RF_TO_NET' ? 'flow-rf-net' : trafficDirection === 'NET_TO_RF' ? 'flow-net-rf' : '') : ''
  const directContact = active && status?.traffic.route_type === 'callsign' ? status.traffic.contact_callsign || null : null
  const target = directContact || status?.link.reflector || (active && trafficDirection === 'NET_TO_RF' ? status?.traffic.src_ext : null) || status?.traffic.destination || '—'
  const stationProfile = active && status?.traffic.station ? transmissions.find((row) => row.src_callsign === status.traffic.station && Boolean(row.name || row.location)) : undefined
  const stationName = status?.traffic.name || stationProfile?.name || '—'
  const stationLocation = status?.traffic.location || stationProfile?.location || '—'
  const lastRfRadio = transmissions.find((row) => row.direction === 'RF_TO_NET' && row.src_ext)?.src_ext
  const radioLabel = active && trafficDirection === 'RF_TO_NET' ? status?.traffic.src_ext || lastRfRadio || 'Rádio' : lastRfRadio || 'Rádio'
  const routeLabel = active ? (trafficDirection === 'RF_TO_NET' ? `${status?.traffic.src_ext || 'RF'} → ${target}` : `${target} → RF`) : ''

  const currentReflector = status?.link.reflector || null
  const summaryReflector = directContact ? null : currentReflector
  const summaryCallsign = directContact
  const summaryLabel = summaryCallsign ? `Direto · ${summaryCallsign}` : summaryReflector || 'Sem destino'
  const summaryReady = Boolean(
    summaryCallsign
      ? statistics?.scope.callsign === summaryCallsign
      : summaryReflector && statistics?.scope.reflector === summaryReflector
  )
  const today = summaryReady ? statistics?.today : undefined
  const rfToday = Number(today?.rf_to_net_seconds || 0)
  const netToday = Number(today?.net_to_rf_seconds || 0)
  const airtimeTotal = rfToday + netToday
  const rfPercent = airtimeTotal > 0 ? Math.round((rfToday / airtimeTotal) * 100) : 0
  const netPercent = airtimeTotal > 0 ? 100 - rfPercent : 0
  const load = status?.system.load['1m']
  const memory = status?.system.memory_percent

  const berEmpty = rfLive ? (trafficDuration > 1.5 ? 'Aguardando amostras BER' : 'Iniciando medição…') : berSamples.length ? 'Última transmissão RF' : 'Aguardando transmissão RF'
  const rssiEmpty = rfLive ? (trafficDuration > 2 ? 'RSSI não fornecido pelo modem' : 'Aguardando RSSI…') : rssiSamples.length ? 'Última transmissão RF' : 'Aguardando transmissão RF'

  const net = networkQuality?.reflector
  const networkLine1 = net?.name
    ? `${net.name}${net.ip ? ` (${net.ip})` : ''}`
    : status?.link.reflector || 'Sem reflector ativo'
  const networkLine2 = net?.sample_count
    ? `Latência ${metric(net.latency_ms, 'ms')} · Jitter ${metric(net.jitter_ms, 'ms', 1)} · Perda ${metric(net.loss_percent, '%', 1)}`
    : 'Coletando sonda TCP · sem ICMP'
  const linked = Boolean(status?.link.reflector && gatewayOnline)
  const durationAlarm = active && trafficDuration >= 150 ? 'critical' : active && trafficDuration >= 120 ? 'warning' : ''
  const dstarProtocol = networkQuality?.dstar.protocol || null
  const dstarUdpPort = networkQuality?.dstar.udp_port || null
  const dstarFrequency = dstarUdpPort
    ? `UDP ${dstarUdpPort}${dstarProtocol ? ` (${dstarProtocol})` : ''}`
    : '—'
  const lastPacketAge = net?.last_sample_age_seconds !== null && net?.last_sample_age_seconds !== undefined
    ? `${net.last_sample_age_seconds.toFixed(net.last_sample_age_seconds < 10 ? 1 : 0)} s atrás`
    : '—'

  return (
    <div className="dashboard-page dashboard-v4">
      <div className="status-grid dashboard-status-grid dashboard-status-grid-v4">
        <StatusCard icon={SquareStack} title="MMDVM Modem" state={status?.modem.online ? 'ONLINE' : status ? 'OFFLINE' : 'NO DATA'} tone={status?.modem.online ? 'good' : 'danger'}
          line1={status ? status.modem.serial_present ? `${status.modem.resolved_device || status.modem.device || 'Serial'} · ${status.modem.baud} bps` : 'Serial indisponível' : 'API indisponível'}
          line2={status ? `RF ${status.modem.rf_level_percent}% · RX ${status.modem.rx_level_percent}% · D-Star TX ${status.modem.dstar_tx_level_percent}%` : '—'} />
        <StatusCard icon={Cpu} title="MMDVMHost" state={hostOnline ? 'ONLINE' : status ? 'OFFLINE' : 'NO DATA'} tone={hostOnline ? 'good' : 'danger'} line1="D-STAR only" line2={status ? `MQTT ${status.mqtt.connected ? 'conectado' : 'desconectado'}` : 'API indisponível'} />
        <StatusCard icon={RadioTower} title="DStarGateway" state={gatewayOnline ? 'CONECTADO' : status ? 'OFFLINE' : 'SEM DADOS'} tone={gatewayOnline ? 'good' : 'danger'} line1={status ? `${status.network.gateway_address}:${status.network.gateway_port}` : '—'} line2={status ? `ircDDB ${status.link.callsign_routing?.enabled ? 'ON' : 'OFF'} · ${status.link.reflector || 'sem reflector'}` : '—'} />
        <StatusCard icon={Globe2} title="Rede / Reflector" state={networkStateLabel(net?.state)} tone={networkTone(net?.state)} line1={networkLine1} line2={networkLine2} extra={<StatusSparkBars samples={net?.samples ?? []} />} />
        <StatusCard icon={Radio} title="RF (Transceptor)" state={rfState} tone={active ? 'info' : status ? 'good' : 'danger'} line1={formatFrequency(status?.hotspot.rx_frequency_hz)} line2={status ? `DV simplex / módulo ${status.hotspot.module}` : '—'} />
        <StatusCard icon={Server} title="Sistema" state={systemHealthy ? 'SAUDÁVEL' : status ? 'ATENÇÃO' : 'SEM DADOS'} tone={systemHealthy ? 'good' : 'warn'} line1={status ? `Load ${load ?? '—'} · RAM ${memory ?? '—'}%` : 'API indisponível'} line2={status ? `Uptime ${formatDuration(status.system.uptime_seconds)}` : '—'} />
      </div>

      <div className="dashboard-main dashboard-main-v4">
        <Panel title="◉ Tráfego ao Vivo" className="live-traffic live-traffic-v4">
          <div className="live-topline">
            <span className={'idle-pill ' + (active ? 'active' : '')}>{active && <i className="on-air-dot" aria-hidden="true" />}{active ? 'ON AIR' : 'IDLE'}</span>
            <div className={'duration-box ' + durationAlarm}><small>Duração</small><strong>{formatTrafficDuration(active ? trafficDuration : 0)}</strong></div>
          </div>
          <div className={'traffic-state ' + (active ? 'active' : '')}>{active ? (directContact ? 'CALLSIGN ROUTING' : directionLabel(trafficDirection)) : 'IDLE'}</div>
          <div className={'traffic-flow ' + (active ? 'active ' : '') + flowClass}>
            <div className="traffic-node"><Radio size={42} /><b>{active ? radioLabel : 'Rádio'}</b><small>D-STAR (RF)</small></div><span className="traffic-link" />
            <div className="traffic-node"><SquareStack size={42} /><b>MMDVM</b><small>Modem</small></div><span className="traffic-link" />
            <div className="traffic-node"><Server size={42} /><b>Gateway</b><small>D-STAR</small></div><span className="traffic-link" />
            <div className="traffic-node"><RadioTower size={42} /><b>{active ? target : '—'}</b><small>{active ? (directContact ? 'Destino direto' : 'Reflector') : 'Destino (NET)'}</small></div>
          </div>
          <div className={'traffic-current ' + (active ? 'active' : '')}>
            <strong>{active ? status?.traffic.station || '—' : '--'}</strong>
            {active ? <>
              <b className="traffic-person">{stationName}</b>
              {status?.traffic.slow_text ? <span className="traffic-message">{status.traffic.slow_text}</span> : null}
              <span className="traffic-location">{stationLocation}</span>
              <small className="traffic-meta">{routeLabel}{directContact ? ' · ircDDB / QuadNet' : status?.link.reflector ? ` · ${status.link.reflector}` : ''}</small>
            </> : <small>Aguardando tráfego D-STAR</small>}
          </div>
        </Panel>

        <NetworkQualityPanel quality={networkQuality} />

        <Panel title={`▣ Resumo de Hoje · ${summaryLabel}`} className="today-panel today-panel-v4">
          <small className="today-scope-label">{summaryCallsign ? 'chamada direta por indicativo' : summaryReflector ? 'reflector atual' : 'sem destino ativo'}</small>
          <div className="today-grid">
            <div><strong>{today?.transmissions ?? '—'}</strong><small>transmissões</small></div>
            <div><strong>{today ? formatDuration(today.airtime_seconds) : '—'}</strong><small>tempo de uso</small></div>
            <div><strong>{today ? formatDuration(today.rf_to_net_seconds) : '—'}</strong><small>RF → NET</small></div>
            <div><strong>{today ? formatDuration(today.net_to_rf_seconds) : '—'}</strong><small>NET → RF</small></div>
          </div>
        </Panel>
      </div>

      <div className="dashboard-lower dashboard-lower-v4">
        <Panel className="last-heard last-heard-v4">
          <div className="panel-heading-row"><h2>◉ Últimas Transmissões</h2><Link to="/statistics">Ver todas →</Link></div>
          <table className="data-table dashboard-heard-table">
            <thead><tr><th>HORÁRIO</th><th>DIREÇÃO</th><th>INDICATIVO</th><th>NOME</th><th>LOCALIZAÇÃO</th><th>DURAÇÃO</th><th>BER</th><th>LOSS</th></tr></thead>
            <tbody>{transmissions.length ? transmissions.map((row) => <tr key={row.id}><td>{formatClock(row.started_at)}</td><td><span className={'direction-pill ' + (row.direction === 'RF_TO_NET' ? 'rf-net' : 'net-rf')}>{directionLabel(row.direction)}</span></td><td><b>{row.src_callsign || '—'}</b></td><td>{row.name || '—'}</td><td>{row.location || '—'}</td><td>{formatDuration(row.duration_seconds)}</td><td><TransmissionQuality kind="ber" value={row.ber_percent} applicable={row.direction === 'RF_TO_NET'} /></td><td><TransmissionQuality kind="loss" value={row.packet_loss_percent} applicable={row.direction === 'NET_TO_RF'} /></td></tr>) : <tr><td colSpan={8} className="empty-cell">Nenhuma transmissão registrada</td></tr>}</tbody>
          </table>
        </Panel>

        <div className="dashboard-right-v4">
          <div className="dashboard-live-metrics dashboard-live-metrics-v4">
            <LiveMetricChart title="BER ao Vivo" subtitle="Qualidade do sinal RF" value={rfLive ? status?.traffic.ber_percent ?? null : berSamples.at(-1) ?? null} unit="%" samples={berSamples} variant="green" live={rfLive} emptyText={berEmpty} minFloor={0} />
            <LiveMetricChart title="RSSI ao Vivo" subtitle="Nível de sinal RF" value={rfLive ? status?.traffic.rssi_dbm ?? null : rssiSamples.at(-1) ?? null} unit="dBm" samples={rssiSamples} variant="blue" live={rfLive} emptyText={rssiEmpty} fixedRange={[-130, -30]} />
          </div>

          <div className="dashboard-bottom-v4">
            <Panel title={`◷ Tempo de Uso (Airtime) · Hoje · ${summaryLabel}`} className="airtime-panel">
              <div className="split-bar"><i style={{ width: rfPercent + '%' }} /><i style={{ width: netPercent + '%' }} /></div>
              <div className="split-caption"><span>RF → NET {rfPercent}% ({formatDuration(rfToday)})</span><span>NET → RF {netPercent}% ({formatDuration(netToday)})</span></div>
            </Panel>

            <Panel title="◉ Estado da Conexão com o Reflector" className="reflector-state-panel reflector-state-panel-v6">
              <div className={'reflector-connected ' + (linked ? 'on' : '')}><span>●</span> {linked ? 'CONECTADO' : 'DESCONECTADO'}</div>
              <div className="reflector-state-columns">
                <div className="reflector-state-column">
                  <span><small>Reflector</small><b>{status?.link.reflector || '—'}</b></span>
                  <span><small>IP</small><b>{net?.ip || '—'}</b></span>
                  <span><small>Frequência</small><b>{dstarFrequency}</b></span>
                </div>
                <div className="reflector-state-column">
                  <span><small>Último pacote</small><b>{lastPacketAge}</b></span>
                  <span><small>Estado</small><b>{reflectorHealthLabel(net?.state)}</b></span>
                  <span><small>Medição</small><b>Sonda TCP</b></span>
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  )
}

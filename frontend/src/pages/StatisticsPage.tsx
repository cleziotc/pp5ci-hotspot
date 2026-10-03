import { useCallback, useEffect, useMemo, useState } from 'react'
import { BarChart3, CalendarDays, Clock3, Radio } from 'lucide-react'
import { getSettings, getStatistics, getStatus, getTransmissions, type SettingsState, type Statistics, type Transmission } from '../api/client'
import { getNetworkHistory, type NetworkHistory } from '../api/network'
import DualBars from '../components/DualBars'
import NetworkHistoryPanel from '../components/NetworkHistoryPanel'
import Panel from '../components/Panel'
import PeriodBars from '../components/PeriodBars'
import TransmissionQuality from '../components/TransmissionQuality'
import ReflectorUsageChart from '../components/ReflectorUsageChart'
import CallsignUsageChart from '../components/CallsignUsageChart'

function formatDuration(value: number | null | undefined): string {
  const seconds = Math.max(0, Math.round(Number(value || 0)))
  if (seconds < 60) return `${seconds}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  if (hours > 0) return rest ? `${hours}h ${minutes}m ${rest}s` : `${hours}h ${minutes}m`
  return `${minutes}m ${rest}s`
}

function formatClock(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString('pt-BR', { hour12: false })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('pt-BR', { hour12: false })
}

function directionLabel(value: string): string {
  if (value === 'RF_TO_NET') return 'RF → NET'
  if (value === 'NET_TO_RF') return 'NET → RF'
  return value || '—'
}

function percent(part: number, total: number): number {
  return total > 0 ? Math.round((part / total) * 100) : 0
}

function LoadingPanel({ text }: { text: string }) {
  return <div className="stats-loading">{text}</div>
}

export default function StatisticsPage() {
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [transmissions, setTransmissions] = useState<Transmission[]>([])
  const [settings, setSettings] = useState<SettingsState | null>(null)
  const [networkHistory, setNetworkHistory] = useState<NetworkHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedScope, setSelectedScope] = useState('all')
  const [currentReflector, setCurrentReflector] = useState<string | null>(null)
  const [currentDirectCallsign, setCurrentDirectCallsign] = useState<string | null>(null)

  const scopeReflector = selectedScope.startsWith('reflector:') ? selectedScope.slice('reflector:'.length) : null
  const scopeCallsign = selectedScope.startsWith('callsign:') ? selectedScope.slice('callsign:'.length) : null

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      getStatistics(scopeReflector, scopeCallsign),
      getTransmissions(10, scopeReflector, scopeCallsign),
      getSettings(),
      scopeCallsign ? Promise.resolve(null) : getNetworkHistory(24, scopeReflector),
      getStatus(),
    ])

    if (results[0].status === 'fulfilled') setStatistics(results[0].value)
    if (results[1].status === 'fulfilled') setTransmissions(results[1].value.items)
    if (results[2].status === 'fulfilled') setSettings(results[2].value)
    if (results[3].status === 'fulfilled') setNetworkHistory(results[3].value)
    if (results[4].status === 'fulfilled') {
      const live = results[4].value
      setCurrentReflector(live.link.reflector || null)
      setCurrentDirectCallsign(
        live.traffic.state === 'active' && live.traffic.route_type === 'callsign'
          ? live.traffic.contact_callsign || null
          : null
      )
    }

    const failed = results.filter((result) => result.status === 'rejected')
    setError(failed.length ? 'Alguns dados estatísticos não puderam ser atualizados.' : null)
  }, [scopeReflector, scopeCallsign])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 10_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  const direction = statistics?.direction_30d
  const rfCount = direction?.rf_to_net ?? 0
  const netCount = direction?.net_to_rf ?? 0
  const directionTotal = rfCount + netCount
  const rfPercent = percent(rfCount, directionTotal)
  const netPercent = directionTotal > 0 ? 100 - rfPercent : 0

  const activityValues = useMemo(
    () => statistics?.hourly_24h.map((row) => ({ a: row.rf_to_net, b: row.net_to_rf })) ?? [],
    [statistics],
  )

  const activityLabels = useMemo(
    () => statistics?.hourly_24h.map((row, index) => (
      index === 0 || index === 23 || index % 4 === 0 ? row.label : ''
    )) ?? [],
    [statistics],
  )

  const directory = statistics?.directory_coverage_30d
  const hosts = settings?.hosts.files ?? []
  const reflectorOptions = useMemo(() => {
    const values = new Set(statistics?.available_reflectors ?? [])
    if (currentReflector) values.add(currentReflector)
    if (scopeReflector) values.add(scopeReflector)
    return Array.from(values).sort((a, b) => a.localeCompare(b))
  }, [statistics, currentReflector, scopeReflector])
  const callsignOptions = useMemo(() => {
    const items = (statistics?.callsign_usage_30d ?? []).map((row) => ({ callsign: row.callsign, name: row.name }))
    if (currentDirectCallsign && !items.some((item) => item.callsign === currentDirectCallsign)) {
      items.unshift({ callsign: currentDirectCallsign, name: null })
    }
    return items
  }, [statistics, currentDirectCallsign])
  const scopeLabel = statistics?.scope.label || (scopeCallsign ? `Direto · ${scopeCallsign}` : scopeReflector || 'Todos os destinos')

  return (
    <div className="standard-page statistics-page statistics-live statistics-v4">
      {error ? <div className="stats-notice">{error}</div> : null}

      <div className="stats-scope-bar">
        <div>
          <small>Escopo das estatísticas</small>
          <strong>{scopeLabel}</strong>
          <span>{scopeCallsign ? 'Estatísticas da conversa direta com este indicativo.' : scopeReflector ? 'Todos os gráficos, KPIs, Top Stations e Last Heard estão filtrados pelo reflector.' : 'Visão consolidada de reflectores e chamadas diretas.'}</span>
        </div>
        <label>
          <span>Destino</span>
          <select value={selectedScope} onChange={(event) => setSelectedScope(event.target.value)}>
            <option value="all">Todos os destinos</option>
            <optgroup label="Reflectores">
              {reflectorOptions.map((reflector) => <option value={`reflector:${reflector}`} key={'ref-' + reflector}>{reflector}</option>)}
            </optgroup>
            <optgroup label="Chamadas diretas">
              {callsignOptions.map((item) => <option value={`callsign:${item.callsign}`} key={'call-' + item.callsign}>{item.callsign}{item.name ? ` · ${item.name}` : ''}</option>)}
            </optgroup>
          </select>
        </label>
        <button type="button" className={selectedScope === 'all' ? 'active' : ''} onClick={() => setSelectedScope('all')}>Todos</button>
        <button
          type="button"
          disabled={!currentReflector}
          className={currentReflector && selectedScope === `reflector:${currentReflector}` ? 'active current' : 'current'}
          onClick={() => currentReflector && setSelectedScope(`reflector:${currentReflector}`)}
        >
          Reflector atual{currentReflector ? ` · ${currentReflector}` : ''}
        </button>
        <button
          type="button"
          disabled={!currentDirectCallsign}
          className={currentDirectCallsign && selectedScope === `callsign:${currentDirectCallsign}` ? 'active current direct' : 'current direct'}
          onClick={() => currentDirectCallsign && setSelectedScope(`callsign:${currentDirectCallsign}`)}
        >
          Chamada atual{currentDirectCallsign ? ` · ${currentDirectCallsign}` : ''}
        </button>
      </div>

      <div className="kpi-grid five stats-kpis">
        <Panel><div className="kpi-with-icon"><Radio /><div><small>Hoje{scopeCallsign ? ` · Direto ${scopeCallsign}` : scopeReflector ? ` · ${scopeReflector}` : ''}</small><strong>{statistics?.today.transmissions ?? '—'}</strong><span>QSOs</span></div><div><strong>{statistics ? formatDuration(statistics.today.airtime_seconds) : '—'}</strong><span>airtime total</span></div></div></Panel>
        <Panel><div className="kpi-with-icon"><CalendarDays /><div><small>Últimos 7 dias</small><strong>{statistics?.last_7d.transmissions ?? '—'}</strong><span>QSOs</span></div><div><strong>{statistics ? formatDuration(statistics.last_7d.airtime_seconds) : '—'}</strong><span>airtime total</span></div></div></Panel>
        <Panel><div className="kpi-with-icon"><CalendarDays /><div><small>Últimos 30 dias</small><strong>{statistics?.last_30d.transmissions ?? '—'}</strong><span>QSOs</span></div><div><strong>{statistics ? formatDuration(statistics.last_30d.airtime_seconds) : '—'}</strong><span>airtime total</span></div></div></Panel>
        <Panel><div className="kpi-with-icon"><BarChart3 /><div><small>Horário de pico</small><strong>{statistics?.peak_hour_today?.transmissions ?? 0}</strong><span>{statistics?.peak_hour_today ? `Hoje ${statistics.peak_hour_today.label}` : 'Sem tráfego hoje'}</span></div></div></Panel>
        <Panel><div className="kpi-with-icon"><Clock3 /><div><small>Duração média QSO</small><strong>{statistics ? `${statistics.average_qso_seconds_30d.toFixed(1)} s` : '—'}</strong><span>últimos 30 dias</span></div></div></Panel>
      </div>

      <div className="stats-period-grid-v4">
        <Panel title="▥ Últimos 7 Dias" className="stats-live-chart">
          {statistics ? (
            <>
              <PeriodBars values={statistics.daily_7d} />
              <div className="stats-total">
                <b>{statistics.last_7d.transmissions.toLocaleString('pt-BR')}</b><span>transmissões</span>
                <b>{formatDuration(statistics.last_7d.airtime_seconds)}</b><span>tempo de uso</span>
              </div>
            </>
          ) : <LoadingPanel text="Carregando últimos 7 dias…" />}
        </Panel>

        <Panel title="▥ Últimos 30 Dias" className="stats-live-chart">
          {statistics ? (
            <>
              <PeriodBars values={statistics.daily_30d} compact />
              <div className="stats-total">
                <b>{statistics.last_30d.transmissions.toLocaleString('pt-BR')}</b><span>transmissões</span>
                <b>{formatDuration(statistics.last_30d.airtime_seconds)}</b><span>tempo de uso</span>
              </div>
            </>
          ) : <LoadingPanel text="Carregando últimos 30 dias…" />}
        </Panel>

        <Panel title="Direção · Últimos 30 Dias" className="direction-panel">
          <div
            className={'donut ' + (directionTotal ? '' : 'empty')}
            style={directionTotal ? { background: `conic-gradient(#32a6ff 0 ${rfPercent}%, #2be49c ${rfPercent}% 100%)` } : undefined}
          >
            <div><strong>{directionTotal.toLocaleString('pt-BR')}</strong><span>QSOs</span></div>
          </div>
          <div className="direction-copy">
            <p><span className="blue-dot">●</span><b>RF → NET {rfPercent}%</b><small>{rfCount.toLocaleString('pt-BR')} QSOs</small></p>
            <p><span className="green-dot">●</span><b>NET → RF {netPercent}%</b><small>{netCount.toLocaleString('pt-BR')} QSOs</small></p>
          </div>
        </Panel>
      </div>

      <div className="routing-usage-grid">
        <Panel title="Uso por Reflector · Últimos 30 Dias · Visão Geral" className="reflector-usage-panel">
          <ReflectorUsageChart values={statistics?.reflector_usage_30d ?? []} selected={scopeReflector} />
          <small className="reflector-usage-note">Visão geral dos reflectores. Os demais indicadores obedecem ao filtro acima.</small>
        </Panel>
        <Panel title="Chamadas Diretas · Últimos 30 Dias · por indicativo" className="reflector-usage-panel callsign-usage-panel">
          <CallsignUsageChart values={statistics?.callsign_usage_30d ?? []} selected={scopeCallsign} />
          <small className="reflector-usage-note">Cada indicativo reúne os QSOs de Callsign Routing nos dois sentidos RF ↔ NET.</small>
        </Panel>
      </div>

      <div className="stats-network-row-v4">
        <Panel title="▥ Atividade · Últimas 24 Horas" className="stats-activity stats-live-chart">
          {statistics ? (
            <>
              <DualBars values={activityValues} labels={statistics.hourly_24h.map((row) => row.label)} />
              <div className="stats-hour-axis">{activityLabels.map((label, index) => <small key={index}>{label}</small>)}</div>
              <div className="legend"><span className="blue-dot">● RF → NET</span><span className="green-dot">● NET → RF</span></div>
            </>
          ) : <LoadingPanel text="Carregando atividade…" />}
        </Panel>

        {scopeCallsign
          ? <Panel title={`Callsign Routing · ${scopeCallsign}`} className="stats-live-chart direct-routing-note"><div><b>ircDDB / QuadNet</b><span>O histórico de rede do reflector não se aplica a uma chamada direta por indicativo.</span><small>As estatísticas acima contam somente os QSOs em que {scopeCallsign} foi o contato direto.</small></div></Panel>
          : <NetworkHistoryPanel history={networkHistory} />}
      </div>

      <div className="stats-bottom-grid">
        <Panel title="Top Stations · Últimos 30 Dias" className="stats-table-panel">
          <div className="stats-table-scroll">
            <table className="data-table compact">
              <thead><tr><th>#</th><th>CALLSIGN</th><th>NOME</th><th>LOCALIZAÇÃO</th><th>QSOs</th><th>AIRTIME</th></tr></thead>
              <tbody>
                {statistics?.top_stations.length ? statistics.top_stations.map((row, index) => (
                  <tr key={row.callsign}>
                    <td>{index + 1}</td><td><b>{row.callsign}</b></td><td>{row.name || '—'}</td><td>{row.location || '—'}</td>
                    <td>{row.transmissions.toLocaleString('pt-BR')}</td><td>{formatDuration(row.airtime_seconds)}</td>
                  </tr>
                )) : <tr><td colSpan={6} className="empty-cell">Nenhuma transmissão nos últimos 30 dias</td></tr>}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Last Heard · Estendido" className="stats-table-panel">
          <div className="stats-table-scroll">
            <table className="data-table compact">
              <thead><tr><th>HORÁRIO</th><th>DIREÇÃO</th><th>CALLSIGN</th><th>NOME</th><th>LOCALIZAÇÃO</th><th>ROTA</th><th>DURAÇÃO</th><th>BER</th><th>LOSS</th></tr></thead>
              <tbody>
                {transmissions.length ? transmissions.map((row) => (
                  <tr key={row.id}>
                    <td>{formatClock(row.started_at)}</td>
                    <td><span className={'direction-pill ' + (row.direction === 'RF_TO_NET' ? 'rf-net' : 'net-rf')}>{directionLabel(row.direction)}</span></td>
                    <td><b>{row.src_callsign || '—'}</b></td><td>{row.name || '—'}</td><td>{row.location || '—'}</td><td>{row.route_type === 'callsign' ? <span className="route-pill direct">Direto · {row.contact_callsign || '—'}</span> : <span className="route-pill reflector">{row.reflector || '—'}</span>}</td><td>{formatDuration(row.duration_seconds)}</td>
                    <td><TransmissionQuality kind="ber" value={row.ber_percent} applicable={row.direction === 'RF_TO_NET'} /></td>
                    <td><TransmissionQuality kind="loss" value={row.packet_loss_percent} applicable={row.direction === 'NET_TO_RF'} /></td>
                  </tr>
                )) : <tr><td colSpan={9} className="empty-cell">Nenhuma transmissão registrada</td></tr>}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="stats-side">
          <Panel title="Resumo da Base CSV">
            <div className="info-list small stats-info-list">
              <p><span>Registros carregados</span><b>{settings?.users.count.toLocaleString('pt-BR') ?? '—'}</b></p>
              <p><span>Última importação</span><b>{formatDateTime(settings?.users.imported_at)}</b></p>
              <p><span>Indicativos ativos encontrados</span><b>{directory ? `${directory.matched_callsigns.toLocaleString('pt-BR')} / ${directory.active_callsigns.toLocaleString('pt-BR')} (${directory.matched_callsigns_percent.toFixed(1)}%)` : '—'}</b></p>
              <p><span>Transmissões enriquecidas</span><b>{directory ? `${directory.enriched_transmissions.toLocaleString('pt-BR')} / ${directory.transmissions_with_callsign.toLocaleString('pt-BR')} (${directory.enriched_transmissions_percent.toFixed(1)}%)` : '—'}</b></p>
            </div>
          </Panel>

          <Panel title="Resumo dos Hosts" className="stats-hosts-panel">
            <table className="data-table compact">
              <thead><tr><th>HOST</th><th>STATUS</th><th>ENTRADAS</th><th>ATUALIZAÇÃO</th></tr></thead>
              <tbody>
                {hosts.length ? hosts.map((host) => (
                  <tr key={host.protocol}>
                    <td>{host.protocol}</td>
                    <td className={host.available ? 'good-text' : 'warn-text'}>{host.available ? '● Online' : '● Missing'}</td>
                    <td>{host.count.toLocaleString('pt-BR')}</td>
                    <td>{formatDateTime(host.updated_at)}</td>
                  </tr>
                )) : <tr><td colSpan={4} className="empty-cell">Carregando host files…</td></tr>}
              </tbody>
            </table>
          </Panel>
        </div>
      </div>

      <div className="stats-footer-meta">
        <span>Atualização automática: 10 s</span>
        <span>Escopo: {scopeLabel}</span>
        <span>Rede: {scopeCallsign ? 'chamada direta via ircDDB / QuadNet' : 'histórico do reflector selecionado quando disponível · ICMP não é necessário'}</span>
        <span>Timezone da API: {statistics?.timezone || '—'}</span>
      </div>
    </div>
  )
}

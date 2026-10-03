type DailyValue = {
  date: string
  transmissions: number
  airtime_seconds: number
  rf_to_net?: number
  net_to_rf?: number
}

type Props = { values: DailyValue[]; compact?: boolean }

function label(date: string): string {
  const parts = date.split('-')
  return parts.length === 3 ? `${parts[2]}/${parts[1]}` : date
}

function fullLabel(date: string): string {
  const parts = date.split('-')
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : date
}

function formatDuration(value: number): string {
  const seconds = Math.max(0, Math.round(Number(value || 0)))
  if (seconds < 60) return `${seconds}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  if (hours > 0) return rest ? `${hours}h ${minutes}m ${rest}s` : `${hours}h ${minutes}m`
  return `${minutes}m ${rest}s`
}

export default function PeriodBars({ values, compact = false }: Props) {
  const max = Math.max(...values.flatMap((value) => [
    value.rf_to_net ?? 0,
    value.net_to_rf ?? 0,
    value.transmissions ?? 0,
  ]), 0)

  if (max <= 0) return <div className="period-bars-empty">Sem dados suficientes</div>

  const step = compact ? Math.max(1, Math.ceil(values.length / 6)) : 1

  return (
    <div className={'period-bars-v3 ' + (compact ? 'compact' : '')}>
      {values.map((value, index) => {
        const rf = value.rf_to_net ?? value.transmissions
        const net = value.net_to_rf ?? 0
        const showLabel = !compact || index === 0 || index === values.length - 1 || index % step === 0
        const hasDirections = value.rf_to_net !== undefined && value.net_to_rf !== undefined
        const accessible = hasDirections
          ? `${fullLabel(value.date)}. Total: ${value.transmissions} transmissões. RF para NET: ${rf}. NET para RF: ${net}. Airtime: ${formatDuration(value.airtime_seconds)}.`
          : `${fullLabel(value.date)}. Total: ${value.transmissions} transmissões. Airtime: ${formatDuration(value.airtime_seconds)}.`

        return (
          <div
            className="period-day chart-hover-item"
            key={value.date}
            tabIndex={0}
            aria-label={accessible}
          >
            <div className="period-day-bars">
              <i className="rf" style={{ height: Math.max(2, (rf / max) * 100) + '%' }} />
              {value.net_to_rf !== undefined && <i className="net" style={{ height: Math.max(2, (net / max) * 100) + '%' }} />}
            </div>
            <small>{showLabel ? label(value.date) : ''}</small>
            <div className="chart-tooltip" role="tooltip">
              <b>{fullLabel(value.date)}</b>
              <span>Transmissões <strong>{value.transmissions.toLocaleString('pt-BR')}</strong></span>
              {hasDirections ? <span>RF → NET <strong>{rf.toLocaleString('pt-BR')}</strong></span> : null}
              {hasDirections ? <span>NET → RF <strong>{net.toLocaleString('pt-BR')}</strong></span> : null}
              <span>Airtime <strong>{formatDuration(value.airtime_seconds)}</strong></span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

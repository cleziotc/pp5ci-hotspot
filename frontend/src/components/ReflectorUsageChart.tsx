import type { Statistics } from '../api/client'

type UsageRow = Statistics['reflector_usage_30d'][number]

function formatDuration(value: number): string {
  const seconds = Math.max(0, Math.round(value || 0))
  if (seconds < 60) return `${seconds}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

export default function ReflectorUsageChart({
  values,
  selected,
}: {
  values: UsageRow[]
  selected: string | null
}) {
  const rows = values.slice(0, 10)
  const max = Math.max(1, ...rows.map((row) => row.airtime_seconds))

  if (!rows.length) {
    return <div className="reflector-usage-empty">Ainda não há tráfego por reflector nos últimos 30 dias.</div>
  }

  return (
    <div className="reflector-usage-chart">
      {rows.map((row) => {
        const width = Math.max(2, (row.airtime_seconds / max) * 100)
        const active = selected === row.reflector
        return (
          <div className={'reflector-usage-row ' + (active ? 'selected' : '')} key={row.reflector}>
            <b>{row.reflector}</b>
            <div className="reflector-usage-track"><i style={{ width: `${width}%` }} /></div>
            <span>{row.transmissions.toLocaleString('pt-BR')} QSOs</span>
            <strong>{formatDuration(row.airtime_seconds)}</strong>
          </div>
        )
      })}
    </div>
  )
}

import { Globe2, Waves } from 'lucide-react'
import type { NetworkHistory, NetworkHistoryPoint } from '../api/network'

type Props = {
  history: NetworkHistory | null
}

function fmt(value: number | null | undefined, suffix = 'ms'): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toFixed(value < 10 ? 1 : 0)} ${suffix}`
}

function points(values: NetworkHistoryPoint[], key: 'latency_ms' | 'jitter_ms', width: number, height: number, max: number): string {
  if (!values.length) return ''
  return values.flatMap((row, index) => {
    const value = row[key]
    if (value === null || value === undefined) return []
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width
    const y = height - Math.min(height, Math.max(0, value / max * height))
    return [`${x.toFixed(1)},${y.toFixed(1)}`]
  }).join(' ')
}

export default function NetworkHistoryPanel({ history }: Props) {
  const values = history?.reflector.series ?? []
  const all = values.flatMap((row) => [row.latency_ms, row.jitter_ms]).filter((value): value is number => typeof value === 'number')
  const max = Math.max(100, ...all, 1)
  const latency = points(values, 'latency_ms', 620, 150, max)
  const jitter = points(values, 'jitter_ms', 620, 150, max)

  return (
    <section className="panel network-history-panel">
      <div className="network-history-head">
        <div>
          <h2><Waves size={17} /> Latência e Jitter do Reflector · Últimas 24h</h2>
          <small>{history?.reflector.name || 'Sem reflector identificado'} · TCP, sem depender de ping/ICMP</small>
        </div>
        <div className="network-history-legend">
          <span className="latency">● Latência</span>
          <span className="jitter">● Jitter</span>
        </div>
      </div>

      {values.length ? (
        <div className="network-history-plot">
          <svg viewBox="0 0 620 150" preserveAspectRatio="none" aria-hidden="true">
            <line x1="0" y1="37.5" x2="620" y2="37.5" />
            <line x1="0" y1="75" x2="620" y2="75" />
            <line x1="0" y1="112.5" x2="620" y2="112.5" />
            <polyline className="latency-line" points={latency} />
            <polyline className="jitter-line" points={jitter} />
          </svg>
          <div className="network-history-axis"><span>24h atrás</span><span>12h</span><span>agora</span></div>
        </div>
      ) : <div className="chart-empty">Coletando histórico de rede…</div>}

      <div className="network-history-summary">
        <div><Waves size={16} /><span>Reflector</span><b>{fmt(history?.reflector.latency_ms)}</b><small>jitter {fmt(history?.reflector.jitter_ms)}</small></div>
        <div><Globe2 size={16} /><span>Internet</span><b>{fmt(history?.internet.latency_ms)}</b><small>jitter {fmt(history?.internet.jitter_ms)}</small></div>
        <div><span>Perda reflector</span><b>{fmt(history?.reflector.loss_percent, '%')}</b><small>janela de 24 h</small></div>
        <div><span>Perda Internet</span><b>{fmt(history?.internet.loss_percent, '%')}</b><small>baseline</small></div>
      </div>
    </section>
  )
}

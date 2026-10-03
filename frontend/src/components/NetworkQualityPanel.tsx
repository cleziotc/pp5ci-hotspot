import { useState } from 'react'
import { Activity, Info, ShieldCheck, Waves, X } from 'lucide-react'
import type { NetworkQuality, NetworkSample } from '../api/network'

type Props = {
  quality: NetworkQuality | null
}

type Tone = 'good' | 'degraded' | 'poor' | 'unavailable'

function metric(value: number | null | undefined, suffix: string, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${value.toFixed(digits)} ${suffix}`
}

function stateLabel(state: string | undefined): string {
  if (state === 'good') return 'BOA'
  if (state === 'degraded') return 'ATENÇÃO'
  if (state === 'poor') return 'RUIM'
  return 'MEDINDO'
}

function latencyTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'unavailable'
  if (value <= 100) return 'good'
  if (value <= 260) return 'degraded'
  return 'poor'
}

function latencyGradient(rtt: number): string {
  const safe = Math.max(1, rtt)

  if (safe <= 100) {
    return 'linear-gradient(to top, #20c982 0%, #35eaa0 58%, #62f0b8 100%)'
  }

  const greenAt = Math.min(100, (100 / safe) * 100)

  if (safe <= 260) {
    const transitionStart = Math.max(0, greenAt - 7)
    const transitionEnd = Math.min(100, greenAt + 10)
    return `linear-gradient(to top,
      #20c982 0%,
      #35eaa0 ${transitionStart.toFixed(2)}%,
      #a9e675 ${transitionEnd.toFixed(2)}%,
      #ffd166 100%)`
  }

  const yellowAt = Math.min(100, (260 / safe) * 100)
  const greenTransitionStart = Math.max(0, greenAt - 6)
  const greenTransitionEnd = Math.min(yellowAt, greenAt + 8)
  const redTransitionStart = Math.max(greenTransitionEnd, yellowAt - 7)
  const redTransitionEnd = Math.min(100, yellowAt + 8)

  return `linear-gradient(to top,
    #20c982 0%,
    #35eaa0 ${greenTransitionStart.toFixed(2)}%,
    #b9e36a ${greenTransitionEnd.toFixed(2)}%,
    #ffd166 ${redTransitionStart.toFixed(2)}%,
    #ff9b50 ${redTransitionEnd.toFixed(2)}%,
    #ff5c6c 100%)`
}

function latencyValues(samples: NetworkSample[]): number[] {
  return samples.flatMap((sample) => sample.success && typeof sample.rtt_ms === 'number' ? [sample.rtt_ms] : [])
}

function jitterValues(samples: NetworkSample[]): number[] {
  const valid = latencyValues(samples)
  return valid.slice(1).map((value, index) => Math.abs(value - valid[index]))
}

function lossValues(samples: NetworkSample[]): number[] {
  if (!samples.length) return []
  return samples.map((sample) => sample.success ? 0 : 100)
}

function Sparkline({
  values,
  variant,
  tone,
}: {
  values: number[]
  variant: 'latency' | 'jitter' | 'loss'
  tone?: Tone
}) {
  if (!values.length) return <div className="network-mini-empty">—</div>

  const width = 120
  const height = 28
  const observedMax = Math.max(...values, 0)
  const scaleMax = variant === 'latency'
    ? Math.max(100, observedMax * 1.65)
    : variant === 'jitter'
      ? Math.max(20, observedMax * 2.0)
      : Math.max(5, observedMax * 1.25)
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? width / 2 : (index / (values.length - 1)) * width
    const y = height - 3 - (Math.max(0, value) / scaleMax) * (height - 6)
    return `${x.toFixed(1)},${Math.max(3, Math.min(height - 3, y)).toFixed(1)}`
  }).join(' ')

  return (
    <svg className={['network-mini-spark', variant, tone || ''].filter(Boolean).join(' ')} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <line x1="0" y1={height - 2} x2={width} y2={height - 2} />
      <polyline points={points} />
    </svg>
  )
}

function assessment(
  latency: number | null | undefined,
  jitter: number | null | undefined,
  loss: number | null | undefined,
  state: string | undefined,
  direct: boolean,
): string {
  if (latency === null || latency === undefined) return 'Aguardando amostras suficientes para classificar a rota.'

  if (state === 'poor' && latency <= 260) {
    if ((loss ?? 0) >= 5) return 'RUIM · a perda de pacotes está alta mesmo com a latência dentro da faixa aceitável.'
    if ((jitter ?? 0) >= 100) return 'RUIM · o jitter está muito alto e pode causar áudio irregular.'
  }

  if (latency <= 100) {
    if (state === 'degraded') return 'ATENÇÃO · latência boa, mas jitter ou perda estão acima do ideal.'
    return direct
      ? 'BOA · rota rápida até o gateway D-STAR remoto, com RTT de até 100 ms.'
      : 'BOA · rota rápida até o reflector, com RTT de até 100 ms.'
  }
  if (latency <= 260) {
    return direct
      ? 'ATENÇÃO · RTT entre 101 e 260 ms. O gateway remoto do indicativo pode estar em outro país; observe também jitter e perda.'
      : 'ATENÇÃO · RTT entre 101 e 260 ms. O reflector pode estar hospedado em outro país; observe também jitter e perda.'
  }
  return direct
    ? 'RUIM · RTT acima de 260 ms até o gateway remoto. Há maior chance de atraso perceptível na chamada direta.'
    : 'RUIM · RTT acima de 260 ms. Há latência elevada e maior chance de atraso perceptível no uso do reflector.'
}

export default function NetworkQualityPanel({ quality }: Props) {
  const [infoOpen, setInfoOpen] = useState(false)
  const target = quality?.active_target || quality?.reflector
  const direct = target?.target_type === 'callsign'
  const samples = target?.samples ?? []
  const successful = latencyValues(samples)
  const observedMax = Math.max(...successful, 0)
  const chartScale = Math.max(100, observedMax * 1.18)
  const latency = latencyValues(samples)
  const jitter = jitterValues(samples)
  const loss = lossValues(samples)
  const latencyClass = latencyTone(target?.latency_ms)
  const slotCount = Math.max(1, Math.round((quality?.window_seconds ?? 60) / (quality?.probe_interval_seconds ?? 3)))
  const visibleSamples = samples.slice(-slotCount)
  const timelineSlots: Array<NetworkSample | null> = [
    ...Array.from({ length: Math.max(0, slotCount - visibleSamples.length) }, () => null),
    ...visibleSamples,
  ]
  const description = assessment(
    target?.latency_ms,
    target?.jitter_ms,
    target?.loss_percent,
    target?.state,
    direct,
  )

  return (
    <section className="panel network-quality-panel">
      <div className="network-quality-head">
        <div className="network-title-wrap">
          <h2>
            <Waves size={17} />
            {direct ? 'Qualidade da Rede (Chamada Direta)' : 'Qualidade da Rede (Reflector)'}
            <button
              type="button"
              className="network-info-button"
              aria-label="Como interpretar a qualidade da rede"
              aria-expanded={infoOpen}
              onClick={() => setInfoOpen((open) => !open)}
            >
              <Info size={14} />
            </button>
          </h2>
          <small>
            {direct
              ? `${target?.callsign || target?.name || 'Chamada direta'} · ${target?.ip || target?.host || 'aguardando IP ircDDB'}`
              : `${target?.name || 'Sem reflector conectado'}${target?.ip ? ` · ${target.ip}` : ''}`}
          </small>
          {infoOpen ? (
            <div className="network-info-popover" role="dialog" aria-label="Como interpretar a qualidade da rede">
              <div className="network-info-popover-head">
                <b>Como interpretar</b>
                <button type="button" aria-label="Fechar" onClick={() => setInfoOpen(false)}><X size={13} /></button>
              </div>
              <p><i className="good" /> <b>0–100 ms · BOA</b><span>Rota rápida até o destino de rede atualmente medido.</span></p>
              <p><i className="degraded" /> <b>101–260 ms · ATENÇÃO</b><span>Pode ser normal quando o reflector ou gateway remoto está hospedado em outro país.</span></p>
              <p><i className="poor" /> <b>&gt;260 ms · RUIM</b><span>Latência alta; pode haver atraso perceptível.</span></p>
              <small>{direct
                ? 'Em Callsign Routing, o IP mostrado é o gateway D-STAR remoto resolvido pelo ircDDB para o indicativo — não o IP do rádio da pessoa. O Polar mantém esse alvo por 60 s após a chamada direta, mas volta imediatamente ao reflector se houver tráfego de reflector. A sonda é TCP e não depende de ICMP/ping.'
                : 'As barras usam gradiente real por faixa. A medição usa sonda TCP e não depende de ICMP/ping.'}</small>
            </div>
          ) : null}
        </div>
        <span className={'network-source ' + (target?.state || 'unavailable')}>
          <ShieldCheck size={13} /> {direct ? 'Gateway G2 · TCP · sem ICMP' : 'Sonda TCP · sem ICMP'}
        </span>
      </div>

      <div className="network-metric-grid">
        <div className={'latency-card ' + latencyClass}>
          <Activity size={18} />
          <strong>{metric(target?.latency_ms, 'ms')}</strong>
          <small>Latência</small>
          <Sparkline values={latency} variant="latency" tone={latencyClass} />
        </div>
        <div>
          <Waves size={18} />
          <strong>{metric(target?.jitter_ms, 'ms', 1)}</strong>
          <small>Jitter RTT</small>
          <Sparkline values={jitter} variant="jitter" />
        </div>
        <div>
          <ShieldCheck size={18} />
          <strong>{metric(target?.loss_percent, '%', 1)}</strong>
          <small>Perda</small>
          <Sparkline values={loss} variant="loss" />
        </div>
      </div>

      <div className={'network-assessment ' + (target?.state || 'unavailable')}>
        <b>{stateLabel(target?.state)}</b>
        <span>{description}</span>
      </div>

      <div className="network-bars" aria-label={direct ? 'Latência das últimas sondas ao gateway D-STAR remoto' : 'Latência das últimas sondas ao reflector'}>
        {samples.length ? timelineSlots.map((sample, index) => {
          if (!sample) return <i key={'empty-' + index} className="empty-slot" style={{ height: '0%' }} />
          const rtt = sample.success && typeof sample.rtt_ms === 'number' ? sample.rtt_ms : null
          const height = rtt === null ? 92 : Math.max(9, Math.min(86, rtt * 100 / chartScale))
          const cls = !sample.success
            ? 'lost'
            : rtt !== null && rtt > 260
              ? 'poor'
              : rtt !== null && rtt > 100
                ? 'degraded'
                : 'good'
          return (
            <i
              key={sample.sampled_at + index}
              className={cls}
              style={{
                height: `${height}%`,
                background: rtt !== null ? latencyGradient(rtt) : undefined,
              }}
              title={rtt !== null ? `${rtt.toFixed(1)} ms` : 'Sonda sem resposta'}
            />
          )
        }) : <span>Coletando amostras de rede…</span>}
      </div>

      <div className="network-quality-foot">
        <span>{direct ? `Destino direto · retenção ${quality?.direct_hold_seconds ?? 60}s` : `Últimos ${quality?.window_seconds ?? 60} segundos`}</span>
        <b className={'network-state ' + (target?.state || 'unavailable')}>{stateLabel(target?.state)}</b>
        <span>Máx: {metric(target?.max_rtt_ms, 'ms')}</span>
      </div>
    </section>
  )
}

type Props = {
  kind: 'ber' | 'loss'
  value: number | null | undefined
  applicable: boolean
}

function tone(kind: 'ber' | 'loss', value: number): 'good' | 'warn' | 'bad' {
  if (kind === 'ber') {
    if (value <= 1.0) return 'good'
    if (value <= 2.5) return 'warn'
    return 'bad'
  }
  if (value <= 0.5) return 'good'
  if (value <= 3.0) return 'warn'
  return 'bad'
}

export default function TransmissionQuality({ kind, value, applicable }: Props) {
  if (!applicable || value === null || value === undefined || !Number.isFinite(value)) {
    return <span className="quality-pill unavailable">—</span>
  }
  const cls = tone(kind, value)
  return <span className={'quality-pill ' + cls} title={kind === 'ber' ? 'BER do enlace RF → hotspot' : 'Perda de pacotes do stream NET → RF'}>{value.toFixed(1)}%</span>
}

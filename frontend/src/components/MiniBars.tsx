type Props = { values: number[]; variant?: 'blue' | 'green' }

export default function MiniBars({ values, variant = 'blue' }: Props) {
  const max = Math.max(...values, 0)
  if (max <= 0) return <div className="chart-empty">Sem dados suficientes</div>

  return (
    <div className={'mini-bars ' + variant}>
      {values.map((value, index) => <i key={index} style={{ height: Math.max(2, (value / max) * 100) + '%' }} />)}
    </div>
  )
}

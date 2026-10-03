type Props = {
  values: Array<{ a: number; b: number }>
  labels?: string[]
}

function tooltipLabel(label: string | undefined, index: number): string {
  return label || `Período ${index + 1}`
}

export default function DualBars({ values, labels = [] }: Props) {
  const max = Math.max(...values.flatMap((v) => [v.a, v.b]), 0)
  if (max <= 0) return <div className="chart-empty">Sem dados suficientes</div>

  return (
    <div className="dual-bars">
      {values.map((value, index) => {
        const total = value.a + value.b
        const accessible = `${tooltipLabel(labels[index], index)}. RF para NET: ${value.a}. NET para RF: ${value.b}. Total: ${total}.`

        return (
          <div
            className="chart-hover-item"
            key={index}
            tabIndex={0}
            aria-label={accessible}
          >
            <i className="a" style={{ height: Math.max(2, (value.a / max) * 100) + '%' }} />
            <i className="b" style={{ height: Math.max(2, (value.b / max) * 100) + '%' }} />
            <div className="chart-tooltip" role="tooltip">
              <b>{tooltipLabel(labels[index], index)}</b>
              <span>RF → NET <strong>{value.a.toLocaleString('pt-BR')}</strong></span>
              <span>NET → RF <strong>{value.b.toLocaleString('pt-BR')}</strong></span>
              <span>Total <strong>{total.toLocaleString('pt-BR')}</strong></span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

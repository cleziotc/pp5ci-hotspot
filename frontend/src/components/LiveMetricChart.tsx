type Props = {
  title: string
  subtitle: string
  value: number | null
  unit: string
  samples: number[]
  variant: 'green' | 'blue'
  live: boolean
  emptyText: string
  minFloor?: number
  fixedRange?: [number, number]
}

function stats(values: number[]) {
  if (!values.length) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length
  return { min, max, avg }
}

function fmt(value: number, unit: string): string {
  if (unit === 'dBm') return `${Math.round(value)}`
  return value.toFixed(1)
}

export default function LiveMetricChart({
  title,
  subtitle,
  value,
  unit,
  samples,
  variant,
  live,
  emptyText,
  minFloor = 0,
  fixedRange,
}: Props) {
  const summary = stats(samples)
  const observedMin = samples.length ? Math.min(...samples) : minFloor
  const observedMax = samples.length ? Math.max(...samples) : minFloor + 1
  const yMin = fixedRange ? fixedRange[0] : Math.min(minFloor, observedMin)
  const yMaxRaw = fixedRange ? fixedRange[1] : Math.max(5, observedMax * 1.25, yMin + 1)
  const yMax = yMaxRaw === yMin ? yMin + 1 : yMaxRaw
  const width = 300
  const height = 96
  const padX = 8
  const padY = 8
  const range = yMax - yMin

  const pointList = samples.map((sample, index) => {
    const x = samples.length <= 1 ? width / 2 : padX + (index / (samples.length - 1)) * (width - padX * 2)
    const y = padY + (1 - (sample - yMin) / range) * (height - padY * 2)
    return { x, y: Math.max(padY, Math.min(height - padY, y)), value: sample }
  })
  const lastPoint = pointList.at(-1)

  return (
    <section className={'panel live-metric-card live-metric-card-v6 ' + variant}>
      <div className="live-metric-head">
        <div>
          <h2>{title}</h2>
          <small>{subtitle}</small>
        </div>
        <span className={live ? 'metric-live on' : 'metric-live'}>{live ? '● Instantâneo' : '● Última RF'}</span>
      </div>

      <div className="live-metric-body-v6">
        <div className="live-metric-graph-v6">
          {samples.length ? (
            <div className="live-metric-plot">
              <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
                {[24, 48, 72].map((y) => <line key={'h' + y} x1="0" y1={y} x2={width} y2={y} className="grid-line" />)}
                {[50, 100, 150, 200, 250].map((x) => <line key={'v' + x} x1={x} y1="0" x2={x} y2={height} className="grid-line vertical" />)}
                {pointList.slice(1).map((point, index) => {
                  const previous = pointList[index]
                  const average = (point.value + previous.value) / 2
                  const warn = variant === 'green' && average >= 1.0
                  return (
                    <line
                      key={index}
                      x1={previous.x}
                      y1={previous.y}
                      x2={point.x}
                      y2={point.y}
                      className={warn ? 'metric-segment warn' : 'metric-segment'}
                    />
                  )
                })}
                {lastPoint ? <circle cx={lastPoint.x} cy={lastPoint.y} r="2.4" className="metric-last-point" /> : null}
              </svg>
            </div>
          ) : <div className="live-metric-empty">{emptyText}</div>}
        </div>

        <div className="live-metric-side-v6">
          <div className="live-metric-current">
            <strong>{value === null || value === undefined ? '—' : fmt(value, unit)}<small>{value === null || value === undefined ? '' : unit}</small></strong>
            <span>Atual</span>
          </div>
          <div className="live-metric-stats-v6">
            <span><small>Mín</small><b>{summary ? fmt(summary.min, unit) : '—'}</b></span>
            <span><small>Máx</small><b>{summary ? fmt(summary.max, unit) : '—'}</b></span>
            <span><small>Média</small><b>{summary ? fmt(summary.avg, unit) : '—'}</b></span>
          </div>
        </div>
      </div>
    </section>
  )
}

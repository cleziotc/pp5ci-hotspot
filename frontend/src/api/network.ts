export type NetworkSample = {
  sampled_at: string
  success: boolean
  rtt_ms: number | null
}

export type NetworkSummary = {
  name: string | null
  target_type?: 'reflector' | 'callsign' | string
  callsign?: string | null
  latency_ms: number | null
  jitter_ms: number | null
  loss_percent: number | null
  max_rtt_ms: number | null
  sample_count: number
  successful_samples: number
  state: 'good' | 'degraded' | 'poor' | 'unavailable' | string
  host?: string | null
  ip?: string | null
  port?: number | null
  last_sample_at?: string | null
  last_sample_age_seconds?: number | null
  fresh?: boolean
  samples?: NetworkSample[]
}

export type NetworkQuality = {
  generated_at: string
  window_seconds: number
  probe_method: string
  icmp_required: boolean
  probe_interval_seconds?: number
  direct_hold_seconds?: number
  active_target: NetworkSummary & { samples: NetworkSample[] }
  reflector: NetworkSummary & { samples: NetworkSample[] }
  direct: NetworkSummary & { samples: NetworkSample[] }
  internet: NetworkSummary & { samples: NetworkSample[] }
  dstar: {
    protocol: string | null
    udp_port: number | null
    last_network_loss: {
      loss_percent: number
      ended_at: string | null
      reflector: string | null
    } | null
  }
}

export type NetworkHistoryPoint = {
  sampled_at: string
  latency_ms: number | null
  jitter_ms: number | null
  loss_percent: number | null
  sample_count: number
}

export type NetworkHistory = {
  generated_at: string
  hours: number
  bucket_minutes: number
  probe_method: string
  icmp_required: boolean
  reflector: NetworkSummary & { series: NetworkHistoryPoint[] }
  internet: NetworkSummary & { series: NetworkHistoryPoint[] }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export const getNetworkQuality = () => getJson<NetworkQuality>('/api/v1/network')
export const getNetworkHistory = (hours = 24, reflector?: string | null) => {
  const params = new URLSearchParams({ hours: String(hours) })
  if (reflector) params.set('reflector', reflector)
  return getJson<NetworkHistory>(`/api/v1/network/history?${params.toString()}`)
}

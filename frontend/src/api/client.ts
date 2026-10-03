export type ServiceState = { active: string; sub: string }

export type HotspotStatus = {
  version: string
  updated_at: string
  hotspot: {
    callsign: string
    name: string
    module: string
    rx_frequency_hz: number
    tx_frequency_hz: number
    mode: string
  }
  modem: {
    online: boolean
    device: string
    resolved_device: string
    serial_present: boolean
    baud: number
    rf_level_percent: number
    rx_level_percent: number
    dstar_tx_level_percent: number
    firmware: string | null
  }
  services: {
    mmdvmhost: ServiceState
    dstargateway: ServiceState
    mosquitto: ServiceState
    collector: ServiceState
  }
  network: {
    gateway_address: string
    gateway_port: number
    local_address: string
    local_port: number
  }
  mqtt: {
    connected: boolean
    topic: string
    last_event_at: string | null
  }
  traffic: {
    state: string
    direction: string | null
    source: string | null
    started_at: string | null
    station: string | null
    name?: string | null
    location?: string | null
    src_ext: string | null
    destination: string | null
    reflector: string | null
    route_type?: 'reflector' | 'callsign' | 'local' | null
    contact_callsign?: string | null
    duration_seconds: number
    ber_percent: number | null
    rssi_dbm: number | null
    slow_text: string | null
    updated_at?: string
    ber_updated_at?: string | null
    rssi_updated_at?: string | null
  }
  link: {
    reflector: string | null
    state: string
    callsign_routing?: {
      enabled: boolean
      hostname: string
      username: string
    }
  }
  system: {
    load: { '1m': number | null; '5m': number | null; '15m': number | null }
    memory_percent: number | null
    uptime_seconds: number | null
  }
}

export type Transmission = {
  id: number
  started_at: string
  ended_at: string
  direction: string
  source: string
  src_callsign: string | null
  src_ext: string | null
  dst_callsign: string | null
  reflector: string | null
  route_type: 'reflector' | 'callsign' | 'local' | null
  contact_callsign: string | null
  duration_seconds: number | null
  ber_percent: number | null
  rssi_min_dbm: number | null
  rssi_max_dbm: number | null
  rssi_ave_dbm: number | null
  packet_loss_percent: number | null
  slow_text: string | null
  name?: string | null
  location?: string | null
}

export type PeriodStat = {
  transmissions: number
  airtime_seconds: number
  rf_to_net_seconds: number
  net_to_rf_seconds: number
}

export type Statistics = {
  timezone: string
  scope: {
    type: 'all' | 'reflector' | 'callsign'
    reflector: string | null
    callsign: string | null
    label: string
  }
  available_reflectors: string[]
  available_callsigns: string[]
  reflector_usage_30d: Array<{
    reflector: string
    transmissions: number
    airtime_seconds: number
    rf_to_net_seconds: number
    net_to_rf_seconds: number
  }>
  callsign_usage_30d: Array<{
    callsign: string
    name: string | null
    location: string | null
    transmissions: number
    airtime_seconds: number
    rf_to_net_seconds: number
    net_to_rf_seconds: number
  }>
  today: PeriodStat
  last_24h: PeriodStat
  last_7d: PeriodStat
  last_30d: PeriodStat
  hourly_24h: Array<{ label: string; rf_to_net: number; net_to_rf: number; total: number }>
  daily_7d: Array<{ date: string; transmissions: number; airtime_seconds: number; rf_to_net: number; net_to_rf: number }>
  daily_30d: Array<{ date: string; transmissions: number; airtime_seconds: number; rf_to_net: number; net_to_rf: number }>
  direction_30d: { rf_to_net: number; net_to_rf: number }
  peak_hour_today: { hour: string; label: string; transmissions: number } | null
  average_qso_seconds_30d: number
  directory_coverage_30d: {
    active_callsigns: number
    matched_callsigns: number
    matched_callsigns_percent: number
    transmissions_with_callsign: number
    enriched_transmissions: number
    enriched_transmissions_percent: number
  }
  top_stations: Array<{
    callsign: string
    name: string | null
    location: string | null
    transmissions: number
    airtime_seconds: number
  }>
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export const getStatus = () => getJson<HotspotStatus>('/api/v1/status')
export const getTransmissions = (limit = 20, reflector?: string | null, callsign?: string | null) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (reflector) params.set('reflector', reflector)
  if (callsign) params.set('callsign', callsign)
  return getJson<{ items: Transmission[]; limit: number; reflector?: string | null; callsign?: string | null }>(`/api/v1/transmissions?${params.toString()}`)
}
export const getStatistics = (reflector?: string | null, callsign?: string | null) => {
  const params = new URLSearchParams()
  if (reflector) params.set('reflector', reflector)
  if (callsign) params.set('callsign', callsign)
  const suffix = params.toString()
  return getJson<Statistics>(`/api/v1/statistics${suffix ? `?${suffix}` : ''}`)
}


export type DiagnosticService = {
  label: string
  unit: string
  active: string
  sub: string
  pid: number
  uptime_seconds: number | null
  since: string | null
}

export type DiagnosticsState = {
  generated_at: string
  services: DiagnosticService[]
  timer: { active: string; sub: string; schedule: string; last_trigger: string | null; next_run: string | null }
  serial: {
    configured_device: string
    device: string
    present: boolean
    usb_chip: string
    vendor_id: string | null
    product_id: string | null
    baud: number
    format: string
    firmware: string | null
  }
  ports: Array<{ port: number; protocol: string; address: string; listening: boolean }>
  metrics: {
    ber_percent: number | null
    rssi_dbm: number | null
    last_activity_seconds: number | null
    last_transmission_at: string | null
    rf_level_percent: number
    rx_level_percent: number
    dstar_tx_level_percent: number
    traffic_state: string | null
    total_transmissions: number
  }
  system: {
    disk: { total_bytes: number; used_bytes: number; free_bytes: number; used_percent: number }
    load: { load_1m: number | null; load_5m: number | null; load_15m: number | null; cpu_count: number; load_percent: number | null }
  }
  directory: { count: number; imported_at: string | null; source_file: string | null; columns: string[] }
  checks: Array<{ name: string; ok: boolean; detail: string }>
  logs: string[]
}

export const getDiagnostics = () => getJson<DiagnosticsState>('/api/v1/diagnostics')
export const runSerialCheck = () => requestJson<{ ok: boolean; message: string; serial: DiagnosticsState['serial'] }>('/api/v1/diagnostics/serial-check', { method: 'POST', body: '{}' })
export const runDstarCheck = () => requestJson<{ ok: boolean; message: string }>('/api/v1/diagnostics/dstar-check', { method: 'POST', body: '{}' })
export const restartDiagnosticService = (target: 'mmdvmhost' | 'dstargateway', token: string) =>
  requestJson<{ ok: boolean; service: string; active: string; sub: string; pid: number }>(
    `/api/v1/diagnostics/restart/${target}`,
    { method: 'POST', body: '{}' },
    token,
  )

export type HostFileStatus = {
  protocol: 'DPlus' | 'DExtra' | 'DCS' | 'XLX'
  path: string
  url: string
  count: number
  updated_at: string | null
  available: boolean
}

export type SettingsState = {
  admin_required: boolean
  general: {
    callsign: string
    hotspot_name: string
    city: string
    grid: string
  }
  mmdvmhost: {
    module: string
    rx_frequency_hz: number
    tx_frequency_hz: number
    rx_offset_hz: number
    tx_offset_hz: number
    rf_level_percent: number
    rx_level_percent: number
    dstar_tx_level_percent: number
    uart_port: string
    uart_speed: number
    rssi_mapping_file: string
    mqtt_host: string
    mqtt_port: number
    mqtt_name: string
  }
  dstargateway: {
    gateway_address: string
    gateway_port: number
    repeater_address: string
    repeater_port: number
    repeater_module: string
    frequency_mhz: number
    reflector: string
    reflector_module: string
    reflector_at_startup: boolean
    reflector_reconnect: string
    language: string
    ircddb_enabled: boolean
    ircddb_hostname: string
    ircddb_username: string
    dextra_enabled: boolean
    dplus_enabled: boolean
    dcs_enabled: boolean
    xlx_enabled: boolean
    xlx_hostfile_url: string
  }
  hosts: {
    schedule: string
    files: HostFileStatus[]
    xlx_gateway_url: string
  }
  users: {
    count: number
    imported_at: string | null
    source_file: string | null
    columns: string[]
  }
  dashboard: {
    refresh_seconds: number
    last_heard_limit: number
    theme: string
    language: string
    show_diagnostics: boolean
    show_activity: boolean
    show_uptime: boolean
  }
}

export type ReflectorOption = {
  name: string
  host: string
  protocol: 'DPlus' | 'DExtra' | 'DCS' | 'XLX'
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  adminPassword?: string,
): Promise<T> {
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  headers.set('Accept', 'application/json')
  if (adminPassword) headers.set('X-PP5CI-Hotspot-Admin-Password', adminPassword)

  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // Keep HTTP status when the body is not JSON.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export const getSettings = () => requestJson<SettingsState>('/api/v1/settings')

export const checkAdminToken = (token: string) =>
  requestJson<{ ok: boolean }>('/api/v1/settings/admin/check', { method: 'POST', body: '{}' }, token)

export const applySettings = (
  section: string,
  values: Record<string, unknown>,
  restart: boolean,
  token: string,
) => requestJson<{ ok: boolean; restarted?: string[] }>(
  `/api/v1/settings/apply/${section}`,
  { method: 'POST', body: JSON.stringify({ values, restart }) },
  token,
)

export const updateHostFiles = (token: string) =>
  requestJson<{ ok: boolean; updated_at: string; gateway_restarted: boolean }>(
    '/api/v1/settings/hosts/update',
    { method: 'POST', body: '{}' },
    token,
  )

export const searchReflectors = (query = '', protocol = 'all') =>
  requestJson<{ items: ReflectorOption[]; total: number }>(
    `/api/v1/settings/reflectors?q=${encodeURIComponent(query)}&protocol=${encodeURIComponent(protocol)}&limit=200`,
  )

export const importUsersCsv = (file: File, token: string) => {
  const form = new FormData()
  form.append('file', file)
  return requestJson<{
    ok: boolean
    count: number
    imported_at: string
    source_file: string
    detected_columns: string[]
  }>('/api/v1/settings/users/import', { method: 'POST', body: form }, token)
}

export type UpdateReleaseAsset = {
  name: string
  size: number
  download_url: string | null
  api_url: string | null
}

export type UpdateOperation = {
  state: 'idle' | 'running' | 'success' | 'failed' | string
  operation: 'install' | 'rollback' | null
  step: 'download' | 'preparation' | 'backup' | 'installation' | 'restart' | 'health_check' | 'done' | null
  progress: number
  message: string
  started_at: string | null
  finished_at: string | null
  from_version: string | null
  to_version: string | null
  backup_id: string | null
  error: string | null
}

export type UpdatesStatus = {
  generated_at: string
  installed_version: string
  available_version: string | null
  update_available: boolean
  github: {
    state: string
    error: string | null
    repository: string
    repository_url: string
    authenticated: boolean
  }
  channel: string
  compatibility: {
    compatible: boolean
    system: string
    machine: string
    label: string
  }
  release: {
    tag: string | null
    name: string | null
    body: string
    published_at: string | null
    html_url: string | null
    draft: boolean
    prerelease: boolean
    artifact: UpdateReleaseAsset | null
    checksum: UpdateReleaseAsset | null
  } | null
  release_ready: boolean
  installer_ready: boolean
  can_install: boolean
  install_reason: string
  operation: UpdateOperation
}

export type UpdateHistoryItem = {
  started_at: string
  from_version: string | null
  to_version: string | null
  result: string
  duration_seconds: number | null
  operation?: 'install' | 'rollback' | string
  backup_id?: string | null
  error?: string | null
}

export type RollbackOption = {
  id: string
  version: string
  created_at: string | null
  sha256: string | null
}

export const getUpdatesStatus = () => getJson<UpdatesStatus>('/api/v1/updates/status')
export const getUpdateOperation = () => getJson<UpdateOperation>('/api/v1/updates/operation')
export const getUpdateHistory = () => getJson<{ items: UpdateHistoryItem[] }>('/api/v1/updates/history')
export const getRollbackOptions = () => getJson<{ items: RollbackOption[] }>('/api/v1/updates/rollback-options')
export const installUpdate = (token: string) =>
  requestJson<{ ok: boolean; accepted: boolean; operation: string; argument: string; unit: string }>(
    '/api/v1/updates/install',
    { method: 'POST', body: '{}' },
    token,
  )
export const rollbackUpdate = (backupId: string, token: string) =>
  requestJson<{ ok: boolean; accepted: boolean; operation: string; argument: string; unit: string }>(
    '/api/v1/updates/rollback',
    { method: 'POST', body: JSON.stringify({ backup_id: backupId }) },
    token,
  )

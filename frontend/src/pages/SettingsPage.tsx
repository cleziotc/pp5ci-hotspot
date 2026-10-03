import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Database,
  FileUp,
  KeyRound,
  Monitor,
  Network,
  Radio,
  RefreshCcw,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Users,
} from 'lucide-react'
import {
  applySettings,
  checkAdminPassword,
  getSettings,
  importUsersCsv,
  searchReflectors,
  updateHostFiles,
  type ReflectorOption,
  type SettingsState,
} from '../api/client'
import Panel from '../components/Panel'

const tabs = ['Geral', 'MMDVMHost', 'DStarGateway', 'Hosts', 'Usuários CSV', 'Dashboard'] as const
type Tab = typeof tabs[number]

const reconnectOptions = ['never', 'fixed', '5', '10', '15', '20', '25', '30', '60', '90', '120', '180']
const reflectorModules = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('pt-BR', { hour12: false })
}

function mhz(hz: number): string {
  return (Number(hz || 0) / 1_000_000).toFixed(6)
}

function hz(value: string): number {
  const parsed = Number(value.replace(',', '.'))
  return Number.isFinite(parsed) ? Math.round(parsed * 1_000_000) : 0
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Operação não concluída'
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('Geral')
  const [settings, setSettings] = useState<SettingsState | null>(null)
  const [adminPassword, setAdminPassword] = useState('')
  const [adminInput, setAdminInput] = useState('')
  const [adminOk, setAdminOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'good' | 'bad' | 'info'; text: string } | null>(null)
  const [reflectorQuery, setReflectorQuery] = useState('')
  const [reflectors, setReflectors] = useState<ReflectorOption[]>([])
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = async () => {
    try {
      const next = await getSettings()
      setSettings(next)
    } catch (error) {
      setNotice({ tone: 'bad', text: errorMessage(error) })
    }
  }

  useEffect(() => {
    void refresh()
    if (adminPassword) {
      void checkAdminPassword(adminPassword)
        .then(() => setAdminOk(true))
        .catch(() => setAdminOk(false))
    }
  }, [])

  useEffect(() => {
    if (tab !== 'DStarGateway') return
    const handle = window.setTimeout(() => {
      void searchReflectors(reflectorQuery)
        .then((result) => setReflectors(result.items))
        .catch(() => setReflectors([]))
    }, 180)
    return () => window.clearTimeout(handle)
  }, [tab, reflectorQuery])

  const selectedReflector = useMemo(
    () => reflectors.find((item) => item.name === settings?.dstargateway.reflector),
    [reflectors, settings?.dstargateway.reflector],
  )

  const unlockAdmin = async () => {
    const password = adminInput
    if (!password) {
      setNotice({ tone: 'bad', text: 'Informe a senha de administrador.' })
      return
    }
    setBusy(true)
    try {
      await checkAdminPassword(password)
      sessionStorage.setItem('polar-admin-token', token)
      setAdminPassword(password)
      setAdminOk(true)
      setNotice({ tone: 'good', text: 'Sessão administrativa habilitada neste navegador.' })
    } catch (error) {
      setAdminOk(false)
      setNotice({ tone: 'bad', text: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  const lockAdmin = () => {    setAdminPassword('')
    setAdminInput('')
    setAdminOk(false)
    setNotice({ tone: 'info', text: 'Sessão administrativa encerrada.' })
  }

  const requireSettings = () => {
    if (!settings) throw new Error('Settings ainda não carregado')
    if (!adminOk || !adminPassword) throw new Error('Habilite o modo administrador para alterar configurações')
    return settings
  }

  const payloadForTab = (current: SettingsState): { section: string; values: Record<string, unknown> } | null => {
    if (tab === 'Geral') return { section: 'general', values: current.general }
    if (tab === 'MMDVMHost') return { section: 'mmdvmhost', values: current.mmdvmhost }
    if (tab === 'DStarGateway') return { section: 'dstargateway', values: current.dstargateway }
    if (tab === 'Hosts') return { section: 'hosts', values: { schedule: current.hosts.schedule } }
    if (tab === 'Dashboard') return { section: 'dashboard', values: current.dashboard }
    return null
  }

  const saveCurrent = async (restart: boolean) => {
    try {
      const current = requireSettings()
      const payload = payloadForTab(current)
      if (!payload) {
        setNotice({ tone: 'info', text: 'Nesta aba as alterações são aplicadas pelo botão de importação.' })
        return
      }
      setBusy(true)
      const result = await applySettings(payload.section, payload.values, restart, adminPassword)
      const restarted = result.restarted?.length
        ? ` Serviços reiniciados: ${result.restarted.join(', ')}.`
        : ''
      setNotice({
        tone: 'good',
        text: restart ? `Configuração aplicada com sucesso.${restarted}` : 'Configuração salva com sucesso.',
      })
      await refresh()
    } catch (error) {
      setNotice({ tone: 'bad', text: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  const updateHostsNow = async () => {
    try {
      requireSettings()
      setBusy(true)
      const result = await updateHostFiles(adminPassword)
      setNotice({
        tone: 'good',
        text: result.gateway_restarted
          ? 'Host files atualizados e DStarGateway reiniciado para carregar as novas listas.'
          : 'Host files atualizados.',
      })
      await refresh()
      if (tab === 'DStarGateway') {
        const resultReflectors = await searchReflectors(reflectorQuery)
        setReflectors(resultReflectors.items)
      }
    } catch (error) {
      setNotice({ tone: 'bad', text: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  const uploadCsv = async () => {
    if (!csvFile) {
      setNotice({ tone: 'bad', text: 'Selecione primeiro um arquivo .csv.' })
      return
    }
    if (csvFile.size > 500 * 1024 * 1024) {
      setNotice({ tone: 'bad', text: 'O arquivo excede o limite de 500 MB.' })
      return
    }
    try {
      requireSettings()
      setBusy(true)
      const result = await importUsersCsv(csvFile, adminPassword)
      setNotice({
        tone: 'good',
        text: `CSV importado: ${result.count.toLocaleString('pt-BR')} registros válidos.`,
      })
      setCsvFile(null)
      if (fileInput.current) fileInput.current.value = ''
      await refresh()
    } catch (error) {
      setNotice({ tone: 'bad', text: errorMessage(error) })
    } finally {
      setBusy(false)
    }
  }

  if (!settings) {
    return <div className="standard-page settings-page"><Panel className="tab-placeholder"><h2>Settings</h2><p>Carregando configurações reais…</p></Panel></div>
  }

  return (
    <div className="standard-page settings-page settings-live">
      <div className="page-title-row settings-title-row">
        <div>
          <h1>Settings</h1>
          <small>Configuração real do N0CALL Hotspot, D-Star, hosts, usuários e dashboard</small>
        </div>
        <div className="page-actions">
          <button disabled={busy || tab === 'Usuários CSV'} onClick={() => void saveCurrent(false)}><Save size={16} /> Salvar</button>
          <button className="good-action" disabled={busy || tab === 'Usuários CSV'} onClick={() => void saveCurrent(true)}>✓ Aplicar</button>
          <button disabled={busy} onClick={() => void refresh()}><RotateCcw size={16} /> Restaurar</button>
        </div>
      </div>

      <div className={'settings-admin-bar ' + (adminOk ? 'unlocked' : '')}>
        <div className="settings-admin-state">
          {adminOk ? <ShieldCheck size={18} /> : <KeyRound size={18} />}
          <span><b>{adminOk ? 'Administrador habilitado' : 'Modo administrador bloqueado'}</b><small>Alterações são protegidas por uma senha local e executadas por helper restrito.</small></span>
        </div>
        <div className="settings-admin-login">
          {!adminOk ? (
            <>
              <input
                type="password"
                value={adminInput}
                placeholder="Senha de administrador"
                onChange={(event) => setAdminInput(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') void unlockAdmin() }}
              />
              <button className="primary" disabled={busy} onClick={() => void unlockAdmin()}>Habilitar</button>
            </>
          ) : <button onClick={lockAdmin}>Encerrar sessão</button>}
        </div>
      </div>

      {notice ? <div className={'settings-notice ' + notice.tone}>{notice.text}</div> : null}

      <div className="tab-row">
        {tabs.map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}
      </div>

      {tab === 'Geral' && (
        <div className="settings-grid settings-grid-live">
          <Panel className="settings-card">
            <div className="section-title"><Users /><div><h2>Identificação</h2><small>Identidade básica do hotspot</small></div></div>
            <div className="form-grid">
              <label>Callsign<input value={settings.general.callsign} onChange={(event) => setSettings({ ...settings, general: { ...settings.general, callsign: event.target.value.toUpperCase() } })} /></label>
              <label>Nome<input value={settings.general.hotspot_name} onChange={(event) => setSettings({ ...settings, general: { ...settings.general, hotspot_name: event.target.value } })} /></label>
              <label>Cidade / QTH<input value={settings.general.city} onChange={(event) => setSettings({ ...settings, general: { ...settings.general, city: event.target.value } })} /></label>
              <label>Grid Locator<input value={settings.general.grid} onChange={(event) => setSettings({ ...settings, general: { ...settings.general, grid: event.target.value.toUpperCase() } })} /></label>
            </div>
            <p className="settings-help">Ao aplicar uma mudança de indicativo, MMDVMHost e DStarGateway são mantidos sincronizados e reiniciados de forma controlada.</p>
          </Panel>

          <Panel className="settings-card settings-wide-card">
            <div className="section-title"><Network /><div><h2>Arquitetura ativa</h2><small>Resumo somente leitura da cadeia local</small></div></div>
            <div className="settings-summary-grid">
              <span><small>MMDVMHost → Gateway</small><b>{settings.dstargateway.gateway_address}:{settings.dstargateway.gateway_port}</b></span>
              <span><small>Gateway → MMDVMHost</small><b>{settings.dstargateway.repeater_address}:{settings.dstargateway.repeater_port}</b></span>
              <span><small>UART</small><b>{settings.mmdvmhost.uart_port}</b></span>
              <span><small>MQTT</small><b>{settings.mmdvmhost.mqtt_host}:{settings.mmdvmhost.mqtt_port}</b></span>
              <span><small>RSSI Mapping</small><b>{settings.mmdvmhost.rssi_mapping_file || '—'}</b></span>
              <span><small>Módulo local</small><b>{settings.mmdvmhost.module}</b></span>
            </div>
          </Panel>
        </div>
      )}

      {tab === 'MMDVMHost' && (
        <div className="settings-grid settings-grid-live">
          <Panel className="settings-card">
            <div className="section-title"><Radio /><div><h2>RF / Modem</h2><small>Parâmetros efetivos do MMDVMHost</small></div></div>
            <div className="form-grid two">
              <label>RX Frequency (MHz)<input value={mhz(settings.mmdvmhost.rx_frequency_hz)} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, rx_frequency_hz: hz(event.target.value) } })} /></label>
              <label>TX Frequency (MHz)<input value={mhz(settings.mmdvmhost.tx_frequency_hz)} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, tx_frequency_hz: hz(event.target.value) } })} /></label>
              <label>RX Offset (Hz)<input type="number" value={settings.mmdvmhost.rx_offset_hz} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, rx_offset_hz: Number(event.target.value) } })} /></label>
              <label>TX Offset (Hz)<input type="number" value={settings.mmdvmhost.tx_offset_hz} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, tx_offset_hz: Number(event.target.value) } })} /></label>
              <label>RF Level (%)<input type="number" min="0" max="100" value={settings.mmdvmhost.rf_level_percent} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, rf_level_percent: Number(event.target.value) } })} /></label>
              <label>RX Level (%)<input type="number" min="0" max="100" value={settings.mmdvmhost.rx_level_percent} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, rx_level_percent: Number(event.target.value) } })} /></label>
              <label>D-Star TX Level (%)<input type="number" min="0" max="100" value={settings.mmdvmhost.dstar_tx_level_percent} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, dstar_tx_level_percent: Number(event.target.value) } })} /></label>
              <label>Módulo local<select value={settings.mmdvmhost.module} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, module: event.target.value } })}>{reflectorModules.map((letter) => <option key={letter}>{letter}</option>)}</select></label>
            </div>
          </Panel>

          <Panel className="settings-card">
            <div className="section-title"><Settings2 /><div><h2>Serial / Telemetria</h2><small>UART, RSSI e MQTT</small></div></div>
            <div className="form-grid">
              <label>UART Device<input value={settings.mmdvmhost.uart_port} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, uart_port: event.target.value } })} /></label>
              <label>UART Baudrate<input type="number" value={settings.mmdvmhost.uart_speed} onChange={(event) => setSettings({ ...settings, mmdvmhost: { ...settings.mmdvmhost, uart_speed: Number(event.target.value) } })} /></label>
              <label>RSSI Mapping<input value={settings.mmdvmhost.rssi_mapping_file} readOnly /></label>
              <label>MQTT Host<input value={settings.mmdvmhost.mqtt_host} readOnly /></label>
              <label>MQTT Port<input value={settings.mmdvmhost.mqtt_port} readOnly /></label>
              <label>MQTT Name<input value={settings.mmdvmhost.mqtt_name} readOnly /></label>
            </div>
            <p className="settings-help">RSSI Mapping e MQTT ficam somente leitura nesta tela para preservar a telemetria validada do projeto.</p>
          </Panel>
        </div>
      )}

      {tab === 'DStarGateway' && (
        <div className="settings-grid settings-grid-live dstar-settings-grid">
          <Panel className="settings-card">
            <div className="section-title"><Radio /><div><h2>Refletor padrão</h2><small>Seleção de REF, XRF, DCS ou XLX e módulo</small></div></div>
            <div className="reflector-picker">
              <label className="reflector-search-label">
                Refletor
                <div className="reflector-search">
                  <Search size={15} />
                  <input
                    value={reflectorQuery || settings.dstargateway.reflector}
                    placeholder="Ex.: XLX026"
                    onFocus={() => { if (!reflectorQuery) setReflectorQuery(settings.dstargateway.reflector) }}
                    onChange={(event) => {
                      const value = event.target.value.toUpperCase()
                      setReflectorQuery(value)
                      setSettings({ ...settings, dstargateway: { ...settings.dstargateway, reflector: value.replace(/\s+[A-Z]$/, '') } })
                    }}
                  />
                </div>
              </label>
              <label>Módulo do refletor<select value={settings.dstargateway.reflector_module} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, reflector_module: event.target.value } })}>{reflectorModules.map((letter) => <option key={letter}>{letter}</option>)}</select></label>
            </div>

            <div className="reflector-results">
              {reflectors.slice(0, 12).map((item) => (
                <button
                  key={item.protocol + item.name}
                  className={settings.dstargateway.reflector === item.name ? 'selected' : ''}
                  onClick={() => {
                    setReflectorQuery(item.name)
                    setSettings({ ...settings, dstargateway: { ...settings.dstargateway, reflector: item.name } })
                  }}
                >
                  <b>{item.name}</b><small>{item.protocol} · {item.host}</small>
                </button>
              ))}
              {!reflectors.length && <small className="muted-copy">Digite parte do refletor para pesquisar nas listas locais.</small>}
            </div>

            <div className="reflector-current">
              <span>Selecionado <b>{settings.dstargateway.reflector || 'Nenhum'} {settings.dstargateway.reflector ? settings.dstargateway.reflector_module : ''}</b></span>
              <span>Protocolo <b>{selectedReflector?.protocol || 'automático pelo prefixo'}</b></span>
            </div>

            <div className="switch-list">
              <label><input type="checkbox" checked={settings.dstargateway.reflector_at_startup} disabled={!settings.dstargateway.reflector} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, reflector_at_startup: event.target.checked } })} /> Conectar ao refletor na inicialização</label>
            </div>
            <div className="form-grid">
              <label>Auto-reconnect<select value={settings.dstargateway.reflector_reconnect} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, reflector_reconnect: event.target.value } })}>{reconnectOptions.map((value) => <option key={value} value={value}>{value === 'never' ? 'Nunca' : value === 'fixed' ? 'Fixo' : `${value} min`}</option>)}</select></label>
            </div>
          </Panel>

          <Panel className="settings-card">
            <div className="section-title"><Network /><div><h2>Gateway / Repeater</h2><small>Portas Homebrew e módulo local</small></div></div>
            <div className="form-grid">
              <label>Gateway Address<input value={settings.dstargateway.gateway_address} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, gateway_address: event.target.value } })} /></label>
              <label>Gateway Port<input type="number" value={settings.dstargateway.gateway_port} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, gateway_port: Number(event.target.value) } })} /></label>
              <label>Repeater Address<input value={settings.dstargateway.repeater_address} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, repeater_address: event.target.value } })} /></label>
              <label>Repeater Port<input type="number" value={settings.dstargateway.repeater_port} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, repeater_port: Number(event.target.value) } })} /></label>
              <label>Módulo local<select value={settings.dstargateway.repeater_module} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, repeater_module: event.target.value } })}>{reflectorModules.map((letter) => <option key={letter}>{letter}</option>)}</select></label>
              <label>Frequência (MHz)<input type="number" step="0.000001" value={settings.dstargateway.frequency_mhz} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, frequency_mhz: Number(event.target.value) } })} /></label>
              <label>Idioma<select value={settings.dstargateway.language} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, language: event.target.value } })}><option value="portugues">Português</option><option value="english_us">English US</option><option value="english_uk">English UK</option><option value="espanol">Español</option></select></label>
            </div>
          </Panel>

          <Panel className="settings-card callsign-routing-card">
            <div className="section-title"><Users /><div><h2>Callsign Routing (ircDDB)</h2><small>Chamadas diretas D-STAR por indicativo</small></div></div>
            <div className="switch-list">
              <label>
                <input
                  type="checkbox"
                  checked={settings.dstargateway.ircddb_enabled}
                  onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, ircddb_enabled: event.target.checked } })}
                />
                Habilitar chamadas diretas via ircDDB / QuadNet
              </label>
            </div>
            <div className="form-grid">
              <label>Servidor ircDDB<input value={settings.dstargateway.ircddb_hostname} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, ircddb_hostname: event.target.value } })} /></label>
              <label>Usuário / Callsign<input value={settings.dstargateway.ircddb_username} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, ircddb_username: event.target.value.toUpperCase() } })} /></label>
            </div>
            <div className={'routing-config-state ' + (settings.dstargateway.ircddb_enabled ? 'on' : 'off')}>
              <b>{settings.dstargateway.ircddb_enabled ? '● CALLSIGN ROUTING HABILITADO' : '○ CALLSIGN ROUTING DESABILITADO'}</b>
              <span>{settings.dstargateway.ircddb_enabled ? `${settings.dstargateway.ircddb_hostname} · ${settings.dstargateway.ircddb_username}` : 'Chamadas diretas por indicativo não serão roteadas.'}</span>
            </div>
            <p className="settings-help">Para uma chamada direta no rádio, use o indicativo da outra estação no campo TO/URCALL, por exemplo PY2ABC. A senha ircDDB permanece vazia conforme a configuração do servidor QuadNet.</p>
          </Panel>

          <Panel className="settings-card">
            <div className="section-title"><Settings2 /><div><h2>Protocolos de refletores</h2><small>Protocolos habilitados no DStarGateway</small></div></div>
            <div className="protocol-grid">
              <label><input type="checkbox" checked={settings.dstargateway.dplus_enabled} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, dplus_enabled: event.target.checked } })} /><span><b>DPlus</b><small>REFxxx</small></span></label>
              <label><input type="checkbox" checked={settings.dstargateway.dextra_enabled} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, dextra_enabled: event.target.checked } })} /><span><b>DExtra</b><small>XRFxxx</small></span></label>
              <label><input type="checkbox" checked={settings.dstargateway.dcs_enabled} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, dcs_enabled: event.target.checked } })} /><span><b>DCS</b><small>DCSxxx</small></span></label>
              <label><input type="checkbox" checked={settings.dstargateway.xlx_enabled} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, xlx_enabled: event.target.checked } })} /><span><b>XLX</b><small>XLXxxx via DCS</small></span></label>
            </div>
            <div className="form-grid">
              <label>XLX Hostfile URL<input value={settings.dstargateway.xlx_hostfile_url} onChange={(event) => setSettings({ ...settings, dstargateway: { ...settings.dstargateway, xlx_hostfile_url: event.target.value } })} /></label>
            </div>
            <p className="settings-help">Ao selecionar um refletor, o protocolo correspondente é habilitado automaticamente ao salvar/aplicar.</p>
          </Panel>
        </div>
      )}

      {tab === 'Hosts' && (
        <div className="settings-grid settings-grid-live hosts-settings-grid">
          <Panel className="settings-card settings-wide-card">
            <div className="section-title"><Settings2 /><div><h2>Atualização automática</h2><small>Listas de refletores usadas pelo DStarGateway e pelo seletor</small></div></div>
            <div className="hosts-control">
              <label>Executar diariamente às<input type="time" value={settings.hosts.schedule} onChange={(event) => setSettings({ ...settings, hosts: { ...settings.hosts, schedule: event.target.value } })} /></label>
              <button className="primary" disabled={busy || !adminOk} onClick={() => void updateHostsNow()}><RefreshCcw size={15} /> Atualizar agora</button>
            </div>
            <p className="settings-help">A atualização manual substitui os arquivos apenas após validar o download. DPlus, DExtra e DCS são carregados pelo gateway após reinício; XLX é mantido também como catálogo para o seletor.</p>
          </Panel>

          {settings.hosts.files.map((host) => (
            <Panel key={host.protocol} className="settings-card host-source-card">
              <div className="host-source-head"><Database /><div><h2>{host.protocol}</h2><small>{host.available ? 'Arquivo disponível' : 'Ainda não baixado'}</small></div></div>
              <strong>{host.count.toLocaleString('pt-BR')}</strong><span>entradas</span>
              <p><small>Última atualização</small><b>{formatDate(host.updated_at)}</b></p>
              <code>{host.url}</code>
              <small className="host-path">{host.path}</small>
            </Panel>
          ))}

          <Panel className="settings-card settings-wide-card">
            <div className="section-title"><Network /><div><h2>Fonte XLX do DStarGateway</h2><small>URL consumida pelo próprio gateway para conexão direta XLX</small></div></div>
            <code className="settings-code">{settings.hosts.xlx_gateway_url}</code>
          </Panel>
        </div>
      )}

      {tab === 'Usuários CSV' && (
        <div className="settings-grid settings-grid-live csv-settings-grid">
          <Panel className="settings-card">
            <div className="section-title"><Database /><div><h2>Base de usuários (.csv)</h2><small>Enriquece Last Heard com nome e localização</small></div></div>
            <div className="upload-box settings-upload-box" onClick={() => fileInput.current?.click()}>
              <FileUp size={34} />
              <b>{csvFile ? csvFile.name : 'Selecione um arquivo .csv'}</b>
              <small>Máximo 500 MB · UTF-8 ou Latin-1 · vírgula, ponto e vírgula ou TAB</small>
              <button type="button">Escolher arquivo</button>
              <input ref={fileInput} hidden type="file" accept=".csv,text/csv" onChange={(event) => setCsvFile(event.target.files?.[0] || null)} />
            </div>
            <button className="primary csv-import-button" disabled={!csvFile || busy || !adminOk} onClick={() => void uploadCsv()}>Importar e substituir base</button>
          </Panel>

          <Panel className="settings-card">
            <div className="section-title"><Users /><div><h2>Base carregada</h2><small>Estado atual no SQLite</small></div></div>
            <div className="csv-live-summary">
              <span><small>Registros</small><b>{settings.users.count.toLocaleString('pt-BR')}</b></span>
              <span><small>Último import</small><b>{formatDate(settings.users.imported_at)}</b></span>
              <span><small>Arquivo</small><b>{settings.users.source_file || '—'}</b></span>
              <span><small>Campos usados</small><b>{settings.users.columns.join(' · ')}</b></span>
            </div>
            <p className="settings-help">A coluna de indicativo é obrigatória. O importador reconhece Callsign/Call/Indicativo; Name/Nome; Location/Local/City/Cidade/QTH; e State/Estado/UF. Quando cidade e estado existem em colunas separadas, a localização é exibida como Cidade - UF. Registros históricos também passam a mostrar os dados do diretório pelo indicativo.</p>
          </Panel>
        </div>
      )}

      {tab === 'Dashboard' && (
        <div className="settings-grid settings-grid-live">
          <Panel className="settings-card">
            <div className="section-title"><Monitor /><div><h2>Preferências do dashboard</h2><small>Aparência e densidade de informações</small></div></div>
            <div className="form-grid">
              <label>Atualização resumo (s)<input type="number" min="1" max="60" value={settings.dashboard.refresh_seconds} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, refresh_seconds: Number(event.target.value) } })} /></label>
              <label>Last Heard<input type="number" min="4" max="30" value={settings.dashboard.last_heard_limit} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, last_heard_limit: Number(event.target.value) } })} /></label>
              <label>Tema<select value={settings.dashboard.theme} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, theme: event.target.value } })}><option value="dark">Dark</option></select></label>
              <label>Idioma<select value={settings.dashboard.language} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, language: event.target.value } })}><option value="pt-BR">Português (Brasil)</option></select></label>
            </div>
            <div className="switch-list">
              <label><input type="checkbox" checked={settings.dashboard.show_diagnostics} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, show_diagnostics: event.target.checked } })} /> Mostrar badges de diagnóstico</label>
              <label><input type="checkbox" checked={settings.dashboard.show_activity} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, show_activity: event.target.checked } })} /> Exibir gráfico de atividade</label>
              <label><input type="checkbox" checked={settings.dashboard.show_uptime} onChange={(event) => setSettings({ ...settings, dashboard: { ...settings.dashboard, show_uptime: event.target.checked } })} /> Exibir uptime</label>
            </div>
          </Panel>

          <Panel className="settings-card">
            <div className="section-title"><Monitor /><div><h2>Comportamento</h2><small>O que já é tempo real e o que usa refresh</small></div></div>
            <div className="settings-summary-grid one-column">
              <span><small>Tráfego D-Star</small><b>SSE instantâneo</b></span>
              <span><small>BER ao vivo</small><b>SSE · ~1 s</b></span>
              <span><small>RSSI ao vivo</small><b>SSE · ~420 ms</b></span>
              <span><small>Resumo / estatísticas</small><b>{settings.dashboard.refresh_seconds} s</b></span>
              <span><small>Últimas transmissões</small><b>{settings.dashboard.last_heard_limit} registros</b></span>
            </div>
          </Panel>
        </div>
      )}
    </div>
  )
}

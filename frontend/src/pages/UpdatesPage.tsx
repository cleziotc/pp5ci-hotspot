import { useCallback, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, Cloud, GitBranch, RefreshCw, ShieldCheck } from 'lucide-react'
import {
  getRollbackOptions,
  getUpdateHistory,
  getUpdateOperation,
  getUpdatesStatus,
  installUpdate,
  rollbackUpdate,
  type RollbackOption,
  type UpdateHistoryItem,
  type UpdateOperation,
  type UpdatesStatus,
} from '../api/client'
import Panel from '../components/Panel'

function displayVersion(value: string | null | undefined) {
  if (!value) return '—'
  return value.startsWith('v') ? value : `v${value}`
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Sao_Paulo',
  }).format(date)
}

function githubLabel(state: string) {
  if (state === 'online') return 'ONLINE'
  if (state === 'auth_required') return 'AUTH REQUIRED'
  if (state === 'auth_error') return 'AUTH ERROR'
  if (state === 'not_found') return 'NOT FOUND'
  return 'OFFLINE'
}

const pipelineSteps = [
  { key: 'download', label: 'Download' },
  { key: 'preparation', label: 'Preparação' },
  { key: 'backup', label: 'Backup' },
  { key: 'installation', label: 'Instalação' },
  { key: 'restart', label: 'Reinício' },
  { key: 'health_check', label: 'Health check' },
] as const

function pipelineState(operation: UpdateOperation | null, index: number) {
  if (!operation || operation.state === 'idle') return { className: '', icon: '○', text: 'Pendente' }
  if (operation.state === 'success') return { className: 'done', icon: '✓', text: 'Concluído' }

  const current = pipelineSteps.findIndex((item) => item.key === operation.step)
  if (current < 0) return { className: '', icon: '○', text: 'Pendente' }

  if (operation.state === 'failed' && index === current) {
    return { className: 'failed', icon: '!', text: 'Falhou' }
  }
  if (index < current) return { className: 'done', icon: '✓', text: 'Concluído' }
  if (operation.state === 'running' && index === current) return { className: 'active', icon: '●', text: 'Em andamento' }
  return { className: '', icon: '○', text: 'Pendente' }
}

function historyResult(value: string) {
  if (value === 'success') return 'Sucesso'
  if (value === 'failed') return 'Falha'
  return value
}

export default function UpdatesPage() {
  const [status, setStatus] = useState<UpdatesStatus | null>(null)
  const [history, setHistory] = useState<UpdateHistoryItem[]>([])
  const [rollbacks, setRollbacks] = useState<RollbackOption[]>([])
  const [operation, setOperation] = useState<UpdateOperation | null>(null)
  const [selectedRollbackId, setSelectedRollbackId] = useState('')
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [adminPassword, setAdminPassword] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setNotice(null)
    try {
      const [nextStatus, nextHistory, nextRollbacks] = await Promise.all([
        getUpdatesStatus(),
        getUpdateHistory(),
        getRollbackOptions(),
      ])
      setStatus(nextStatus)
      setOperation(nextStatus.operation)
      setHistory(nextHistory.items)
      setRollbacks(nextRollbacks.items)
      setSelectedRollbackId((current) => {
        if (current && nextRollbacks.items.some((item) => item.id === current)) return current
        return nextRollbacks.items[0]?.id || ''
      })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Falha ao verificar atualizações')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (operation?.state !== 'running') return
    const timer = window.setInterval(() => {
      void getUpdateOperation()
        .then((next) => {
          setOperation(next)
          if (next.state !== 'running') {
            window.setTimeout(() => void refresh(), 800)
          }
        })
        .catch(() => {
          // A API pode ficar indisponível por alguns segundos durante o reinício.
        })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [operation?.state, refresh])

  const release = status?.release
  const selectedRollback = rollbacks.find((item) => item.id === selectedRollbackId) ?? null
  const githubState = status?.github.state ?? 'offline'
  const githubGood = githubState === 'online'
  const busy = operation?.state === 'running'

  const releaseChecks = useMemo(() => [
    {
      ok: Boolean(release && !release.draft && !release.prerelease),
      title: 'Release pronta',
      detail: release ? `Draft: ${release.draft ? 'sim' : 'não'} · Pre-release: ${release.prerelease ? 'sim' : 'não'}` : 'Nenhuma release',
    },
    {
      ok: Boolean(status?.compatibility.compatible),
      title: 'Compatível',
      detail: status?.compatibility.label || '—',
    },
    {
      ok: Boolean(release?.artifact),
      title: 'Artefato',
      detail: release?.artifact?.name || 'Ausente',
    },
    {
      ok: Boolean(release?.checksum),
      title: 'SHA-256',
      detail: release?.checksum?.name || 'Ausente',
    },
  ], [release, status])

  const openRepository = () => {
    if (status?.github.repository_url) window.open(status.github.repository_url, '_blank', 'noopener,noreferrer')
  }

  const startInstall = async () => {
    if (!status?.can_install || !adminPassword || !status.available_version) return
    const accepted = window.confirm(
      `Instalar ${displayVersion(status.available_version)}?\n\nO PP5CI Hotspot fará download, validará SHA-256, criará backup, atualizará somente a camada web e executará health check. A cadeia RF não será reiniciada pelo updater.`,
    )
    if (!accepted) return
    setActing(true)
    setNotice(null)
    try {
      await installUpdate(adminPassword)
      setOperation({
        state: 'running',
        operation: 'install',
        step: null,
        progress: 0,
        message: 'Operação aceita; aguardando início do updater',
        started_at: new Date().toISOString(),
        finished_at: null,
        from_version: status.installed_version,
        to_version: status.available_version.replace(/^v/, ''),
        backup_id: null,
        error: null,
      })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Falha ao iniciar atualização')
    } finally {
      setActing(false)
    }
  }

  const startRollback = async () => {
    if (!selectedRollback || !adminPassword || busy) return
    const accepted = window.confirm(
      `Voltar para ${displayVersion(selectedRollback.version)}?\n\nAntes do rollback será criado um novo ponto de retorno. Configurações e banco de dados permanecem preservados.`,
    )
    if (!accepted) return
    setActing(true)
    setNotice(null)
    try {
      await rollbackUpdate(selectedRollback.id, adminPassword)
      setOperation({
        state: 'running',
        operation: 'rollback',
        step: null,
        progress: 0,
        message: 'Operação aceita; aguardando início do updater',
        started_at: new Date().toISOString(),
        finished_at: null,
        from_version: status?.installed_version || null,
        to_version: selectedRollback.version,
        backup_id: selectedRollback.id,
        error: null,
      })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Falha ao iniciar rollback')
    } finally {
      setActing(false)
    }
  }

  const progress = Math.max(0, Math.min(100, Number(operation?.progress || 0)))

  return (
    <div className="standard-page updates-page updates-live">
      <div className="page-title-row">
        <div>
          <h1>Atualizações</h1>
          <small>GitHub Releases reais · release notes obrigatórias · SHA-256 · backup transacional · rollback</small>
        </div>
        <div className="page-actions">
          <input
            type="password"
            value={adminPassword}
            placeholder="Senha de administrador"
            autoComplete="current-password"
            onChange={(event) => setAdminPassword(event.target.value)}
            disabled={busy || acting}
          />
          <button disabled={loading || busy} onClick={() => void refresh()}><RefreshCw size={16} /> {loading ? 'Verificando…' : 'Verificar agora'}</button>
          <button
            className="primary"
            disabled={!status?.can_install || !adminPassword || acting || busy}
            title={!adminPassword ? 'Informe a senha de administrador' : status?.install_reason || ''}
            onClick={() => void startInstall()}
          >
            ↓ {acting ? 'Iniciando…' : 'Atualizar'}
          </button>
        </div>
      </div>

      {notice ? <div className="settings-notice bad">{notice}</div> : null}

      <div className="updates-kpis">
        <Panel><div className="update-kpi"><CheckCircle2 /><div><small>Instalada</small><strong>● {displayVersion(status?.installed_version)}</strong><span>API local</span></div></div></Panel>
        <Panel><div className="update-kpi"><Cloud /><div><small>Disponível</small><strong>● {displayVersion(status?.available_version)}</strong><span>{status?.update_available ? 'Atualização disponível' : 'Sem versão mais nova'}</span></div></div></Panel>
        <Panel><div className="update-kpi"><GitBranch /><div><small>GitHub</small><strong className={githubGood ? '' : 'warn-text'}>● {githubLabel(githubState)}</strong><span>{status?.github.repository || 'cleziotc/pp5ci-hotspot'}</span></div></div></Panel>
        <Panel><div className="update-kpi"><GitBranch /><div><small>Canal</small><strong>● {(status?.channel || 'stable').toUpperCase()}</strong><span>Release oficial</span></div></div></Panel>
        <Panel><div className="update-kpi"><ShieldCheck /><div><small>Admin</small><strong className={adminPassword ? '' : 'warn-text'}>● {adminPassword ? 'HABILITADO' : 'BLOQUEADO'}</strong><span>{adminPassword ? 'Senha informada nesta página' : 'Informe abaixo'}</span></div></div></Panel>
      </div>

      <div className="updates-grid">
        <div className="updates-left">
          <Panel title="Release disponível">
            {release ? (
              <>
                <div className="release-header">
                  <div>
                    <strong className="release-version">{displayVersion(release.tag)}</strong>
                    <span className="direction-pill">{status?.update_available ? 'Nova versão' : 'Última versão'}</span>
                    <small>Publicado em {formatDate(release.published_at)}</small>
                  </div>
                </div>
                <div className="release-checks">
                  {releaseChecks.map((item) => (
                    <div key={item.title} className={item.ok ? '' : 'release-check-bad'}>
                      {item.ok ? '✓' : '!'}
                      <span><b>{item.title}</b><small>{item.detail}</small></span>
                    </div>
                  ))}
                </div>
                <div className="release-notes">
                  <b>Release notes</b>
                  <pre>{release.body || 'A release não possui notas.'}</pre>
                </div>
              </>
            ) : (
              <div className="update-empty">
                <b>Nenhuma GitHub Release disponível</b>
                <small>{status?.github.error || 'Publique a primeira release oficial para preencher esta área.'}</small>
              </div>
            )}
          </Panel>

          <Panel title="Rollback de release">
            {selectedRollback ? (
              <div className="rollback-row">
                <select
                  value={selectedRollbackId}
                  disabled={busy || acting}
                  onChange={(event) => setSelectedRollbackId(event.target.value)}
                >
                  {rollbacks.map((item) => <option key={item.id} value={item.id}>{displayVersion(item.version)} · {formatDate(item.created_at)}</option>)}
                </select>
                <div><b>{displayVersion(selectedRollback.version)}</b><small>Backup local real</small></div>
                <button
                  className="primary"
                  disabled={!adminPassword || busy || acting}
                  onClick={() => void startRollback()}
                >
                  ↶ Voltar para esta release
                </button>
              </div>
            ) : (
              <div className="update-empty compact"><b>Nenhum rollback disponível</b><small>Backups aparecerão aqui somente quando existirem no appliance.</small></div>
            )}
          </Panel>
        </div>

        <div className="updates-right">
          <Panel title="⚙ Atualização em tempo real">
            <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
            <div className="progress-line"><span>{operation?.message || 'Aguardando uma operação de update'}</span><b>{progress}%</b></div>
            <div className="pipeline">
              {pipelineSteps.map((item, index) => {
                const state = pipelineState(operation, index)
                return (
                  <div key={item.key} className={state.className}>
                    <span>{state.icon}</span><b>{item.label}</b><small>{state.text}</small>
                  </div>
                )
              })}
            </div>
            {operation?.error ? <div className="update-operation-error">{operation.error}</div> : null}
            <div className="update-install-reason">{busy ? 'Operação transacional em execução. Não desligue o equipamento durante esta etapa.' : status?.install_reason || 'Verificando capacidade de instalação…'}</div>
          </Panel>

          <Panel title="◷ Histórico real">
            <div className="diag-table-scroll">
              <table className="data-table">
                <thead><tr><th>DATA</th><th>DE</th><th>PARA</th><th>RESULTADO</th><th>DURAÇÃO</th></tr></thead>
                <tbody>
                  {history.length ? history.map((item, index) => (
                    <tr key={`${item.started_at}-${index}`}>
                      <td>{formatDate(item.started_at)}</td>
                      <td>{displayVersion(item.from_version)}</td>
                      <td>{displayVersion(item.to_version)}</td>
                      <td>{historyResult(item.result)}</td>
                      <td>{item.duration_seconds == null ? '—' : `${Math.round(item.duration_seconds)}s`}</td>
                    </tr>
                  )) : <tr><td colSpan={5} className="empty-cell">Nenhuma atualização ou rollback foi executado por esta página.</td></tr>}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="◉ Repositório">
            <div className="repository-row">
              <div><b>{status?.github.repository || 'cleziotc/pp5ci-hotspot'}</b><small>Fonte das releases, código e documentação.</small></div>
              <button onClick={openRepository}>Abrir no GitHub</button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

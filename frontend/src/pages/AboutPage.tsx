import { Code2, Cpu, Database, Monitor, Radio, RadioTower, RefreshCw, Server } from 'lucide-react'
import Panel from '../components/Panel'

export default function AboutPage() {
  return (
    <div className="standard-page about-page">
      <div className="about-top">
        <Panel title="Sobre o PP5CI Hotspot">
          <div className="about-copy">
            <div className="about-icon">ⓘ</div>
            <div className="about-intro">
              <p>
                O PP5CI Hotspot é um appliance D-STAR para Linux que integra modem MMDVM,
                MMDVMHost, DStarGateway e uma camada web completa de operação. A versão 0.2.14
                reúne monitoramento em tempo real de RF e rede, estatísticas, configuração,
                diagnóstico e atualização transacional sem interferir desnecessariamente na cadeia RF.
              </p>
              <div className="about-badges">
                <span>● v0.2.14 estável</span>
                <span>D-STAR simplex</span>
                <span>Linux x86_64</span>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="Arquitetura">
          <div className="architecture-stack">
            <div className="architecture-flow">
              <div><Radio /><b>RF / ID-52</b><small>D-STAR</small></div>
              <span>→</span>
              <div><Cpu /><b>MMDVM</b><small>Dual Hat</small></div>
              <span>→</span>
              <div><Server /><b>MMDVMHost</b><small>UART 115200</small></div>
              <span>→</span>
              <div><RadioTower /><b>DStarGateway</b><small>Gateway</small></div>
              <span>→</span>
              <div><RadioTower /><b>Rede D-STAR</b><small>REF / XRF / DCS / XLX</small></div>
            </div>
            <div className="architecture-data-flow">
              <span>MMDVMHost</span><b>→</b><span>MQTT</span><b>→</b><span>Collector</span><b>→</b>
              <span>SQLite</span><b>→</b><span>FastAPI</span><b>→</b><span>Nginx / React</span>
            </div>
          </div>
        </Panel>
      </div>

      <Panel title="Componentes da v0.2.14">
        <div className="component-grid">
          <div>
            <Radio />
            <b>MMDVM Modem</b>
            <p>Interface RF para voz e dados D-STAR ligada por USB/UART ao servidor.</p>
            <small>MMDVM_HS_Dual_Hat v1.5.2</small>
          </div>
          <div>
            <Cpu />
            <b>MMDVMHost</b>
            <p>Controla o modem, processa o tráfego D-STAR e publica telemetria para a camada web.</p>
            <small>UART 115200 · MQTT JSON</small>
          </div>
          <div>
            <RadioTower />
            <b>DStarGateway</b>
            <p>Interliga o hotspot à rede D-STAR, reflectores e serviços de gateway.</p>
            <small>F4FXL v0.7 · REF / XRF / DCS / XLX</small>
          </div>
          <div>
            <Database />
            <b>Collector + Dados</b>
            <p>Consolida eventos, QSOs, BER, RSSI, slow text, qualidade de rede e histórico operacional.</p>
            <small>Mosquitto · SQLite/WAL · CSV</small>
          </div>
          <div>
            <Monitor />
            <b>API + Dashboard</b>
            <p>Dashboard, qualidade do reflector, Statistics, Diagnostics, Settings, Updates e About em uma interface local.</p>
            <small>FastAPI · React/Vite · Nginx</small>
          </div>
          <div>
            <RefreshCw />
            <b>Updates + Rollback</b>
            <p>Atualização por GitHub Releases com SHA-256, backup, health check e rollback local.</p>
            <small>Até 5 pontos de retorno</small>
          </div>
        </div>
      </Panel>

      <div className="about-bottom">
        <Panel title="Versões validadas">
          <table className="data-table">
            <thead>
              <tr><th>COMPONENTE</th><th>VERSÃO</th><th>DETALHES</th></tr>
            </thead>
            <tbody>
              <tr><td>PP5CI Hotspot</td><td><b>v0.2.14</b></td><td>Release estável</td></tr>
              <tr><td>Sistema Operacional</td><td><b>Ubuntu 26.04.1 LTS</b></td><td>Linux x86_64</td></tr>
              <tr><td>MMDVM Modem</td><td><b>v1.5.2</b></td><td>Dual ADF7021 / CA6JAU</td></tr>
              <tr><td>MMDVMHost</td><td><b>590c531</b></td><td>Build Polar validado</td></tr>
              <tr><td>DStarGateway</td><td><b>v0.7</b></td><td>commit 0c1dbb5</td></tr>
              <tr><td>Interface USB</td><td><b>CH340</b></td><td>/dev/serial/by-id</td></tr>
            </tbody>
          </table>
        </Panel>

        <div className="about-center">
          <Panel title="Operação da v0.2.14">
            <div className="about-facts">
              <p><b>Atualizações</b><span>GitHub Releases privadas, artefato + SHA-256 e instalação transacional.</span></p>
              <p><b>Proteção do RF</b><span>Updates reiniciam API e collector; MMDVMHost e DStarGateway são apenas verificados.</span></p>
              <p><b>Qualidade de rede</b><span>Sonda TCP sem ICMP, baseline de Internet e classificação por faixas de RTT com ajuda contextual para rotas nacionais e internacionais.</span></p>
              <p><b>Hosts D-STAR</b><span>Sincronização automática diária às 03:00 America/Sao_Paulo.</span></p>
              <p><b>Persistência</b><span>Configurações em /etc/pp5ci-hotspot e banco operacional preservados em update/rollback.</span></p>
            </div>
          </Panel>

          <Panel title="Repositório e serviços">
            <div className="repo-card">
              <Code2 size={48} />
              <div>
                <small>Código fonte e releases</small>
                <strong>pp5ci-hotspot</strong>
                <span>cleziotc/pp5ci-hotspot · stable v0.2.14</span>
              </div>
            </div>
            <div className="directory-grid about-directory-grid">
              <code>/opt/pp5ci-hotspot</code>
              <code>/etc/pp5ci-hotspot</code>
              <code>/var/lib/pp5ci-hotspot</code>
              <code>pp5ci-hotspot-api.service</code>
              <code>pp5ci-hotspot-collector.service</code>
              <code>pp5ci-hotspot-hosts-update.timer</code>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}

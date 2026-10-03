# Guia do código

## Backend

Pacote: `backend/pp5ci_hotspot/`

### `api.py`

Aplicação FastAPI principal. Registra routers, endpoints de status, estatísticas, transmissões e SSE.

### `config.py`

Lê `MMDVM-Host.ini` e `DStarGateway.cfg` e produz a configuração efetiva consumida pelo backend.

### `db.py`

Banco SQLite principal: transmissões, metadados, diretório CSV e agregações de estatísticas.

### `events.py`

Normaliza eventos MQTT do MMDVMHost e representa sessões RF→NET / NET→RF.

### `collector.py`

Processo residente que:

- consome MQTT;
- acompanha eventos do MMDVMHost;
- acompanha journal do DStarGateway;
- enriquece sessões;
- persiste transmissões;
- alimenta estado em tempo real.

### `system_state.py`

Snapshot de serviços, modem, link, reflector, MQTT e recursos do sistema.

### `settings_api.py`

Leitura e alteração controlada de Geral, MMDVMHost, DStarGateway, host files, CSV e preferências.

### `diagnostics_api.py`

Serviços, serial, firmware, UDP, disco, load, logs e checks de diagnóstico.

### `network_monitor.py`

Mede caminho de rede para reflector ou gateway D-STAR remoto. Usa sondas TCP, não ICMP.

### `network_db.py`

Persistência e consultas das amostras de RTT/jitter/perda e associação com destinos.

### `network_api.py`

Endpoints para métricas e histórico de qualidade da rede.

### `updates_api.py`

Consulta GitHub Releases do repositório público, informa compatibilidade e aciona update/rollback via helper.

### `admin.py`

Validação da senha administrativa e ponte restrita para o helper root.

## Scripts privilegiados

### `scripts/pp5ci-hotspot-admin.py`

Único helper administrativo geral. Valida payload, paths, frequências, módulos, endereços e lista de serviços antes de qualquer alteração privilegiada.

### `scripts/pp5ci-hotspot-updater.py`

Motor de atualização transacional: download, SHA-256, extração segura, backup, swap, restart de camada web, health check e rollback.

### `scripts/install-common.sh`

Provisionamento completo compartilhado pelos instaladores VM e Raspberry Pi.

## Frontend

Aplicação React/Vite em `frontend/src/`.

### `api/client.ts`

Tipos e chamadas para status, statistics, diagnostics, settings e updates.

### `api/network.ts`

Cliente específico da API de qualidade de rede.

### `pages/DashboardPage.tsx`

Visão operacional principal: serviços, link, tráfego ao vivo, métricas e Last Heard.

### `pages/StatisticsPage.tsx`

KPIs e gráficos por período, reflector e chamada direta.

### `pages/SettingsPage.tsx`

Configuração protegida por senha administrativa.

### `pages/DiagnosticsPage.tsx`

Saúde do appliance, serial, firmware, portas, recursos e logs.

### `pages/UpdatesPage.tsx`

GitHub Releases, pipeline de update e rollbacks locais.

### `pages/AboutPage.tsx`

Informações de versão, arquitetura e projeto.

### `components/NetworkQualityPanel.tsx`

Apresentação das métricas de rede e estado de chamada direta/refletor.

## Configuração

`config/MMDVM-Host.ini.example` e `config/DStarGateway.cfg.example` usam placeholders preenchidos pelo instalador.

`config/web.env.example` define os paths e variáveis do backend.

`config/pp5ci-hotspot.sudoers` limita os comandos privilegiados.

## systemd

Os units em `systemd/` são a referência canônica. Código Python e helpers devem usar exatamente os mesmos nomes.

## Testes

`backend/tests/` cobre eventos, rede, settings, statistics, diagnostics, estado e updates.

O CI também compila frontend, valida shell/Python e bloqueia referências ao projeto privado anterior.

## Regra para contribuições

Ao adicionar funcionalidade:

1. não codifique indicativo, QTH, IP ou frequência de uma estação específica;
2. não inclua segredos;
3. mantenha paths sob o namespace `pp5ci-hotspot`;
4. não reinicie RF por mudanças apenas de dashboard/API;
5. adicione ou ajuste testes;
6. atualize `CHANGELOG.md` e a nota de release;
7. mantenha créditos upstream quando tocar código de terceiros.

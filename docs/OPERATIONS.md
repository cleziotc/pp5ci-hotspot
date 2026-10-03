# Operação e manutenção — PP5CI Hotspot

## Serviços principais

```bash
systemctl status pp5ci-hotspot-mmdvmhost.service
systemctl status pp5ci-hotspot-dstargateway.service
systemctl status pp5ci-hotspot-collector.service
systemctl status pp5ci-hotspot-api.service
systemctl status mosquitto.service
systemctl status nginx.service
```

## Logs

```bash
journalctl -u pp5ci-hotspot-mmdvmhost.service -f
journalctl -u pp5ci-hotspot-dstargateway.service -f
journalctl -u pp5ci-hotspot-collector.service -f
journalctl -u pp5ci-hotspot-api.service -f
```

## Cadeia RF

O MMDVMHost e o DStarGateway formam a cadeia operacional RF. Alterações de frontend, documentação ou API não justificam reiniciar esses serviços.

PIDs e estado podem ser conferidos com:

```bash
systemctl show pp5ci-hotspot-mmdvmhost.service pp5ci-hotspot-dstargateway.service \
  -p Id -p MainPID -p ActiveState -p SubState --no-pager
```

## API

```bash
curl -fsS http://127.0.0.1:8080/api/v1/health
curl -fsS http://127.0.0.1:8080/api/v1/status
curl -fsS http://127.0.0.1:8080/api/v1/diagnostics
```

## Banco

Banco padrão:

```text
/var/lib/pp5ci-hotspot/pp5ci-hotspot.db
```

SQLite opera em WAL. Backups devem incluir banco e arquivos WAL/SHM de forma consistente ou usar backup SQLite apropriado.

## Configuração

```text
/etc/pp5ci-hotspot/MMDVM-Host.ini
/etc/pp5ci-hotspot/DStarGateway.cfg
/etc/pp5ci-hotspot/RSSI.dat
/etc/pp5ci-hotspot/web.env
/etc/pp5ci-hotspot/admin-token
```

O `admin-token` não deve ser exibido em logs, screenshots ou respostas da API.

## Frontend

Build:

```bash
cd frontend
npm ci
npm run build
```

Publicação:

```text
/var/www/pp5ci-hotspot/
```

Uma publicação de frontend não requer reinício de MMDVMHost/DStarGateway.

## Hosts D-Star

Timer:

```text
pp5ci-hotspot-hosts-update.timer
```

Agenda oficial:

```text
03:00 America/Sao_Paulo
```

Arquivos:

```text
/usr/local/share/dstargateway.d/
```

## Backups antes de alteração

Antes de substituir backend ou frontend em produção, criar backup timestampado em `/root`.

Mudanças de configuração RF exigem backup do arquivo anterior e validação após aplicação.

## Diagnóstico seguro

- **Serial Check**: valida dispositivo/configuração; não transmite RF.
- **D-Star Path Check**: valida serviços e portas UDP locais; não transmite RF.
- Reinícios administrativos são ações separadas e explícitas.

## Rollback

A base 0.1.0 permanece a referência RF conhecida. Rollback de camada web não deve apagar:

- `/etc/pp5ci-hotspot/`;
- `/var/lib/pp5ci-hotspot/`;
- base CSV;
- host files válidos;
- configuração do MMDVMHost/DStarGateway.


## Updates transacionais

A página Updates usa GitHub Releases oficiais e o motor:

```text
/usr/local/libexec/pp5ci-hotspot-updater
```

O fluxo é:

```text
Download → Preparação → Backup → Instalação → Reinício → Health check
```

Regras operacionais:

- o artefato e o arquivo `.sha256` são baixados da release privada autenticada;
- o SHA-256 é conferido antes da extração;
- o tarball rejeita caminhos inseguros, devices e links;
- somente a camada web é substituída;
- apenas `pp5ci-hotspot-collector.service` e `pp5ci-hotspot-api.service` são reiniciados;
- MMDVMHost e DStarGateway não são reiniciados pelo updater;
- `/etc/pp5ci-hotspot/` e o banco operacional em `/var/lib/pp5ci-hotspot/` são preservados;
- falha de instalação ou health check restaura automaticamente o backup anterior;
- até cinco backups locais são mantidos em `/var/lib/pp5ci-hotspot/releases/`.

Estado e histórico:

```text
/var/lib/pp5ci-hotspot/update-status.json
/var/lib/pp5ci-hotspot/update-history.json
```

O token GitHub somente de leitura permanece em:

```text
/etc/pp5ci-hotspot/github-token
```

Nunca exibir o conteúdo desse arquivo em logs ou na interface.

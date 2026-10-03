# Arquitetura — PP5CI Hotspot 0.2.x

## 1. Princípio

A arquitetura mantém a base RF 0.1.0 como camada independente e validada. A camada web observa, armazena e administra o sistema sem substituir MMDVMHost ou DStarGateway.

```text
                    RF
Rádio D-Star ↔ MMDVM_HS Dual Hat
                    ↕ UART 115200 / CH340
                 MMDVMHost
                    ↕ UDP local
               DStarGateway
                    ↕ Internet
                Reflectores
```

A camada de observabilidade é paralela:

```text
MMDVMHost
  ├─ journald ───────────────────────────────┐
  └─ MQTT JSON → Mosquitto → Collector ─────┤
                                            ↓
                                        SQLite/WAL
                                            ↓
                                         FastAPI
                                            ↓
                                          Nginx
                                            ↓
                                      React / Vite
```

## 2. Base RF

| Componente | Referência validada |
| --- | --- |
| Firmware | MMDVM_HS_Dual_Hat-v1.5.2, GitID #89daa20 |
| MMDVMHost | `590c531391dfd3146073afbc3956f70d42c62a46` + patch Polar RSSI |
| DStarGateway | F4FXL v0.7, `0c1dbb5` |
| Serial | CH340, USB ID `1a86:7523` |
| UART | 115200 8N1 |
| Modo | D-Star simplex |
| Gateway UDP | `127.0.0.1:20010` |
| Host UDP | `127.0.0.1:20011` |

A serial configurada usa `/dev/serial/by-id/` e é resolvida para `/dev/ttyUSB*` apenas para diagnóstico.

## 3. Serviços

### pp5ci-hotspot-mmdvmhost.service

Executa MMDVMHost. É parte da cadeia RF e não deve ser reiniciado por operações de leitura.

### pp5ci-hotspot-dstargateway.service

Executa DStarGateway. O estado atual do reflector é obtido de `/tmp/Links.log`.

### mosquitto.service

Broker MQTT local em `127.0.0.1:1883`.

### pp5ci-hotspot-collector.service

Assina os eventos MQTT do MMDVMHost, enriquece eventos com journald quando necessário e grava estado/histórico no SQLite.

### pp5ci-hotspot-api.service

FastAPI local em `127.0.0.1:8080`. É a única fonte consumida pelo frontend para dados operacionais.

### pp5ci-hotspot-hosts-update.timer

Atualiza host files D-Star diariamente às 03:00 `America/Sao_Paulo`.

### nginx.service

Serve o frontend estático e encaminha `/api/` para a API local.

## 4. Persistência

Banco padrão:

```text
/var/lib/pp5ci-hotspot/pp5ci-hotspot.db
```

Tabelas principais:

- `transmissions`: QSOs concluídos;
- `runtime_state`: estado atual do tráfego;
- `metadata`: timestamps, reflector e estado auxiliar;
- `callsign_directory`: base CSV importada.

SQLite usa WAL e `busy_timeout`.

## 5. Fontes de verdade

### Tráfego

MQTT do MMDVMHost + journald para complementos como URCALL e slow text.

### Reflector

`/tmp/Links.log` do DStarGateway. Arquivo existente e vazio significa unlinked.

### Configuração

```text
/etc/pp5ci-hotspot/MMDVM-Host.ini
/etc/pp5ci-hotspot/DStarGateway.cfg
/etc/pp5ci-hotspot/RSSI.dat
/etc/pp5ci-hotspot/web.env
```

### Hosts

```text
/usr/local/share/dstargateway.d/
```

### Usuários

CSV importado e normalizado para `callsign_directory`.

## 6. Frontend

Frontend React/Vite publicado em:

```text
/var/www/pp5ci-hotspot/
```

Páginas:

- Dashboard;
- Statistics;
- Diagnostics;
- Settings;
- Updates;
- About.

O contrato visual fica em `docs/UI_CONTRACT.md`.

## 7. Administração

Ações de escrita exigem token local em:

```text
/etc/pp5ci-hotspot/admin-token
```

O navegador mantém apenas a sessão administrativa temporária. O token não é retornado por endpoints.

Operações privilegiadas são delegadas a:

```text
/usr/local/sbin/pp5ci-hotspot-admin
/etc/sudoers.d/pp5ci-hotspot
```

O helper aceita apenas comandos explicitamente implementados.

## 8. Diagnostics

A Diagnostics combina:

- systemd;
- udev;
- `/proc/net/udp`;
- journald;
- configuração;
- SQLite.

Os checks de Serial e D-Star Path são deliberadamente não-RF.

## 9. Releases e Updates

GitHub Releases é a fonte planejada para versões disponíveis. Cada release deve ter:

- tag `vX.Y.Z`;
- release notes;
- `pp5ci-hotspot-vX.Y.Z.tar.gz`;
- `pp5ci-hotspot-vX.Y.Z.tar.gz.sha256`.

O processo está descrito em `docs/RELEASES.md`.

Para repositório privado, a API local usa uma credencial GitHub somente de leitura, armazenada apenas no appliance.

## 10. Regras de evolução

1. Não inventar telemetria.
2. Não reiniciar RF para alteração puramente web.
3. Fazer backup antes de substituição de arquivos de produção.
4. Preservar `/etc/pp5ci-hotspot` e `/var/lib/pp5ci-hotspot` em updates/rollback.
5. Validar CI antes de deploy.
6. Validar serviços e comportamento real após deploy.

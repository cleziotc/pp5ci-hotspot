# Contrato de dados e API — PP5CI Hotspot

Status: **0.2.x em implementação ativa**.

O frontend não lê systemd, logs, serial, banco ou arquivos diretamente. Toda informação operacional passa pela API local normalizada.

## 1. Convenções

Base:

```text
http://127.0.0.1:8080/api/v1/
```

Datas são ISO-8601 UTC quando persistidas. A apresentação usa o fuso configurado.

Valores indisponíveis devem ser `null`; o frontend apresenta `—`. Não é permitido fabricar zero ou estimativas.

## 2. Estado

### GET /api/v1/health

Saúde básica e versão da API.

### GET /api/v1/status

Estado operacional do hotspot:

- identificação;
- modem;
- serviços;
- rede;
- MQTT;
- tráfego atual;
- reflector;
- sistema.

### GET /api/v1/events

SSE para atualização rápida do estado de tráfego.

### GET /api/v1/network

Qualidade de rede atual em janela móvel de 60 s, sem dependência de ICMP:
- reflector ativo;
- host/IP resolvido;
- latência mediana;
- jitter RTT;
- perda de sondas;
- máximo RTT;
- estado BOA/ATENÇÃO/INSTÁVEL;
- baseline independente de Internet;
- última perda D-Star real quando disponível;
- protocolo e porta UDP do link D-Star quando publicados pelo Links.log.

A classificação de saúde usa limites conservadores para rotas internacionais: ATENÇÃO por RTT somente a partir de 400 ms e INSTÁVEL por RTT somente a partir de 650 ms. Jitter e perda têm prioridade diagnóstica.

### GET /api/v1/network/history

Histórico de até 168 h, com visualização padrão de 24 h e buckets de 10 minutos.

## 3. Tráfego e estatísticas

### GET /api/v1/transmissions

Parâmetro `limit` entre 1 e 500.

Retorna transmissões persistidas e enriquecidas pela base de indicativos.

### GET /api/v1/statistics

Retorna:

- today;
- last 24 h;
- last 7 d;
- last 30 d;
- séries horárias e diárias;
- split RF→NET / NET→RF;
- peak hour;
- duração média;
- cobertura da base CSV;
- top stations.

## 4. Settings

### GET /api/v1/settings

Retorna configuração efetiva de Geral, MMDVMHost, DStarGateway, Hosts, Users e Dashboard.

### POST /api/v1/settings/admin/check

Valida a senha administrativa enviada no header sem retornar a credencial.

### POST /api/v1/settings/apply/{section}

Protegido por admin. Valida e aplica alterações permitidas.

### GET /api/v1/settings/reflectors

Pesquisa reflectores nos host files ativos.

### POST /api/v1/settings/hosts/update

Protegido por admin. Atualiza os host files.

### POST /api/v1/settings/users/import

Protegido por admin. Faz upload, validação, staging e troca atômica da base CSV.

## 5. Diagnostics

### GET /api/v1/diagnostics

Retorna:

- serviços e PIDs;
- timer;
- serial e firmware;
- portas UDP;
- BER/RSSI;
- Last activity;
- contagem de QSOs;
- disco/load;
- últimos checks;
- logs recentes.

### POST /api/v1/diagnostics/serial-check

Check seguro do dispositivo/configuração serial. Não transmite RF.

### POST /api/v1/diagnostics/dstar-check

Check seguro do caminho local MMDVMHost ↔ DStarGateway. Não injeta áudio e não aciona PTT.

### POST /api/v1/diagnostics/restart/{target}

Protegido por admin. Reinicia apenas o serviço solicitado.

### GET /api/v1/diagnostics/logs/export

Protegido por admin. Exporta o recorte de logs.

## 6. Updates

### GET /api/v1/updates/status

Deve informar:

- versão instalada;
- última release oficial;
- update disponível;
- estado do GitHub;
- release notes;
- assets;
- presença de SHA-256;
- compatibilidade;
- capacidade de instalar/rollback.

### GET /api/v1/updates/operation

Estado local da operação transacional: estado, etapa, progresso, mensagem, versões de origem/destino, backup e erro.

### GET /api/v1/updates/history

Histórico local real de updates e rollbacks. Nunca retorna linhas fictícias.

### GET /api/v1/updates/rollback-options

Lista apenas os cinco backups locais realmente existentes e expõe um identificador controlado, nunca um caminho arbitrário.

### POST /api/v1/updates/install

Protegido por admin. O backend seleciona a última release estável validada; o cliente não fornece URL de download. O helper privilegiado inicia o updater em unidade systemd transitória.

### POST /api/v1/updates/rollback

Protegido por admin. Aceita somente um identificador de backup previamente listado. Cria um ponto de retorno antes do rollback e executa health check.

O updater executa:

```text
download → SHA-256 → preparação → backup → instalação → reinício web → health check
```

A atualização não reinicia MMDVMHost nem DStarGateway; esses serviços são apenas verificados no health check. Configuração e banco permanecem preservados.

## 7. GitHub público e autenticação administrativa

A API usa:

```text
PP5CI_HOTSPOT_GITHUB_REPOSITORY=cleziotc/pp5ci-hotspot
```

Releases públicas são consultadas sem token GitHub.

Operações administrativas usam a senha criada no instalador, enviada no header:

```text
X-PP5CI-Hotspot-Admin-Password
```

A senha original não é armazenada pelo backend; apenas o hash PBKDF2-SHA256 é persistido em `/etc/pp5ci-hotspot/admin-password.json`.

## 8. Persistência e integridade

O banco guarda estado operacional, transmissões e amostras de qualidade de rede. Segredos não são armazenados no SQLite.

Escritas administrativas devem seguir:

```text
validar → backup → escrever em staging → substituir atomicamente → health check
```

Se a operação falhar, o último estado válido deve permanecer ativo.

## 9. Segurança operacional

- Monitoramento funciona sem admin.
- Escrita exige admin.
- Abertura da página não transmite RF.
- Reinício de MMDVMHost/DStarGateway é explícito.
- Updates não podem apagar `/etc/pp5ci-hotspot` nem `/var/lib/pp5ci-hotspot`.


## Filtros por reflector (0.2.8)

### GET /api/v1/statistics?reflector=<REFLECTOR>

Quando `reflector` é informado, os totais de hoje, 24 h, 7 d, 30 d, séries, direção, horário de pico, duração média e Top Stations são calculados somente para esse reflector.

A resposta inclui:
- `scope.reflector`;
- `scope.label`;
- `available_reflectors`;
- `reflector_usage_30d` com visão geral global de transmissões e airtime.

Sem o parâmetro, o endpoint mantém a visão consolidada de todos os reflectores.

### GET /api/v1/transmissions?limit=N&reflector=<REFLECTOR>

Filtra o Last Heard pelo reflector solicitado.

### GET /api/v1/network/history?hours=N&reflector=<REFLECTOR>

Permite consultar o histórico de qualidade de rede de um reflector específico, quando houver amostras persistidas.


## Classificação de qualidade de rede (0.2.9)

O campo `state` da qualidade de rede usa a pior condição entre RTT, jitter e perda.

Faixas de RTT:
- `good`: até 100 ms;
- `degraded`: acima de 100 ms até 260 ms;
- `poor`: acima de 260 ms.

Jitter:
- `degraded` a partir de 40 ms;
- `poor` a partir de 100 ms.

Perda:
- `degraded` a partir de 1%;
- `poor` a partir de 5%.

A API não altera nem normaliza o RTT medido; apenas classifica o resultado.


## Atribuição de reflector por QSO (0.2.11)

O collector deve persistir um reflector canônico no formato `REF123 A`, `XLX300 D`, etc.

- Quando o evento MQTT D-Star fornece reflector, ele é normalizado.
- Quando o evento RF fornece reflector vazio, o reflector ativo é obtido de `/tmp/Links.log`.
- Filtros aceitam variantes com ou sem espaço antes do módulo.
- Na inicialização da API, transmissões históricas sem reflector podem ser recuperadas a partir de uma amostra `network_samples` próxima no tempo, dentro de uma janela curta.
- Registros já associados nunca são sobrescritos por esse reparo.


## Callsign Routing (0.2.12)

### Estado ao vivo

`/api/v1/status` e SSE passam a expor em `traffic`:
- `route_type`: `reflector`, `callsign` ou `local`;
- `contact_callsign`: indicativo remoto quando a sessão usa Callsign Routing.

`link.callsign_routing` expõe a configuração efetiva de ircDDB:
- `enabled`;
- `hostname`;
- `username`.

### Persistência

A tabela `transmissions` recebe de forma aditiva:
- `route_type TEXT`;
- `contact_callsign TEXT`.

Chamadas diretas não recebem `reflector`. Isso impede que um QSO via ircDDB seja somado ao reflector que eventualmente continue linkado no hotspot.

### Filtros

`GET /api/v1/statistics?callsign=PY2ABC` retorna exclusivamente os QSOs diretos com aquele contato.

`GET /api/v1/transmissions?callsign=PY2ABC` filtra o Last Heard pelo mesmo contato.

A resposta de statistics passa a incluir:
- `scope.type`;
- `scope.callsign`;
- `available_callsigns`;
- `callsign_usage_30d`.

### Migração ircDDB

Na primeira inicialização da v0.2.12, a API chama um helper administrativo restrito para configurar `ircv4.openquad.net`, sincronizar o usuário com o callsign do gateway e reiniciar somente o DStarGateway quando a configuração realmente muda.


## Live Callsign Target Enrichment (0.2.13)

O collector acompanha simultaneamente:
- `pp5ci-hotspot-mmdvmhost.service`;
- `pp5ci-hotspot-dstargateway.service`.

Quando o DStarGateway registra a linha nativa:

`<MYCALL> is trying to G2 route to callsign <URCALL>`

o EventProcessor enriquece a sessão RF ativa com:
- `destination=<URCALL>`;
- `route_type=callsign`;
- `contact_callsign=<URCALL>`;
- `reflector=null`.

Essa atualização é persistida em `runtime_state` e publicada imediatamente pelo SSE de `/api/v1/events`. O mecanismo também aceita o evento G2 antes do MQTT start, mantendo-o temporariamente no buffer de enriquecimento.


## Alvo dinâmico de qualidade de rede (0.2.14)

O endpoint `GET /api/v1/network` passa a fornecer:

- `active_target`: destino atualmente monitorado;
- `reflector`: resumo do reflector conectado;
- `direct`: resumo do último gateway de Callsign Routing;
- `direct_hold_seconds`: período de retenção do alvo direto, padrão 60 s.

`active_target.target_type` pode ser:
- `reflector`;
- `callsign`.

Quando `target_type=callsign`, o objeto inclui `callsign`, `host/ip`, amostras, latência, jitter e perda da sonda TCP.

### Descoberta do IP direto

Com `logIRCDDBTraffic=true`, o DStarGateway publica linhas no formato nativo `USER: ... <IPv4>`. O collector mantém um cache em memória por indicativo e usa esse endereço como gateway remoto do Callsign Routing.

### Retenção e prioridade

1. Sessão ativa `route_type=callsign`: alvo direto.
2. Após encerrar, o alvo direto continua sendo sondado por 60 s.
3. Sessão ativa que não seja callsign cancela imediatamente a retenção direta.
4. Expirado o período, o monitor volta ao reflector.
5. Uma nova sessão direta substitui o contato anterior e reinicia o temporizador.

A tabela `network_samples` recebe o campo aditivo `callsign` e usa `target=direct` para essas amostras.

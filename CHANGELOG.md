# Changelog

Todas as mudanças relevantes do PP5CI Hotspot são registradas aqui.

O projeto segue versionamento semântico `MAJOR.MINOR.PATCH`.

## [0.3.0] - 2026-10-03

### Projeto público independente

- Publicado como `cleziotc/pp5ci-hotspot`, sem dependência do repositório privado anterior.
- Namespace Python alterado para `pp5ci_hotspot`.
- Paths de instalação alterados para `/opt/pp5ci-hotspot`, `/etc/pp5ci-hotspot`, `/var/lib/pp5ci-hotspot` e `/var/www/pp5ci-hotspot`.
- Serviços systemd padronizados em `pp5ci-hotspot-*`.
- Updater passa a consultar somente GitHub Releases do repositório público `cleziotc/pp5ci-hotspot`.
- Nenhum token GitHub é necessário para descobrir ou baixar releases públicas.

### Instalação

- Novo `install-vm.sh` para Ubuntu/Debian com MMDVM em serial/USB.
- Novo `install-rpi.sh` para Raspberry Pi com MMDVM via UART GPIO `/dev/serial0`.
- Instalador solicita o indicativo do operador.
- Instalador solicita frequência inicial.
- Instalador solicita criação e confirmação da senha de administrador.
- Senha administrativa é armazenada somente como PBKDF2-HMAC-SHA256 + salt.
- Instalação passa a provisionar cadeia RF, backend, frontend, Mosquitto, Nginx, serviços e updater em uma única execução.

### Administração

- Settings e Updates usam senha de administrador em vez de token local aleatório.
- A senha não é persistida pelo frontend em localStorage/sessionStorage.
- Header administrativo público: `X-PP5CI-Hotspot-Admin-Password`.

### Raspberry Pi

- Habilitação automática de `enable_uart=1`.
- Remoção controlada de console serial de `cmdline.txt`.
- Uso do alias `/dev/serial0`.
- Documentação de GPIO14/TXD, GPIO15/RXD e GND.

### Documentação e créditos

- README público detalhado.
- Documentação de instalação, Raspberry Pi, segurança, código, arquitetura, API, interface e operação.
- Créditos explícitos a G4KLX, F4FXL/KC3FRA, N7TAE, CA6JAU e projetos upstream.
- CI bloqueia a reintrodução de nomes/paths do projeto privado anterior.

### Compatibilidade funcional

- Mantida a linha funcional 0.2.14: Callsign Routing, estatísticas por reflector/indicativo, qualidade de rede direta, diagnostics, settings e updates transacionais.
- Exemplos públicos usam indicativos genéricos; nenhum indicativo de estação é usado como configuração fixa.

## [0.2.14] - 2026-10-03

### Adicionado

- O card **Qualidade da Rede** passa a acompanhar dinamicamente o destino de rede realmente usado pelo D-STAR.
- Em Callsign Routing, o Polar usa o endereço IPv4 do gateway D-STAR remoto resolvido pelo ircDDB para o indicativo.
- O DStarGateway passa a fornecer ao collector seus registros nativos `USER:`, que contêm indicativo e endereço IPv4 do gateway remoto.
- A sonda direta usa TCP contra o IP remoto, priorizando as portas 40000, 443, 80 e 22, sem depender de ICMP.
- O card muda o título para **Qualidade da Rede (Chamada Direta)** e mostra o indicativo e IP do gateway remoto.

### Regra de seleção do alvo

- Durante uma chamada direta, o alvo de medição passa imediatamente para o gateway remoto do indicativo.
- Após o fim da chamada direta, esse alvo permanece ativo por **60 segundos**.
- Uma nova chamada direta renova o período de 60 segundos e pode trocar o indicativo/IP monitorado.
- Qualquer tráfego de reflector RF → NET ou NET → RF cancela imediatamente a retenção da chamada direta e devolve a medição ao reflector.
- Se o período de 60 segundos expirar sem novo tráfego direto, a medição retorna ao reflector conectado.
- Chamadas diretas recebidas seguem a mesma lógica usando o indicativo remoto e o endereço aprendido pelo ircDDB.

### Modelo de dados

- `network_samples` recebe de forma aditiva o campo `callsign` para separar amostras de gateways diretos por indicativo.
- `/api/v1/network` passa a expor `active_target`, `direct` e `direct_hold_seconds`.
- O histórico do reflector continua preservado e separado das amostras diretas.

### Precisão da interpretação

- O IP exibido em Callsign Routing é o **gateway D-STAR remoto** escolhido pelo ircDDB/G2 para alcançar o indicativo.
- Ele não representa necessariamente o IP do rádio, hotspot ou equipamento pessoal do operador.
- A medição continua sendo uma sonda TCP de caminho, e não RTT do áudio UDP D-STAR em si.

### Migração

- Novas instalações habilitam `logIRCDDBTraffic=true` no DStarGateway.
- Instalações existentes recebem essa opção automaticamente por uma migração idempotente da v0.2.14.
- O DStarGateway só é reiniciado quando a configuração realmente precisa ser alterada.

### Segurança operacional

- Nenhuma alteração na cadeia RF, vocoder ou MMDVMHost.
- O collector apenas lê os registros nativos do DStarGateway e executa sondas TCP.
- Nenhum pacote D-STAR adicional é transmitido para realizar a medição.
- ICMP/ping continua não sendo necessário.

## [0.2.13] - 2026-10-03

### Corrigido

- Corrigida a identificação do destino no **Tráfego ao Vivo** durante chamadas diretas D-STAR por Callsign Routing.
- O collector passa a acompanhar também o journal do `pp5ci-hotspot-dstargateway.service`, além do MMDVMHost.
- O log nativo do DStarGateway `<MYCALL> is trying to G2 route to callsign <URCALL>` passa a ser usado como fonte autoritativa para o destino direto.
- Quando o MMDVMHost reporta inicialmente `CQCQCQ` ou mantém o reflector ativo como contexto, o evento do DStarGateway corrige imediatamente a sessão para `route_type=callsign`.
- O nó da antena no Live Traffic passa a mostrar o indicativo remoto, por exemplo **PY2ABC**, com o rótulo **Destino direto**.
- A linha inferior passa a refletir `ircDDB / QuadNet` em vez do reflector durante a chamada direta.

### Estatísticas

- A mesma correção alimenta `contact_callsign` antes do encerramento do QSO.
- O QSO direto é persistido sob o indicativo correto e continua separado das estatísticas do reflector que permanecer linkado.
- A correção funciona tanto quando o log G2 chega antes quanto depois do evento MQTT de início da transmissão.

### Segurança operacional

- Nenhuma alteração em RF, vocoder, modem ou protocolo de áudio.
- Nenhuma alteração na configuração ircDDB introduzida na v0.2.12.
- O collector apenas lê journald; não envia comandos ao DStarGateway.
- O MMDVMHost permanece inalterado.

## [0.2.12] - 2026-10-03

### Adicionado

- Callsign Routing D-STAR via **ircDDB / QuadNet**.
- Servidor padrão: `ircv4.openquad.net`.
- O usuário ircDDB é sincronizado com o indicativo do hotspot e a senha permanece vazia.
- Migração automática e controlada habilita ircDDB em instalações existentes na primeira inicialização da v0.2.12.
- Settings → DStarGateway recebe controles de Callsign Routing, servidor e usuário.
- O card DStarGateway do Dashboard informa `ircDDB ON/OFF`.
- Live Traffic identifica chamadas diretas como **CALLSIGN ROUTING**, mostra o indicativo de destino e `ircDDB / QuadNet`.
- Banco SQLite passa a persistir `route_type` e `contact_callsign` por transmissão.
- Statistics recebe escopo por chamada direta, com seleção de indicativo e atalho para a chamada atual.
- Novo painel **Chamadas Diretas · Últimos 30 Dias · por indicativo**.
- Last Heard Estendido mostra a rota de cada transmissão.

### Estatísticas de chamadas diretas

- Uma chamada RF → NET para `PY2ABC` é registrada como rota `callsign`, contato `PY2ABC`.
- Uma chamada NET → RF recebida de `PY2ABC` também é agrupada sob contato `PY2ABC`.
- QSOs diretos não são contabilizados como tráfego de reflector, mesmo quando o hotspot permanece linkado a um reflector.
- O Dashboard muda temporariamente o Resumo de Hoje e Airtime para **Direto · <CALLSIGN>** enquanto a chamada direta está ativa.
- A visão `Todos os destinos` inclui reflectores e chamadas diretas; filtros específicos permanecem separados.

### Configuração

- Novas instalações já recebem:
  - `[ircddb_1] enabled=true`
  - `hostname=ircv4.openquad.net`
  - `username=<CALLSIGN>`
  - `password=`
- Em atualização, um helper root restrito aplica somente essa migração e reinicia apenas o DStarGateway quando necessário.

### Segurança operacional

- A cadeia MMDVMHost não é alterada.
- O helper de migração é explicitamente autorizado no sudoers e não aceita comandos arbitrários.
- Alterações de DStarGateway são feitas com backup e escrita atômica.
- O esquema SQLite é migrado de forma aditiva e preserva todo o histórico existente.

## [0.2.11] - 2026-10-03

### Corrigido

- Corrigido o Resumo de Hoje e o Airtime por reflector no Dashboard, que podiam permanecer em zero mesmo com QSOs registrados.
- Sessões RF → NET passam a herdar o reflector ativo diretamente de /tmp/Links.log quando o MMDVMHost publica o campo reflector vazio.
- Sessões NET → RF também usam o reflector ativo do gateway como referência autoritativa quando disponível.
- Identificadores como XLX300D e XLX300 D passam a ser tratados como o mesmo reflector.
- Filtros de Statistics e Last Heard por reflector toleram diferenças de espaçamento no identificador.

### Recuperação de histórico recente

- QSOs antigos sem reflector são recuperados automaticamente usando as amostras de network_samples já coletadas pela sonda do reflector.
- A recuperação só associa um QSO quando existe uma amostra de reflector próxima no tempo, evitando atribuição arbitrária ao reflector atual.
- Registros já associados a um reflector não são alterados.

### Segurança operacional

- Nenhuma alteração em RF, MMDVMHost ou DStarGateway.
- A correção atua somente na atribuição/persistência do reflector e nas consultas estatísticas.
- Banco existente é preservado; o reparo é idempotente.

## [0.2.10] - 2026-10-03

### Alterado

- Barras de latência do painel Qualidade da Rede passam a usar gradiente real por faixa de RTT.
- O gradiente é calculado individualmente para cada barra, de acordo com o RTT representado.
- Até 100 ms a barra permanece em tons de verde.
- Entre 101 e 260 ms, a porção correspondente acima de 100 ms transiciona progressivamente para amarelo.
- Acima de 260 ms, somente a parte da barra que ultrapassa esse limite evolui para laranja/vermelho.
- Perda total de sonda continua sendo exibida como vermelho sólido.

### Explicação visual

- O gradiente não é decorativo: sua posição corresponde às faixas reais de RTT.
- Uma barra de 80 ms aparece somente verde.
- Uma barra de 250 ms mostra verde na base e amarelo no topo.
- Uma barra acima de 260 ms adiciona a faixa vermelha no trecho superior.

### Segurança operacional

- Nenhuma mudança nos cálculos de RTT, jitter, perda ou classificação.
- Nenhuma alteração na cadeia RF, MMDVMHost ou DStarGateway.

## [0.2.9] - 2026-10-03

### Alterado

- Classificação de latência do reflector passa a usar três faixas explícitas:
  - 0–100 ms: verde / BOA;
  - 101–260 ms: amarelo / ATENÇÃO;
  - acima de 260 ms: vermelho / RUIM.
- A faixa 101–260 ms informa que a latência pode ser normal quando o reflector está hospedado em outro país.
- Jitter e perda continuam podendo piorar o estado mesmo com RTT baixo.
- Barras do gráfico de 60 segundos e mini-barras do card superior seguem as mesmas cores de RTT.
- O valor e o sparkline de Latência também acompanham a faixa atual.

### Adicionado

- Faixa de diagnóstico textual no painel Qualidade da Rede, explicando o estado atual.
- Pop-up funcional no ícone “i”, com explicação das três faixas, jitter, perda e uso de sonda TCP sem ICMP.
- Botão de fechar e suporte a teclado/foco no pop-up.

### Corrigido

- O ícone de informação do painel Qualidade da Rede deixa de ser apenas decorativo e passa a responder ao clique.

### Segurança operacional

- A mudança altera apenas classificação e apresentação das métricas.
- A medição RTT continua real e não é compensada artificialmente.
- Nenhuma alteração na cadeia RF, MMDVMHost ou DStarGateway.

## [0.2.8] - 2026-10-03

### Adicionado

- Dashboard passa a calcular **Resumo de Hoje** no contexto do reflector atualmente conectado.
- O título do resumo informa explicitamente o reflector atual.
- Ao trocar de reflector, o Dashboard carrega imediatamente os totais de hoje daquele reflector; se ainda não houve tráfego nele, os valores começam em zero.
- Ao retornar a um reflector já utilizado no mesmo dia, seus totais anteriores são recuperados.
- Statistics recebe seletor de escopo: **Todos os reflectores** ou um reflector específico.
- Botão rápido **Reflector atual** aplica o reflector conectado ao filtro de Statistics.
- KPIs, gráficos de 7/30 dias, atividade 24 h, direção, horário de pico, duração média, Top Stations e Last Heard obedecem ao filtro selecionado.
- Histórico de rede pode ser consultado para o reflector selecionado.
- Novo gráfico **Uso por Reflector · Últimos 30 Dias · Visão Geral**, com QSOs e airtime por reflector.

### Preservação de histórico

- Trocar de reflector não apaga nem reinicia o histórico persistente.
- O Dashboard muda apenas o escopo da consulta; os dados continuam no SQLite.
- A visão geral por reflector permanece global para permitir comparação entre reflectores.

### Segurança operacional

- Alteração exclusivamente de consulta, agregação e interface.
- Nenhuma mudança em RF, MMDVMHost, DStarGateway, BER, RSSI, LOSS ou sonda de rede.
- MMDVMHost e DStarGateway permanecem preservados durante updates.

## [0.2.7] - 2026-10-03

### Corrigido

- Nome e localidade no Live Traffic deixam de depender das transmissões recentes já encerradas.
- O backend consulta a base de indicativos em tempo real assim que recebe o indicativo do QSO atual.
- Troca de reflector não afeta mais a exibição de nome/localidade da estação em tráfego ao vivo.
- O SSE e o endpoint /api/v1/status passam a entregar name e location junto ao estado da transmissão ativa.

### Compatibilidade

- O fallback pelas transmissões recentes foi mantido no frontend para compatibilidade.
- Indicativos ausentes da base continuam exibindo “—”, sem inventar dados.

### Segurança operacional

- Alteração apenas de enriquecimento de dados; nenhuma mudança na cadeia RF, BER, RSSI ou rede.
- MMDVMHost e DStarGateway permanecem preservados durante updates.

## [0.2.6] - 2026-10-03

### Adicionado

- Colunas **BER** e **LOSS** em Últimas Transmissões no Dashboard.
- As mesmas colunas foram adicionadas em Statistics → Last Heard · Estendido.
- BER é exibido apenas em transmissões RF → NET, usando o BER real armazenado pelo MMDVMHost.
- LOSS é exibido apenas em transmissões NET → RF, usando a perda real de pacotes da sessão.
- Valores não aplicáveis ou indisponíveis aparecem como “—”, sem fabricar 0%.
- Badges de qualidade usam verde, amarelo e vermelho para facilitar diagnóstico visual.

### Faixas visuais

- BER: verde até 1,0%; amarelo de 1,1% a 2,5%; vermelho acima de 2,5%.
- LOSS: verde até 0,5%; amarelo de 0,6% a 3,0%; vermelho acima de 3,0%.

### Segurança operacional

- Alteração somente de apresentação; nenhum cálculo RF ou de rede foi modificado.
- MMDVMHost e DStarGateway permanecem preservados durante updates.

## [0.2.5] - 2026-10-03

### Corrigido

- Gráfico de Qualidade da Rede passa a ocupar toda a largura temporal dos últimos 60 segundos.
- As barras usam slots temporais fixos, evitando concentração das amostras no lado esquerdo.
- A altura das barras foi recalibrada para maior presença visual: o maior RTT da janela fica próximo de 80–85% da área útil, preservando folga para picos.
- Slots ainda não preenchidos permanecem vazios e preservam a posição correta no eixo do tempo.

### Mantido

- Cálculos de latência, jitter RTT, perda e limites de classificação permanecem inalterados.
- Alertas do cronômetro em 2:00 e 2:30 permanecem ativos.
- BER/RSSI, estado do reflector e demais elementos da v0.2.4 permanecem sem alteração funcional.

## [0.2.4] - 2026-10-03

### Corrigido

- Qualidade da Rede passa a usar mini-barras proporcionais com folga vertical, evitando colunas permanentemente no topo quando o RTT é estável.
- Densidade padrão da sonda TCP aumentada de 5 s para 3 s para melhorar a leitura visual da janela de 60 segundos.
- Sparklines de latência, jitter RTT e perda passam a usar escala absoluta/conservadora, sem exagerar pequenas variações.
- BER e RSSI reorganizados para o layout aprovado: gráfico à esquerda, bloco Atual à direita e Mín/Máx/Média logo abaixo do valor atual.
- Gráficos BER/RSSI recebem grade vertical e horizontal; BER usa amarelo em trechos acima de 1%.
- Estado da Conexão com o Reflector passa a reproduzir o bloco aprovado em duas colunas, com divisor central.
- Metadados do link D-Star passam a expor protocolo e porta UDP do reflector quando disponíveis no Links.log.

### Adicionado

- Alerta visual no cronômetro de Duração:
  - a partir de 2:00, o badge de duração pisca em amarelo;
  - a partir de 2:30, o badge passa a piscar em vermelho.
- Porta/protocolo D-Star exibidos no Estado da Conexão com o Reflector.

### Segurança operacional

- Os alertas de duração são somente visuais e não interrompem transmissões.
- A sonda de rede continua sem ICMP e não transmite RF.
- MMDVMHost e DStarGateway continuam preservados durante updates.

## [0.2.3] - 2026-10-03

### Corrigido

- Dashboard ajustado para reproduzir com fidelidade o layout visual aprovado.
- BER e RSSI agora usam gráfico à esquerda e bloco de valor atual à direita, como no preview.
- Painel de qualidade de rede passa a exibir sparklines individuais para latência, jitter RTT e perda.
- Linha superior recebe mini-histograma no card Rede / Reflector.
- Cabeçalho e navegação alinhados ao preview, com rótulos em português.

### Alterado

- Classificação de saúde da rede ficou mais conservadora para reflectores hospedados fora do Brasil.
- Latências intercontinentais de aproximadamente 200–300 ms não geram mais alerta por si só.
- Estado ATENÇÃO por latência passa a partir de 400 ms; INSTÁVEL por latência a partir de 650 ms.
- Jitter e perda continuam com peso maior na classificação de qualidade.
- Barras de latência permanecem verdes abaixo de 400 ms, amarelas acima disso e vermelhas somente em perda de sonda.

### Segurança operacional

- A medição de RTT real não foi alterada nem artificialmente reduzida; somente a interpretação de saúde foi recalibrada.
- MMDVMHost e DStarGateway permanecem preservados durante a atualização.
- O monitor de rede continua sem transmitir RF e sem depender de ICMP.

## [0.2.2] - 2026-10-03

### Adicionado

- Monitor de qualidade de rede do reflector sem dependência de ICMP, usando sondas TCP.
- Métricas de latência, jitter e perda em janela móvel de 60 segundos.
- Baseline independente da Internet para diagnóstico comparativo.
- Histórico de 24 horas da qualidade de rede na página Statistics.
- Persistência das amostras de rede em SQLite/WAL com retenção automática.
- Card Rede / Reflector e painel de estado detalhado da conexão no Dashboard.

### Alterado

- Dashboard reorganizado conforme layout aprovado, com foco em tráfego ao vivo, RF e rede.
- Tráfego ao Vivo passa a exibir direção, fluxo Rádio → MMDVM → Gateway → Reflector, indicativo, nome, localização e slow text D-STAR em amarelo.
- BER e RSSI deixam de ser duplicados na janela de tráfego e continuam em painéis dedicados.
- Badge DV removido da janela de tráfego.
- Gráficos de 7 e 30 dias movidos do Dashboard para Statistics.
- Classificação da rede usa janela móvel e limites tolerantes a picos isolados.

### Segurança operacional

- Monitor de rede isolado dentro do collector; falhas de telemetria não interrompem o tráfego D-STAR.
- Update continua reiniciando somente API e collector, preservando MMDVMHost e DStarGateway.
- Configuração e banco operacional continuam preservados pelo mecanismo transacional de update/rollback.

## [0.2.1] - 2026-10-02

### Alterado

- Página About reescrita para refletir a arquitetura e o estado operacional reais da linha 0.2.x.
- Arquitetura visual ampliada com cadeia RF e fluxo de dados MQTT → Collector → SQLite → FastAPI → Nginx/React.
- Componentes, versões validadas, serviços, diretórios e operação transacional atualizados na interface.
- Campo “Próximos passos” removido da página About por já representar itens concluídos.

### Segurança operacional

- Alteração exclusivamente de frontend/documentação; nenhuma mudança na cadeia RF.
- Distribuição feita por GitHub Release e aplicada pelo mecanismo transacional da página Updates.

## [0.2.0] - 2026-10-02

### Adicionado

- Camada web React/Vite aprovada para Dashboard, Statistics, Diagnostics, Settings, Updates e About.
- API FastAPI local e serviços systemd dedicados.
- Collector MQTT com estado de tráfego em SQLite.
- Dashboard em tempo real com RF→NET, NET→RF, Last Heard, BER, RSSI e slow text.
- Detecção do reflector atual por `/tmp/Links.log`.
- Statistics reais para hoje, 24 h, 7 d e 30 d.
- Importação CSV com staging atômico e suporte a arquivos grandes.
- Settings funcional com aplicação administrativa controlada.
- Atualização automática de arquivos DPlus, DExtra, DCS e XLX.
- Diagnostics real com serviços, USB/serial, firmware, portas UDP, métricas RF, logs e health checks.
- Serial Check e D-Star Path Check seguros, sem transmissão RF.
- CI de frontend, backend e shell.
- Página Updates integrada a GitHub Releases privadas, com release notes, artefato e SHA-256 reais.
- Motor transacional de update/rollback com até cinco pontos de retorno locais.
- Histórico real de operações e progresso do pipeline de atualização.

### Corrigido

- Fechamento explícito de conexões SQLite para evitar vazamento de file descriptors.
- Leitura do reflector D-Star em tempo real.
- Formatação de cidade/estado no CSV.
- Persistência e apresentação de slow text.
- RSSI D-Star em tempo real.
- `Last activity` da Diagnostics baseado na última transmissão real.
- Recent Logs abrindo no fim e respeitando rolagem manual.
- Scheduler de hosts fixado em 03:00 `America/Sao_Paulo`.
- Encerramento gracioso da API limitado para evitar timeout durante update/rollback.
- Polling da página Updates mantido desde a aceitação da operação, eliminando corrida inicial de estado.

### Segurança operacional

- Token administrativo armazenado fora do frontend.
- Helper root com comandos permitidos explicitamente.
- Alterações de configuração com backup/validação.
- Cadeia RF preservada durante mudanças de frontend/API.
- Token GitHub privado removido em redirecionamentos de download para hosts externos.
- Update/rollback reinicia somente API e collector; MMDVMHost e DStarGateway são apenas verificados pelo health check.

## [0.1.0] - 2026-10-01

### Adicionado

- Base D-Star funcional validada.
- MMDVM_HS Dual Hat via CH340 e UART 115200.
- MMDVMHost e DStarGateway congelados em versões conhecidas.
- Serviços systemd persistentes.
- D-Star simplex módulo A.
- RX, TX, slow data, BER, RSSI, áudio AMBE e ECHO validados.
- Instalação reproduzível e preservação de configurações existentes.

# Contrato visual — PP5CI Hotspot

Status: **APROVADO**  
Data de aprovação: 01/10/2026  
Alvo principal: **1920 × 1024**  
Referência visual: dashboard do projeto DV4mini, adaptado ao D-Star/MMDVM.

Este documento é o contrato de interface do PP5CI Hotspot. Alterações relevantes de hierarquia, distribuição dos cards, navegação, identidade visual ou conteúdo operacional exigem nova aprovação visual.

## 1. Regras gerais

- Tema escuro azul-marinho, com superfícies em tons de azul profundo.
- Cards arredondados, bordas discretas e contraste alto.
- Azul representa infraestrutura, navegação, RF e informação.
- Verde representa estado saudável, conexão ativa e tráfego.
- Amarelo representa atenção; vermelho representa falha.
- Tipografia legível em monitor 1920×1024, sem resolver excesso de conteúdo apenas reduzindo fontes.
- O Dashboard deve caber inteiro na tela-alvo sem rolagem vertical.
- As demais páginas devem ser desenhadas para a mesma resolução; rolagem só quando a natureza do conteúdo exigir.
- Barra superior fixa com identidade, navegação, estado geral, data e hora.
- Navegação principal: Dashboard, Estatísticas, Diagnósticos, Configurações, Atualizações e Sobre.
- A aparência deve permanecer na mesma família visual do dashboard DV4mini aprovado.

## 2. Regra de dados reais

Os números mostrados nos mockups aprovados são ilustrativos. O produto final **não pode inventar telemetria**.

Quando uma métrica não estiver disponível na fonte real:
- mostrar “—” ou “Indisponível”;
- não substituir ausência por zero;
- não estimar temperatura, RSSI, BER ou estado de reflector sem fonte confiável;
- indicar claramente dado atrasado/stale quando aplicável.

## 3. Dashboard

### Cabeçalho

Título:
- `PP5CI PP5CI Hotspot Hotspot` (indicativo e nome dinâmicos)

Subtítulo:
- `D-STAR / Linux Gateway`

À direita:
- pill `HOTSPOT ONLINE`;
- data;
- hora;
- indicação de fuso quando necessário.

### Linha de estado

Seis cards:

1. **MMDVM Modem**
   - ONLINE/OFFLINE
   - firmware
   - identificação do modem/hardware

2. **MMDVMHost**
   - ONLINE/OFFLINE
   - modo D-STAR only
   - UART/baud

3. **DStarGateway**
   - CONECTADO/OFFLINE
   - estado do gateway
   - reflector atual

4. **Rede / Reflector**
   - BOA/ATENÇÃO/INSTÁVEL/MEDINDO
   - reflector e IP
   - latência, jitter RTT e perda
   - mini-histograma das amostras recentes

5. **RF**
   - PRONTO/RX/TX
   - frequência
   - DV simplex
   - módulo

6. **Sistema**
   - SAUDÁVEL/ATENÇÃO/ERRO
   - load
   - RAM
   - uptime

### Live Traffic

Card principal, mantendo a composição do DV4mini:

```text
Rádio D-Star → MMDVM → Gateway → reflector/ECHO
```

Estados:
- IDLE
- RF → NET
- NET → RF

Exibir:
- duração atual; o badge de Duração pisca em amarelo a partir de 2:00 e em vermelho a partir de 2:30;
- estação atual;
- nome e localização quando disponíveis, consultados diretamente na base CSV durante a transmissão ativa;
- slow text D-STAR em amarelo;
- destino;
- caminho da transmissão;
- indicação visual ativa somente durante tráfego.

BER e RSSI ficam fora deste card, em painéis próprios. O badge DV não deve ser duplicado dentro do Live Traffic.

### Resumo de atividade

- Hoje: transmissões, airtime total, RF→NET, NET→RF.
- Os gráficos de Últimos 7 Dias e Últimos 30 Dias ficam em Estatísticas.

### Qualidade da Rede (Reflector)

O Dashboard mostra um card próprio entre Tráfego ao Vivo e Resumo de Hoje:
- três KPIs com sparklines individuais: latência, jitter RTT e perda;
- gráfico principal dos últimos 60 segundos em mini-barras proporcionais com folga vertical;
- fonte identificada como sonda TCP sem ICMP;
- classificação conservadora para rotas internacionais: latência abaixo de 400 ms não gera alerta sozinha;
- jitter e perda têm peso maior que RTT absoluto.

As barras ficam verdes abaixo de 400 ms, amarelas a partir de 400 ms e vermelhas em perda de sonda.

### Last Heard

Colunas mínimas:
- Time
- Direction
- Station
- Name
- Location
- Duration
- BER
- LOSS

Name e Location vêm da base CSV quando houver correspondência pelo indicativo.

BER é aplicável a RF → NET. LOSS é aplicável a NET → RF. Quando a métrica não se aplica ou não foi fornecida, mostrar “—”; nunca converter ausência em 0%.

### BER / RSSI / Airtime / Reflector

À direita de Últimas Transmissões há uma matriz 2×2:
- BER ao Vivo: gráfico à esquerda, valor Atual à direita e Mín/Máx/Média sob o valor Atual; grade vertical/horizontal e trechos de BER >=1% em amarelo;
- RSSI ao Vivo: mesma composição, linha azul e grade vertical/horizontal;
- Tempo de Uso (Airtime) · Hoje;
- Estado da Conexão com o Reflector.

### Hotspot Information

Campos mínimos:
- Callsign
- Name
- Reflector/link atual
- Module
- Frequency
- Mode
- Device
- Firmware
- UDP ports

## 4. Statistics

A página de estatísticas segue o layout aprovado e contém:

### KPIs
- Today: QSOs + airtime
- Last 7 Days: QSOs + airtime
- Last 30 Days: QSOs + airtime
- Peak Hour
- Average QSO Duration

### Gráficos
- Últimos 7 Dias
- Últimos 30 Dias
- Activity · Last 24 Hours
- Latência e Jitter do Reflector · Últimas 24h
- Direction Split · 30 Days

### Tabelas / resumos
- Top Stations · Last 30 Days
- Last Heard · Extended, incluindo BER e LOSS por transmissão
- CSV Database Summary
- Hosts Summary

A persistência estatística deve usar SQLite; o CSV é fonte de enriquecimento de identidade/localização, não banco primário das transmissões.

## 5. Diagnostics

Linha superior:
- MMDVM Modem
- MMDVMHost
- DStarGateway
- Serial / USB
- Network
- Scheduler

Blocos:
- Service Health
- Serial / USB Diagnostics
- UDP / Ports
- RF / Modem Metrics
- Recent Logs
- Last Checks
- Actions / Tools

Métricas RF só aparecem quando realmente disponíveis. BER e RSSI podem ser obtidos de eventos do MMDVMHost quando o modem os fornece. Temperatura não deve aparecer como valor real sem fonte comprovada.

A ação “Run Echo Test” será um teste guiado: o sistema abre uma janela de validação e orienta o operador a transmitir com URCALL=E; o resultado é baseado no tráfego realmente observado. O backend não deve iniciar transmissão RF automática escondida.

## 6. Settings

Cabeçalho com ações:
- Salvar
- Aplicar
- Restaurar

Abas:
- Geral
- MMDVMHost
- DStarGateway
- Hosts
- Usuários CSV
- Dashboard

Blocos da visão geral:
- Identificação
- Frequências e RF
- Rede / Serviços
- Hosts automático
- Base de usuários (.csv)
- Preferências do dashboard

Toda alteração deve informar:
- se foi somente gravada;
- se foi aplicada;
- se exigiu reload/restart;
- se falhou e foi revertida.

Arquivos de configuração devem ser escritos de forma atômica, com backup anterior e health check após aplicação.

## 7. Hosts

Atualização automática diária às **03:00 no fuso configurado no PP5CI Hotspot**.

A interface deve mostrar:
- última atualização;
- próxima execução;
- status por família de hosts;
- número de registros;
- botão Atualizar agora;
- falha da última tentativa, se houver.

A troca dos arquivos deve ser atômica: baixar → validar → preparar → substituir. Em falha, manter o último conjunto válido.

## 8. Base CSV

A página/configuração de CSV deve permitir:
- upload;
- validação;
- substituição atômica;
- contagem de registros;
- data/hora do último import;
- colunas reconhecidas;
- arquivo de exemplo.

Campos mínimos esperados:
- callsign;
- name;
- location.

A implementação pode aceitar aliases de colunas, desde que a importação mostre claramente o mapeamento final.

## 9. Updates

A página de atualizações segue o **mesmo contrato operacional do PolarTime**:

- consulta ao GitHub em tempo real;
- botão Verificar agora;
- versão instalada;
- versão disponível;
- estado do GitHub;
- canal;
- estado administrativo;
- release notes obrigatórias;
- artefato de release;
- SHA-256 obrigatório;
- pipeline real: Download → Preparação → Backup → Instalação → Reinício → Health check;
- histórico real;
- rollback transacional;
- até 5 releases locais;
- preservação de configuração e banco durante rollback;
- descrição/release notes da versão escolhida antes da confirmação.

Atualização e rollback só podem ser habilitados quando o backend confirmar que a operação é segura.

## 10. About

Conteúdo aprovado:
- Sobre o projeto
- Arquitetura
- Componentes principais
- Versões validadas
- Repositório do projeto
- Diretórios e serviços
- Próximos passos

A página deve refletir versões e caminhos reais do appliance.

## 11. Critério de aceitação visual

Uma release de interface não é considerada aceita apenas porque compila.

Deve ser verificada em 1920×1024:
- hierarquia igual ao contrato;
- Dashboard sem rolagem vertical;
- fontes legíveis;
- ausência de cards vazios desnecessários;
- tabelas sem colunas críticas truncadas;
- estados IDLE/RX/TX claros;
- cores coerentes;
- nenhuma métrica fictícia;
- navegação completa e consistente.


## Escopo por reflector (0.2.8)

### Dashboard

O card **Resumo de Hoje** e o card **Tempo de Uso (Airtime) · Hoje** devem usar automaticamente o reflector atualmente conectado como escopo.

- Trocar de reflector não apaga histórico.
- Um reflector ainda não usado no dia aparece com zero.
- Ao retornar a um reflector usado anteriormente no dia, recuperar seus totais.
- O título deve indicar explicitamente o reflector atual.

### Statistics

A página deve oferecer:
- Todos os reflectores;
- seleção de um reflector específico;
- atalho Reflector atual.

O filtro se aplica aos KPIs, séries temporais, direção, horário de pico, duração média, Top Stations, Last Heard e histórico de rede quando houver amostras do reflector.

O gráfico **Uso por Reflector · Últimos 30 Dias · Visão Geral** permanece não filtrado para permitir comparação entre reflectores.


## Qualidade de Rede · faixas RTT (0.2.9)

O painel Qualidade da Rede deve classificar a latência do reflector assim:

- 0–100 ms: verde / BOA;
- 101–260 ms: amarelo / ATENÇÃO;
- acima de 260 ms: vermelho / RUIM.

A faixa amarela deve informar que RTT nessa ordem pode ocorrer quando o reflector está hospedado em outro país.

Jitter e perda são métricas independentes e podem piorar o estado global mesmo quando a latência está verde.

O ícone “i” ao lado do título deve ser clicável e abrir um pop-up pequeno contendo:
- as três faixas de latência;
- explicação sobre reflector internacional;
- aviso de que jitter e perda também influenciam o estado;
- informação de que a sonda é TCP e não depende de ICMP/ping.

As barras dos últimos 60 s e as mini-barras do card superior devem usar as mesmas cores das faixas.


## Gradiente real das barras de latência (0.2.10)

As barras dos últimos 60 segundos devem usar gradiente vertical proporcional ao RTT real da própria amostra:

- até 100 ms: somente verde;
- de 101 a 260 ms: verde na base, transição e amarelo na parte correspondente acima de 100 ms;
- acima de 260 ms: verde → amarelo → laranja/vermelho, sendo o vermelho reservado ao trecho acima de 260 ms;
- falha de sonda: vermelho sólido.

O gradiente deve ser calculado por barra, de modo que as transições correspondam aos limiares reais de 100 ms e 260 ms, e não a posições decorativas fixas.


## Estatísticas por reflector · consistência (0.2.11)

Resumo de Hoje, Airtime de Hoje, Statistics e Last Heard filtrados por reflector devem usar a mesma identidade canônica do link atual.

O Dashboard não deve exibir zero apenas porque um evento RF do MMDVMHost omitiu o campo reflector. A associação do QSO deve usar o reflector ativo do gateway e o histórico recente pode ser reparado por correlação temporal com a telemetria de rede.


## Callsign Routing (0.2.12)

### Dashboard

Quando `traffic.route_type = callsign`:
- o título central deve indicar **CALLSIGN ROUTING**;
- o último nó do fluxo deve mostrar o indicativo remoto e o rótulo **Destino direto**;
- a linha de rota deve informar `ircDDB / QuadNet`;
- o Resumo de Hoje e o Airtime devem usar temporariamente o escopo **Direto · <CALLSIGN>**;
- Last Heard geral continua mostrando todas as transmissões.

O card DStarGateway deve indicar se ircDDB está ON ou OFF.

### Statistics

O seletor de destino deve oferecer:
- Todos os destinos;
- reflectores individuais;
- chamadas diretas agrupadas por indicativo.

Deve existir um painel global **Chamadas Diretas · Últimos 30 Dias · por indicativo** com QSOs e airtime por contato.

Quando um indicativo direto é selecionado:
- Hoje, 7 dias, 30 dias, direção, horário de pico, duração média, Top Stations e Last Heard obedecem ao contato;
- Last Heard mostra a rota `Direto · <CALLSIGN>`;
- o histórico de latência do reflector não é apresentado como se fosse a rota da chamada direta.

### Settings

DStarGateway deve oferecer:
- habilitar/desabilitar Callsign Routing;
- hostname ircDDB;
- usuário/callsign;
- estado configurado.

O padrão do produto é ircDDB habilitado em `ircv4.openquad.net`.


## Live Traffic · destino direto (0.2.13)

Durante uma chamada direta por Callsign Routing, o quarto nó do fluxo deve sempre representar o destino real do QSO, e não o reflector que eventualmente continue linkado.

Exemplo obrigatório:

`ID52 → MMDVM → Gateway → PY2ABC`

com:
- valor principal do quarto nó: `PY2ABC`;
- subtítulo: `Destino direto`;
- estado central: `CALLSIGN ROUTING`;
- metadado inferior: `ircDDB / QuadNet`.

O reflector ainda pode permanecer visível em outros painéis de estado da conexão, mas não deve substituir o destino direto dentro do painel **Tráfego ao Vivo**.


## Qualidade da Rede · Callsign Routing (0.2.14)

O card de Qualidade da Rede deve representar o destino de rede efetivamente relevante naquele momento.

### Durante chamada direta

Exibir:
- título **Qualidade da Rede (Chamada Direta)**;
- indicativo remoto;
- IPv4 do gateway D-STAR remoto resolvido pelo ircDDB, quando disponível;
- latência, jitter, perda e barras usando a mesma escala/gradiente já definida para reflectores;
- badge `Gateway G2 · TCP · sem ICMP`.

O pop-up de informação deve esclarecer que o IP pertence ao gateway D-STAR remoto usado para rotear o indicativo e não necessariamente ao equipamento pessoal do operador.

### Retenção

Após a última chamada direta, manter o alvo direto por 60 segundos.

Voltar imediatamente ao reflector quando:
- houver transmissão RF → NET pelo reflector;
- houver recepção NET → RF pelo reflector;
- qualquer sessão ativa deixar de ser `route_type=callsign`.

Sem novo tráfego, ao expirar os 60 segundos o card retorna automaticamente para o reflector conectado.

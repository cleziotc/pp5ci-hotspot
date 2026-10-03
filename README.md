# PP5CI Hotspot

PP5CI Hotspot é um appliance D-STAR para Linux, com MMDVMHost + DStarGateway, dashboard web, estatísticas, diagnósticos, Callsign Routing via ircDDB/QuadNet, monitoramento de qualidade de rede e atualizações transacionais.

O nome **PP5CI Hotspot** identifica o projeto. O indicativo da estação **não é fixo no código**: durante a instalação o operador informa seu próprio indicativo, que é aplicado ao MMDVMHost, DStarGateway e ircDDB.

<img width="1280" height="633" alt="image" src="https://github.com/user-attachments/assets/83c77bae-93c1-48f4-a7a5-781abed25552" />


## Versão atual

**0.3.0** — primeira edição pública independente, baseada na linha funcional 0.2.14 e adaptada para instalação genérica em VM e Raspberry Pi.

## Principais recursos

- D-STAR simplex com MMDVM_HS / MMDVM_HS Dual Hat;
- MMDVMHost e DStarGateway compilados a partir de referências upstream fixadas;
- dashboard web responsivo;
- tráfego RF → NET e NET → RF em tempo real;
- BER, RSSI, slow text e Last Heard;
- estatísticas por reflector e por chamada direta;
- Callsign Routing por ircDDB / QuadNet;
- identificação de destino direto pelo journal do DStarGateway;
- qualidade de rede do reflector ou gateway remoto, sem depender de ICMP;
- banco SQLite local;
- base CSV opcional de radioamadores;
- atualização automática das listas DPlus, DExtra, DCS e XLX;
- página de Settings protegida por senha;
- página de Updates ligada ao repositório público `cleziotc/pp5ci-hotspot`;
- artefatos de release com SHA-256;
- atualização e rollback transacionais.

## Plataformas

### VM / computador Linux

O instalador `install-vm.sh` foi projetado para Debian e Ubuntu com `apt`, em arquiteturas Linux suportadas pelas dependências do projeto.

A placa MMDVM deve aparecer como uma porta serial Linux. É recomendado usar um caminho persistente de `/dev/serial/by-id/...`.

### Raspberry Pi

O instalador `install-rpi.sh` usa a UART do conector GPIO do Raspberry Pi.

Ligação esperada para uma placa MMDVM HAT:

| Raspberry Pi | Função |
|---|---|
| pino físico 8 | TX do Raspberry Pi → RX da MMDVM |
| pino físico 10 | RX do Raspberry Pi ← TX da MMDVM |
| pino físico 6 | GND |
| dispositivo Linux | `/dev/serial0` |

Quando necessário, o instalador habilita `enable_uart=1` e remove console serial do `cmdline.txt`. Se essa configuração for alterada, um reboot é necessário.

Raspberry Pi Zero 2 W, Pi 3, Pi 4 e Pi 5 são alvos recomendados. Modelos ARM muito antigos podem não suportar a versão atual do Node.js usada para compilar o frontend.

## Instalação rápida

### Ubuntu / Debian VM

```bash
curl -fsSL https://raw.githubusercontent.com/cleziotc/pp5ci-hotspot/main/install-vm.sh | sudo bash
```

### Raspberry Pi

```bash
curl -fsSL https://raw.githubusercontent.com/cleziotc/pp5ci-hotspot/main/install-rpi.sh | sudo bash
```

Também é possível clonar o repositório:

```bash
git clone https://github.com/cleziotc/pp5ci-hotspot.git
cd pp5ci-hotspot
sudo ./install-vm.sh
# ou:
sudo ./install-rpi.sh
```

## O que o instalador pergunta

A instalação é interativa e solicita:

1. indicativo do radioamador;
2. frequência RX/TX em Hz;
3. porta serial da MMDVM na instalação VM;
4. criação da senha de administrador;
5. confirmação da senha de administrador.

A senha precisa ter pelo menos 8 caracteres.

A senha **não é salva em texto claro**. O sistema armazena somente salt + hash PBKDF2-SHA256 em:

```text
/etc/pp5ci-hotspot/admin-password.json
```

## Arquitetura

```text
Rádio D-STAR
    ↕ RF
MMDVM_HS / MMDVM_HS Dual Hat
    ↕ UART
MMDVMHost
    ↕ UDP local
DStarGateway
    ↕ Internet
Reflectores / ircDDB / QuadNet

MMDVMHost
    └── MQTT JSON
          ↓
      Mosquitto
          ↓
      Collector
       ├── SQLite
       └── estado em tempo real
          ↓
       FastAPI
          ↓
        Nginx
          ↓
     React dashboard
```

## Serviços systemd

```text
pp5ci-hotspot-mmdvmhost.service
pp5ci-hotspot-dstargateway.service
pp5ci-hotspot-collector.service
pp5ci-hotspot-api.service
pp5ci-hotspot-hosts-update.service
pp5ci-hotspot-hosts-update.timer
mosquitto.service
nginx.service
```

## Diretórios instalados

```text
/opt/pp5ci-hotspot/                  aplicação, venv e binários
/etc/pp5ci-hotspot/                  configurações e hash da senha
/var/lib/pp5ci-hotspot/              SQLite, estado e backups de release
/var/www/pp5ci-hotspot/              frontend publicado
/usr/local/share/dstargateway.d/     listas D-Star
/usr/local/sbin/pp5ci-hotspot-admin  helper administrativo
/usr/local/libexec/pp5ci-hotspot-updater
```

## Updates

O canal estável consulta exclusivamente:

```text
https://github.com/cleziotc/pp5ci-hotspot/releases
```

Nenhum token GitHub é necessário para consultar o repositório público.

Uma release instalável precisa conter:

```text
pp5ci-hotspot-vX.Y.Z.tar.gz
pp5ci-hotspot-vX.Y.Z.tar.gz.sha256
```

O updater valida SHA-256, cria backup local, atualiza a camada gerenciada e executa health check. Configurações locais e banco SQLite são preservados. Rollback cria um novo ponto de retorno antes da restauração.

## Desenvolvimento

Backend:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

Validação dos instaladores:

```bash
bash -n install-vm.sh install-rpi.sh scripts/install-common.sh
python3 -m py_compile scripts/pp5ci-hotspot-admin.py scripts/pp5ci-hotspot-updater.py
```

## Documentação

- [Instalação](docs/INSTALLATION.md)
- [Raspberry Pi / GPIO](docs/RASPBERRY_PI.md)
- [Arquitetura](docs/arquitetura.md)
- [Guia do código](docs/CODE_GUIDE.md)
- [Contrato da API](docs/API_CONTRACT.md)
- [Contrato da interface](docs/UI_CONTRACT.md)
- [Operação e manutenção](docs/OPERATIONS.md)
- [Segurança](docs/SECURITY.md)
- [Releases e updates](docs/RELEASES.md)
- [Créditos e componentes de terceiros](THIRD_PARTY_NOTICES.md)
- [Changelog](CHANGELOG.md)

## Referências fixadas

| Componente | Referência usada pela linha atual |
|---|---|
| MMDVMHost | commit `590c531391dfd3146073afbc3956f70d42c62a46` |
| DStarGateway | commit `0c1dbb5` / linha v0.7 |
| MMDVM_HS | hardware/firmware compatível com protocolo MMDVM UART |

## Créditos

PP5CI Hotspot integra e depende de software livre desenvolvido por diversos radioamadores. Os principais créditos, autores e licenças estão descritos em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Em especial, devem ser reconhecidos os trabalhos de Jonathan Naylor **G4KLX**, Geoffrey Merck **F4FXL / KC3FRA**, Thomas A. Early **N7TAE**, Andy Uribe **CA6JAU**, além das comunidades MMDVM, D-STAR, ircDDB, QuadNet e Pi-Star.

## Uso responsável

A frequência, potência, indicativo e demais parâmetros de RF são responsabilidade do operador. Configure o hotspot conforme a regulamentação aplicável à sua licença e região.

## Licença

Consulte [LICENSE](LICENSE). Componentes de terceiros permanecem sujeitos às suas próprias licenças.

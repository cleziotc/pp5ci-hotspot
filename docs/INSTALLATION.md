# Instalação

## Visão geral

Existem dois instaladores públicos:

- `install-vm.sh`: Debian/Ubuntu em VM ou computador Linux com MMDVM ligada por serial/USB.
- `install-rpi.sh`: Raspberry Pi com MMDVM HAT ligada pela UART do GPIO.

Ambos chamam `scripts/install-common.sh`, que executa a instalação completa.

## Instalação em VM

```bash
curl -fsSL https://raw.githubusercontent.com/cleziotc/pp5ci-hotspot/main/install-vm.sh | sudo bash
```

O instalador tenta localizar uma porta persistente em `/dev/serial/by-id/` e permite confirmar ou alterar o caminho.

## Instalação em Raspberry Pi

```bash
curl -fsSL https://raw.githubusercontent.com/cleziotc/pp5ci-hotspot/main/install-rpi.sh | sudo bash
```

A MMDVM é configurada em `/dev/serial0`.

## Perguntas da instalação

### Indicativo

O indicativo informado é convertido para maiúsculas e usado em:

- `[General] Callsign` no MMDVMHost;
- gateway e repeater no DStarGateway;
- login DPlus;
- usuário ircDDB/QuadNet.

Nenhum indicativo pessoal é pré-configurado no repositório.

### Frequência

A frequência é informada em Hz, por exemplo:

```text
434000000
```

O instalador preenche RX e TX com o mesmo valor inicial. Ajustes posteriores podem ser feitos em Settings.

### Senha de administrador

A senha é digitada e confirmada de forma oculta no terminal. Mínimo: 8 caracteres.

O instalador gera um salt aleatório de 24 bytes e deriva a credencial com PBKDF2-HMAC-SHA256, 310.000 iterações.

Arquivo resultante:

```text
/etc/pp5ci-hotspot/admin-password.json
```

Permissões:

```text
root:mmdvm 0640
```

A senha original não é gravada.

## O que é instalado

1. dependências de compilação;
2. MMDVMHost em commit fixado;
3. patch de RSSI;
4. DStarGateway em commit fixado;
5. Python virtualenv e backend;
6. Mosquitto local;
7. frontend React;
8. Nginx;
9. helper administrativo;
10. updater transacional;
11. systemd units;
12. timer de atualização de host files.

## Portas locais

| Serviço | Endereço |
|---|---|
| DStarGateway Homebrew | `127.0.0.1:20010/UDP` |
| MMDVMHost D-Star Network | `127.0.0.1:20011/UDP` |
| API FastAPI | `127.0.0.1:8080/TCP` |
| MQTT Mosquitto | `127.0.0.1:1883/TCP` |
| Web | `0.0.0.0:80/TCP` via Nginx |

## Pós-instalação

Verifique:

```bash
systemctl status pp5ci-hotspot-mmdvmhost
systemctl status pp5ci-hotspot-dstargateway
systemctl status pp5ci-hotspot-collector
systemctl status pp5ci-hotspot-api
systemctl status nginx
```

Abra no navegador:

```text
http://IP-DO-HOTSPOT/
```

## Logs

```bash
journalctl -u pp5ci-hotspot-mmdvmhost -f
journalctl -u pp5ci-hotspot-dstargateway -f
journalctl -u pp5ci-hotspot-collector -f
journalctl -u pp5ci-hotspot-api -f
```

## Reinstalação

Arquivos existentes de MMDVMHost, DStarGateway e RSSI recebem backup timestamp antes de serem substituídos pela configuração inicial.

A reinstalação deve ser usada com cautela porque foi pensada como provisionamento. Para versões novas, prefira a página Updates.

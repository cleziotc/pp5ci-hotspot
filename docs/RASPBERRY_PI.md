# Raspberry Pi e MMDVM via GPIO

## Objetivo

No Raspberry Pi, o PP5CI Hotspot usa a UART primária exposta como `/dev/serial0`. A MMDVM HAT é conectada ao header de 40 pinos; não é necessário adaptador USB-TTL.

## Pinagem

| Pino físico | GPIO / sinal | Ligação |
|---|---|---|
| 8 | GPIO14 / TXD | TX do Raspberry → RX da MMDVM |
| 10 | GPIO15 / RXD | RX do Raspberry ← TX da MMDVM |
| 6 | GND | GND comum |

Se a HAT encaixa diretamente no header, essas conexões já fazem parte do encaixe.

## Configuração feita pelo instalador

O instalador procura:

```text
/boot/firmware/config.txt
/boot/config.txt
```

e garante:

```text
enable_uart=1
```

Também procura console serial em:

```text
/boot/firmware/cmdline.txt
/boot/cmdline.txt
```

e remove entradas `console=serial0,...`, `console=ttyAMA0,...` ou `console=ttyS0,...` para que a UART fique disponível ao modem.

Quando algum desses arquivos é alterado, reinicie o Raspberry Pi.

## Verificação após reboot

```bash
ls -l /dev/serial0
readlink -f /dev/serial0
systemctl status pp5ci-hotspot-mmdvmhost
journalctl -u pp5ci-hotspot-mmdvmhost -n 100 --no-pager
```

O MMDVMHost deve identificar o firmware MMDVM na inicialização.

## Bluetooth e UART

Em alguns modelos de Raspberry Pi, `/dev/serial0` é um alias que aponta para a UART apropriada conforme a configuração da plataforma. O projeto usa o alias em vez de codificar `ttyAMA0` ou `ttyS0`.

## Modelos recomendados

- Raspberry Pi Zero 2 W;
- Raspberry Pi 3;
- Raspberry Pi 4;
- Raspberry Pi 5.

O frontend precisa ser compilado durante a instalação a partir do repositório `main`. Por isso memória, arquitetura e suporte a Node.js importam. Em modelos muito antigos, prefira instalar a partir de um artefato de release pré-compilado quando disponível.

## Alimentação

A MMDVM HAT e o Raspberry Pi devem receber alimentação estável. Erros de serial, resets ou comportamento RF irregular podem ser causados por alimentação inadequada e não necessariamente por software.

# Validação da edição pública

## Escopo

Esta lista define o que deve ser validado antes de considerar uma release pública pronta.

## Build

Backend:

```bash
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
python -m compileall -q backend/pp5ci_hotspot
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

Scripts:

```bash
bash -n install-vm.sh install-rpi.sh scripts/install-common.sh
python3 -m py_compile scripts/pp5ci-hotspot-admin.py scripts/pp5ci-hotspot-updater.py
```

## Identidade pública

O repositório não pode conter:

- namespace antigo;
- paths antigos;
- URL de repositório privado;
- nomes de units antigos;
- senha/token real;
- IP, QTH ou indicativo pessoal como configuração fixa.

O CI executa uma verificação automática para impedir regressão de nomes do projeto anterior.

## Instalação VM

Validar em Ubuntu/Debian limpo:

1. instalador solicita indicativo;
2. instalador solicita frequência;
3. instalador detecta/aceita serial;
4. instalador solicita e confirma senha;
5. MMDVMHost inicia;
6. DStarGateway inicia;
7. Mosquitto inicia;
8. collector inicia;
9. API inicia;
10. Nginx serve o frontend;
11. dashboard abre por HTTP;
12. Settings aceita a senha criada;
13. credencial incorreta recebe HTTP 401.

## Instalação Raspberry Pi

Validar:

1. `enable_uart=1`;
2. ausência de console serial conflitante;
3. `/dev/serial0` presente após reboot;
4. MMDVMHost identifica a HAT;
5. pinos 8/10 do GPIO são usados pela UART;
6. demais serviços iniciam normalmente.

## D-STAR

Validar:

- RX RF;
- TX RF;
- RF→NET;
- NET→RF;
- reflector;
- Callsign Routing;
- slow text;
- BER;
- RSSI quando suportado pelo modem.

## Dashboard

Validar:

- status de serviços;
- link atual;
- tráfego ao vivo;
- Last Heard;
- Statistics;
- Settings;
- Diagnostics;
- Updates.

## Callsign Routing

Validar com indicativos de teste autorizados:

- destino direto exibido sob a antena;
- rota identificada como callsign;
- reflector linkado não contamina estatística direta;
- gateway remoto aprendido via ircDDB;
- sonda de rede muda para gateway remoto;
- retenção por 60 segundos;
- retorno imediato ao reflector quando há tráfego de reflector.

## Updates

Para uma release de teste:

1. tag corresponde a `VERSION`;
2. nota `docs/releases/vX.Y.Z.md` existe;
3. tar.gz é criado;
4. SHA-256 é criado;
5. GitHub Release publica ambos;
6. página Updates encontra a release pública;
7. download não exige token;
8. checksum é validado;
9. backup é criado;
10. update conclui health check;
11. rollback restaura a versão anterior.

## Regra final

Uma release só deve ser marcada como estável depois que o CI estiver verde e os testes de hardware pertinentes à plataforma tiverem sido executados.

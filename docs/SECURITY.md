# Segurança

## Modelo administrativo

Leitura de dashboard e telemetria não exige senha administrativa.

Operações que alteram configuração, reiniciam serviços ou executam update/rollback exigem a senha criada durante a instalação.

## Armazenamento da senha

A senha não é armazenada em texto claro.

Arquivo:

```text
/etc/pp5ci-hotspot/admin-password.json
```

Formato lógico:

```json
{
  "algorithm": "pbkdf2-sha256",
  "iterations": 310000,
  "salt": "<base64>",
  "hash": "<base64>"
}
```

O backend deriva a senha recebida com PBKDF2-HMAC-SHA256 e compara o resultado em tempo constante com `hmac.compare_digest`.

## Transporte da senha

A interface envia a senha somente em requisições administrativas no header:

```text
X-PP5CI-Hotspot-Admin-Password
```

O frontend não grava a senha em `localStorage` nem `sessionStorage`; ela permanece apenas no estado da página atual.

Em rede não confiável, coloque HTTPS na frente do Nginx. HTTP puro na LAN não protege a senha contra captura de tráfego.

## Privilégios

A API e o collector executam como usuário `mmdvm`.

Operações privilegiadas são delegadas ao helper root:

```text
/usr/local/sbin/pp5ci-hotspot-admin
```

O sudoers libera somente subcomandos explicitamente aceitos pelo helper.

## Updater

O updater:

- aceita apenas tags estáveis `vX.Y.Z`;
- consulta o repositório público configurado;
- exige artefato e arquivo SHA-256;
- limita o tamanho do download;
- rejeita paths inseguros no tar;
- rejeita symlinks/hardlinks/devices no artefato;
- cria backup transacional antes da troca;
- executa health check;
- restaura o backup em caso de falha.

## MQTT

O Mosquitto escuta apenas em `127.0.0.1:1883` e permite anonymous apenas nesse listener local.

## API

A API escuta somente em `127.0.0.1:8080`. O acesso da LAN ocorre por Nginx.

## Segredos

Não faça commit de:

- senha administrativa;
- arquivos `admin-password.json`;
- bancos SQLite de produção;
- dumps de configuração com credenciais futuras;
- tokens de serviços externos.

O repositório público não precisa de token GitHub para o canal normal de updates.

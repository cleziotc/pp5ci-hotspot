# Processo de releases — PP5CI Hotspot

## Objetivo

Toda versão oferecida pela página **Updates** deve corresponder a uma GitHub Release real, com release notes obrigatórias, artefato e checksum SHA-256.

## Versionamento

- `main`: linha estável.
- `develop`: integração e validação.
- `VERSION`: versão do pacote estável.
- `backend/pp5ci_hotspot/__init__.py`: versão exposta pela API.
- tags oficiais: `vMAJOR.MINOR.PATCH`.

Versões em desenvolvimento podem usar o sufixo `-dev` na API, mas uma release oficial não pode.

## Release notes

Cada release mantém um arquivo versionado:

```text
docs/releases/v0.1.0.md
docs/releases/v0.2.0.md
...
```

O conteúdo desse arquivo é usado como corpo da GitHub Release.

## Artefatos

Uma release oficial deve publicar:

```text
pp5ci-hotspot-vX.Y.Z.tar.gz
pp5ci-hotspot-vX.Y.Z.tar.gz.sha256
```

O checksum é obrigatório para a página Updates considerar o pacote instalável.

## Workflow

O workflow `.github/workflows/release.yml` é disparado quando uma tag `v*` é enviada.

Ele:

1. confere se a tag corresponde ao arquivo `VERSION`;
2. executa os testes do backend e o build do frontend;
3. inclui `frontend/dist` no pacote;
4. gera o tarball;
5. calcula SHA-256;
6. publica a GitHub Release usando as notas versionadas.

## Instalação pela página Updates

O appliance consulta a GitHub Release estável, valida artefato e SHA-256 e entrega a execução privilegiada somente ao helper controlado. O updater cria backup local, instala a camada web em staging, reinicia apenas API/collector e executa health check. Falhas acionam restauração automática.

Configurações em `/etc/pp5ci-hotspot/` e o banco em `/var/lib/pp5ci-hotspot/` não são substituídos. Até cinco backups de rollback são mantidos.

## Critério de publicação

Antes de criar uma tag:

- CI da branch deve estar verde;
- release notes devem estar finalizadas;
- `VERSION` e `__version__` devem corresponder;
- Dashboard/Statistics/Diagnostics/Settings devem ter sido validados na VM;
- nenhuma alteração deve exigir reinício RF sem estar documentada;
- backup e rollback devem estar definidos para alterações destrutivas.

## Releases históricas

### v0.1.0

Base RF validada em 01/10/2026. O marco técnico está documentado em `docs/releases/v0.1.0.md`.

### v0.2.0

Camada web, API, collector, estatísticas, settings, diagnostics e mecanismo de updates. As notas ficam em `docs/releases/v0.2.0.md` até a publicação.

## Repositório privado

Quando o repositório for privado, a consulta de Releases e o download dos assets requerem uma credencial GitHub **somente de leitura**. O token fica em `/etc/pp5ci-hotspot/github-token`, com acesso restrito, e nunca é enviado ao navegador.

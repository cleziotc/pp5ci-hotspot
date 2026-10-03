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

O processo público possui dois caminhos compatíveis:

- `.github/workflows/publish.yml`: caminho recomendado. Uma branch `publish/vX.Y.Z` deve apontar exatamente para o commit de `main`. O workflow valida `VERSION` e release notes, cria/finaliza a tag, executa testes, monta tar.gz + SHA-256 e publica a GitHub Release na mesma execução.
- `.github/workflows/release.yml`: caminho alternativo para uma tag `v*` enviada manualmente por um mantenedor.

O publicador recomendado:

1. confirma que a branch é exatamente `publish/v<conteúdo de VERSION>`;
2. confirma que o commit é o mesmo de `main`;
3. exige `docs/releases/vX.Y.Z.md`;
4. cria a tag; uma tag ainda sem Release pode ser finalizada para o commit atual, mas uma tag de Release já publicada nunca é movida;
5. executa testes do backend;
6. compila o frontend;
7. valida os instaladores;
8. inclui `frontend/dist` no pacote;
9. gera tar.gz e SHA-256;
10. publica a GitHub Release.

Para publicar uma versão, crie a branch `publish/vX.Y.Z` a partir do commit estável de `main`. O fluxo rejeita uma branch divergente.

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

## Repositório público

O canal oficial é `cleziotc/pp5ci-hotspot`. A consulta de releases e o download dos assets não dependem de token GitHub.

O updater rejeita releases sem artefato e SHA-256 correspondentes.

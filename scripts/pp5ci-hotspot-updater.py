#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import grp
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP = Path("/opt/pp5ci-hotspot")
BACKEND = APP / "backend"
VENV = APP / "venv"
WEB = Path("/var/www/pp5ci-hotspot")
ETC = Path("/etc/pp5ci-hotspot")
STATE = Path("/var/lib/pp5ci-hotspot")
BACKUPS = STATE / "releases"
STATUS = STATE / "update-status.json"
HISTORY = STATE / "update-history.json"
LOCK = STATE / "update.lock"
TOKEN = ETC / "github-token"
ADMIN = Path("/usr/local/sbin/pp5ci-hotspot-admin")
UPDATER = Path("/usr/local/libexec/pp5ci-hotspot-updater")
SUDOERS = Path("/etc/sudoers.d/pp5ci-hotspot")
SYSTEMD = Path("/etc/systemd/system")
REPO = os.getenv("PP5CI_HOTSPOT_GITHUB_REPOSITORY", "cleziotc/pp5ci-hotspot").strip() or "cleziotc/pp5ci-hotspot"
WEB_UNITS = (
    "pp5ci-hotspot-api.service",
    "pp5ci-hotspot-collector.service",
    "pp5ci-hotspot-hosts-update.service",
    "pp5ci-hotspot-hosts-update.timer",
)
RF_UNITS = ("pp5ci-hotspot-host.service", "polar-dstargateway.service")
PROGRESS = {"download": 10, "preparation": 25, "backup": 40, "installation": 70, "restart": 85, "health_check": 95, "done": 100}


class UpdateError(RuntimeError):
    pass


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep redirects clean when GitHub hands release assets to storage hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).hostname
        new_host = urllib.parse.urlsplit(newurl).hostname
        if old_host != new_host:
            redirected.remove_header("Authorization")
        return redirected


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: Any, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def status(state: str, operation: str, step: str, message: str, started: str, old: str, new: str,
           backup_id: str | None = None, error: str | None = None, finished: str | None = None) -> None:
    write_json(STATUS, {
        "state": state,
        "operation": operation,
        "step": step,
        "progress": PROGRESS.get(step, 0),
        "message": message,
        "started_at": started,
        "finished_at": finished,
        "from_version": old,
        "to_version": new,
        "backup_id": backup_id,
        "error": error,
    })


def history(item: dict[str, Any]) -> None:
    items = read_json(HISTORY, [])
    if not isinstance(items, list):
        items = []
    write_json(HISTORY, [item, *items][:100])


def run(argv: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    if check and p.returncode:
        raise UpdateError((p.stderr or p.stdout or "falha de comando").strip()[-1500:])
    return p


def version_from(init_file: Path) -> str:
    try:
        text = init_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise UpdateError(f"Versão não encontrada em {init_file}") from exc
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not m:
        raise UpdateError("Versão não encontrada")
    return m.group(1)


def installed_version() -> str:
    return version_from(BACKEND / "pp5ci_hotspot" / "__init__.py")


def version_key(value: str) -> tuple[int, int, int, int]:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value.strip())
    if not m:
        raise UpdateError(f"Versão inválida: {value}")
    return (int(m[1]), int(m[2]), int(m[3]), 1 if not m[4] else 0)


def request(url: str, accept: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": "PP5CI-Hotspot-Updater/0.2",
        "X-GitHub-Api-Version": "2022-11-28",
    })


def github_release(tag: str) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"
    try:
        with urllib.request.urlopen(request(url, "application/vnd.github+json"), timeout=15) as r:
            release = json.load(r)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub HTTP {exc.code}") from exc
    except Exception as exc:
        raise UpdateError(f"Falha ao consultar GitHub: {exc}") from exc
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease") or release.get("tag_name") != tag:
        raise UpdateError("Release GitHub inválida")
    artifact_name = f"pp5ci-hotspot-{tag}.tar.gz"
    checksum_name = artifact_name + ".sha256"
    assets = {str(x.get("name")): x for x in release.get("assets", []) if isinstance(x, dict)}
    if artifact_name not in assets or checksum_name not in assets:
        raise UpdateError("Release sem artefato e SHA-256 esperados")
    return assets[artifact_name], assets[checksum_name]


def download(asset: dict[str, Any], target: Path) -> None:
    url = str(asset.get("url") or "")
    if not re.fullmatch(r"https://api\.github\.com/repos/[^/]+/[^/]+/releases/assets/\d+", url):
        raise UpdateError("URL de asset inválida")
    total = 0
    try:
        opener = urllib.request.build_opener(SafeRedirectHandler())
        with opener.open(request(url, "application/octet-stream"), timeout=30) as r, target.open("wb") as f:
            while True:
                chunk = r.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 250 * 1024 * 1024:
                    raise UpdateError("Asset excede 250 MB")
                f.write(chunk)
    except Exception as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"Falha no download: {exc}") from exc
    if not total:
        raise UpdateError("Asset vazio")


def verify(artifact: Path, checksum: Path) -> str:
    try:
        parts = checksum.read_text(encoding="utf-8").strip().splitlines()[0].split()
        expected, named = parts[0].lower(), parts[-1].lstrip("*")
    except Exception as exc:
        raise UpdateError("SHA-256 inválido") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or Path(named).name != artifact.name:
        raise UpdateError("SHA-256 inválido")
    h = hashlib.sha256()
    with artifact.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        raise UpdateError("SHA-256 do artefato não confere")
    return expected


def extract(artifact: Path, target: Path) -> Path:
    target.mkdir()
    root = target.resolve()
    with tarfile.open(artifact, "r:gz") as tar:
        for member in tar.getmembers():
            dest = (target / member.name).resolve()
            if (dest != root and root not in dest.parents) or member.isdev() or member.issym() or member.islnk():
                raise UpdateError("Artefato contém caminho/tipo inseguro")
        tar.extractall(target, filter="data")
    dirs = [x for x in target.iterdir() if x.is_dir()]
    if len(dirs) != 1:
        raise UpdateError("Estrutura do artefato inválida")
    release = dirs[0]
    for rel in (
        "backend/pp5ci_hotspot/__init__.py",
        "backend/requirements.txt",
        "frontend/dist/index.html",
        "scripts/pp5ci-hotspot-admin.py",
        "scripts/pp5ci-hotspot-updater.py",
        "config/pp5ci-hotspot.sudoers",
        "systemd/pp5ci-hotspot-api.service",
        "systemd/pp5ci-hotspot-collector.service",
    ):
        if not (release / rel).exists():
            raise UpdateError(f"Artefato incompleto: {rel}")
    return release


def cp(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    elif source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def make_backup(old: str, target: str | None, digest: str | None) -> str:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    mmdvm_gid = grp.getgrnam("mmdvm").gr_gid
    os.chown(BACKUPS, 0, mmdvm_gid)
    os.chmod(BACKUPS, 0o750)
    backup_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{re.sub(r'[^0-9A-Za-z._-]+', '-', old)}"
    b = BACKUPS / backup_id
    b.mkdir(mode=0o750)
    os.chown(b, 0, mmdvm_gid)
    cp(BACKEND, b / "backend")
    cp(VENV, b / "venv")
    cp(WEB, b / "frontend")
    cp(ADMIN, b / "admin/pp5ci-hotspot-admin")
    cp(UPDATER, b / "admin/pp5ci-hotspot-updater")
    cp(SUDOERS, b / "admin/pp5ci-hotspot.sudoers")
    for unit in WEB_UNITS:
        cp(SYSTEMD / unit, b / "systemd" / unit)
    metadata_path = b / "metadata.json"
    write_json(metadata_path, {
        "id": backup_id,
        "version": old,
        "created_at": utc(),
        "target_version": target,
        "sha256": digest,
        "config_preserved": True,
        "database_preserved": True,
    }, 0o640)
    os.chown(metadata_path, 0, mmdvm_gid)
    return backup_id


def stage_venv(release: Path, target: Path) -> None:
    run(["python3", "-m", "venv", str(target)], 120)
    run([str(target / "bin/python"), "-m", "pip", "install", "--upgrade", "pip"], 300)
    run([str(target / "bin/python"), "-m", "pip", "install", "-r", str(release / "backend/requirements.txt")], 600)


def swap(stage: Path, target: Path) -> None:
    old = target.with_name(target.name + ".update-old")
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        os.replace(target, old)
    os.replace(stage, target)
    if old.exists():
        shutil.rmtree(old)


def put(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    os.close(fd)
    tmp = Path(name)
    try:
        shutil.copy2(source, tmp)
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def apply_release(release: Path) -> None:
    bnext = APP / f".backend-next-{os.getpid()}"
    vnext = APP / f".venv-next-{os.getpid()}"
    wnext = WEB.parent / f".pp5ci-hotspot-next-{os.getpid()}"
    for p in (bnext, vnext, wnext):
        if p.exists():
            shutil.rmtree(p)
    shutil.copytree(release / "backend", bnext)
    shutil.copytree(release / "frontend/dist", wnext)
    stage_venv(release, vnext)

    fd, sudo_name = tempfile.mkstemp(prefix="pp5ci-hotspot.sudoers.", dir="/etc/sudoers.d")
    os.close(fd)
    sudo_tmp = Path(sudo_name)
    try:
        shutil.copy2(release / "config/pp5ci-hotspot.sudoers", sudo_tmp)
        os.chmod(sudo_tmp, 0o440)
        run(["visudo", "-cf", str(sudo_tmp)], 20)

        swap(bnext, BACKEND)
        swap(vnext, VENV)
        swap(wnext, WEB)
        put(release / "scripts/pp5ci-hotspot-admin.py", ADMIN, 0o755)
        put(release / "scripts/pp5ci-hotspot-updater.py", UPDATER, 0o755)
        os.replace(sudo_tmp, SUDOERS)
        sudo_tmp = Path("/nonexistent")
        for unit in WEB_UNITS:
            src = release / "systemd" / unit
            if src.exists():
                put(src, SYSTEMD / unit, 0o644)
        run(["systemctl", "daemon-reload"], 30)
    finally:
        try:
            sudo_tmp.unlink()
        except OSError:
            pass


def restore(backup_id: str) -> None:
    if not re.fullmatch(r"[0-9A-Za-z._-]+", backup_id):
        raise UpdateError("Backup inválido")
    b = BACKUPS / backup_id
    if not (b / "metadata.json").exists():
        raise UpdateError("Backup não encontrado")
    bnext = APP / f".backend-restore-{os.getpid()}"
    vnext = APP / f".venv-restore-{os.getpid()}"
    wnext = WEB.parent / f".pp5ci-hotspot-restore-{os.getpid()}"
    for src, dst in ((b / "backend", bnext), (b / "venv", vnext), (b / "frontend", wnext)):
        if not src.exists():
            raise UpdateError(f"Backup incompleto: {src.name}")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
    swap(bnext, BACKEND)
    swap(vnext, VENV)
    swap(wnext, WEB)
    for src, dst, mode in (
        (b / "admin/pp5ci-hotspot-admin", ADMIN, 0o755),
        (b / "admin/pp5ci-hotspot-updater", UPDATER, 0o755),
        (b / "admin/pp5ci-hotspot.sudoers", SUDOERS, 0o440),
    ):
        if src.exists():
            if dst == SUDOERS:
                run(["visudo", "-cf", str(src)], 20)
            put(src, dst, mode)
    for unit in WEB_UNITS:
        src = b / "systemd" / unit
        if src.exists():
            put(src, SYSTEMD / unit, 0o644)
    run(["systemctl", "daemon-reload"], 30)


def restart_web() -> None:
    run(["systemctl", "restart", "pp5ci-hotspot-collector.service"], 30)
    run(["systemctl", "restart", "pp5ci-hotspot-api.service"], 30)


def health(expected: str) -> None:
    for unit in ("pp5ci-hotspot-api.service", "pp5ci-hotspot-collector.service", *RF_UNITS):
        p = run(["systemctl", "is-active", unit], 15, False)
        if p.returncode or p.stdout.strip() != "active":
            raise UpdateError(f"Health check: {unit} não está ativo")
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/health", timeout=3) as r:
                if isinstance(json.load(r), dict):
                    break
        except Exception:
            time.sleep(1)
    else:
        raise UpdateError("Health check: API indisponível")
    if version_key(installed_version()) != version_key(expected):
        raise UpdateError(f"Versão instalada é {installed_version()}, esperado {expected}")


def prune(protect: set[str] | None = None) -> None:
    protect = protect or set()
    dirs = sorted((x for x in BACKUPS.glob("*") if x.is_dir() and (x / "metadata.json").exists()), reverse=True)
    keep: list[Path] = [path for path in dirs if path.name in protect][:5]
    for path in dirs:
        if path in keep:
            continue
        if len(keep) < 5:
            keep.append(path)
        else:
            shutil.rmtree(path, ignore_errors=True)


def do_install(tag: str) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise UpdateError("Somente tags estáveis vX.Y.Z são permitidas")
    old, new = installed_version(), tag.lstrip("v")
    if version_key(tag) <= version_key(old):
        raise UpdateError("A release não é mais nova que a versão instalada")
    started, t0, backup_id = utc(), time.monotonic(), None
    status("running", "install", "download", f"Baixando {tag}", started, old, new)
    try:
        with tempfile.TemporaryDirectory(prefix="pp5ci-hotspot-update-") as td:
            tmp = Path(td)
            ainfo, cinfo = github_release(tag)
            artifact, checksum = tmp / f"pp5ci-hotspot-{tag}.tar.gz", tmp / f"pp5ci-hotspot-{tag}.tar.gz.sha256"
            download(ainfo, artifact)
            download(cinfo, checksum)
            digest = verify(artifact, checksum)
            status("running", "install", "preparation", "SHA-256 validado; preparando release", started, old, new)
            release = extract(artifact, tmp / "extract")
            if version_key(version_from(release / "backend/pp5ci_hotspot/__init__.py")) != version_key(tag):
                raise UpdateError("Versão interna do artefato não corresponde à tag")
            status("running", "install", "backup", "Criando backup transacional", started, old, new)
            backup_id = make_backup(old, new, digest)
            try:
                status("running", "install", "installation", "Instalando camada web", started, old, new, backup_id)
                apply_release(release)
                status("running", "install", "restart", "Reiniciando somente API e collector", started, old, new, backup_id)
                restart_web()
                status("running", "install", "health_check", "Validando API, collector e cadeia RF sem reiniciá-la", started, old, new, backup_id)
                health(new)
            except Exception:
                restore(backup_id)
                restart_web()
                health(old)
                raise
        finished = utc()
        status("success", "install", "done", f"Atualização para {tag} concluída", started, old, new, backup_id, finished=finished)
        history({"started_at": started, "finished_at": finished, "from_version": old, "to_version": new,
                 "operation": "install", "result": "success", "duration_seconds": round(time.monotonic()-t0, 3), "backup_id": backup_id})
        prune()
    except Exception as exc:
        finished, msg = utc(), str(exc)[:1200]
        status("failed", "install", "health_check" if backup_id else "preparation",
               "Atualização falhou; estado anterior preservado/restaurado", started, old, new, backup_id, msg, finished)
        history({"started_at": started, "finished_at": finished, "from_version": old, "to_version": new,
                 "operation": "install", "result": "failed", "duration_seconds": round(time.monotonic()-t0, 3),
                 "backup_id": backup_id, "error": msg})
        raise


def do_rollback(backup_id: str) -> None:
    if not re.fullmatch(r"[0-9A-Za-z._-]+", backup_id):
        raise UpdateError("Backup inválido")
    meta = read_json(BACKUPS / backup_id / "metadata.json", {})
    if not isinstance(meta, dict) or not meta.get("version"):
        raise UpdateError("Backup inválido")
    old, new = installed_version(), str(meta["version"])
    started, t0, safety = utc(), time.monotonic(), None
    status("running", "rollback", "backup", "Criando ponto de retorno antes do rollback", started, old, new, backup_id)
    try:
        safety = make_backup(old, new, None)
        try:
            status("running", "rollback", "installation", f"Restaurando {backup_id}", started, old, new, backup_id)
            restore(backup_id)
            status("running", "rollback", "restart", "Reiniciando somente API e collector", started, old, new, backup_id)
            restart_web()
            status("running", "rollback", "health_check", "Validando rollback sem reiniciar RF", started, old, new, backup_id)
            health(new)
        except Exception:
            restore(safety)
            restart_web()
            health(old)
            raise
        finished = utc()
        status("success", "rollback", "done", f"Rollback para {new} concluído", started, old, new, backup_id, finished=finished)
        history({"started_at": started, "finished_at": finished, "from_version": old, "to_version": new,
                 "operation": "rollback", "result": "success", "duration_seconds": round(time.monotonic()-t0, 3), "backup_id": backup_id})
        prune({backup_id})
    except Exception as exc:
        finished, msg = utc(), str(exc)[:1200]
        status("failed", "rollback", "health_check" if safety else "backup",
               "Rollback falhou; estado anterior preservado/restaurado", started, old, new, backup_id, msg, finished)
        history({"started_at": started, "finished_at": finished, "from_version": old, "to_version": new,
                 "operation": "rollback", "result": "failed", "duration_seconds": round(time.monotonic()-t0, 3),
                 "backup_id": backup_id, "error": msg})
        raise


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("pp5ci-hotspot-updater precisa executar como root")
    if len(sys.argv) != 3 or sys.argv[1] not in {"install", "rollback"}:
        raise SystemExit("Uso: pp5ci-hotspot-updater {install <vX.Y.Z>|rollback <backup-id>}")
    STATE.mkdir(parents=True, exist_ok=True)
    LOCK.touch(exist_ok=True)
    with LOCK.open("r+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Já existe uma operação de update/rollback em execução") from exc
        try:
            do_install(sys.argv[2]) if sys.argv[1] == "install" else do_rollback(sys.argv[2])
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

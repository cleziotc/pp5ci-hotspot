#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
[[ "${MODE}" == "vm" || "${MODE}" == "rpi" ]] || { echo "Uso: $0 {vm|rpi}" >&2; exit 2; }

MMDVMHOST_REF="590c531391dfd3146073afbc3956f70d42c62a46"
DSTARGATEWAY_REF="0c1dbb5"
SERVICE_USER="mmdvm"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_ROOT="${BUILD_ROOT:-/usr/local/src/pp5ci-hotspot-build}"
CONFIG_DIR="/etc/pp5ci-hotspot"
APP_DIR="/opt/pp5ci-hotspot"
STATE_DIR="/var/lib/pp5ci-hotspot"
WEB_DIR="/var/www/pp5ci-hotspot"

die() { echo "ERRO: $*" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*"; }

[[ "${EUID}" -eq 0 ]] || die "Execute como root (sudo)."
command -v apt-get >/dev/null || die "Este instalador suporta distribuições Debian/Ubuntu com apt."
[[ -r /dev/tty ]] || die "É necessário um terminal interativo para informar indicativo e senha."

prompt() {
  local __var="$1" __text="$2" __default="${3:-}" value
  if [[ -n "${__default}" ]]; then
    read -r -p "${__text} [${__default}]: " value < /dev/tty
    value="${value:-${__default}}"
  else
    read -r -p "${__text}: " value < /dev/tty
  fi
  printf -v "${__var}" '%s' "${value}"
}

CALLSIGN="${CALLSIGN:-}"
if [[ -z "${CALLSIGN}" ]]; then prompt CALLSIGN "Indicativo do radioamador (ex.: PY2ABC)"; fi
CALLSIGN="${CALLSIGN^^}"
[[ "${CALLSIGN}" =~ ^[A-Z0-9]{3,8}$ ]] || die "Indicativo inválido. Use somente letras e números (3 a 8 caracteres)."

FREQUENCY="${FREQUENCY:-}"
if [[ -z "${FREQUENCY}" ]]; then prompt FREQUENCY "Frequência RX/TX em Hz (ex.: 434000000)" "434000000"; fi
[[ "${FREQUENCY}" =~ ^[0-9]{7,10}$ ]] || die "Frequência inválida; informe o valor inteiro em Hz."

MODULE="${MODULE:-A}"
MODULE="${MODULE^^}"
[[ "${MODULE}" =~ ^[A-D]$ ]] || die "MODULE deve ser A, B, C ou D."

ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
if [[ -z "${ADMIN_PASSWORD}" ]]; then
  while :; do
    read -r -s -p "Crie a senha de administrador do PP5CI Hotspot (mín. 8 caracteres): " ADMIN_PASSWORD < /dev/tty
    echo > /dev/tty
    read -r -s -p "Confirme a senha de administrador: " ADMIN_PASSWORD_CONFIRM < /dev/tty
    echo > /dev/tty
    [[ "${#ADMIN_PASSWORD}" -ge 8 ]] || { echo "A senha precisa ter pelo menos 8 caracteres." > /dev/tty; continue; }
    [[ "${ADMIN_PASSWORD}" == "${ADMIN_PASSWORD_CONFIRM}" ]] || { echo "As senhas não conferem." > /dev/tty; continue; }
    unset ADMIN_PASSWORD_CONFIRM
    break
  done
fi
[[ "${#ADMIN_PASSWORD}" -ge 8 ]] || die "ADMIN_PASSWORD precisa ter pelo menos 8 caracteres."

SERIAL_PORT="${SERIAL_PORT:-}"
RPI_UART_CHANGED=0
if [[ "${MODE}" == "rpi" ]]; then
  [[ -r /proc/device-tree/model ]] || die "Modo Raspberry Pi selecionado, mas o hardware não foi identificado como Raspberry Pi."
  SERIAL_PORT="${SERIAL_PORT:-/dev/serial0}"
else
  if [[ -z "${SERIAL_PORT}" && -d /dev/serial/by-id ]]; then
    SERIAL_PORT="$(find /dev/serial/by-id -maxdepth 1 -type l -print 2>/dev/null | sort | head -1 || true)"
  fi
  if [[ -n "${SERIAL_PORT}" ]]; then
    prompt SERIAL_PORT "Porta serial da MMDVM" "${SERIAL_PORT}"
  else
    prompt SERIAL_PORT "Porta serial da MMDVM (preferir /dev/serial/by-id/...)"
  fi
  [[ -e "${SERIAL_PORT}" ]] || die "Porta serial não encontrada: ${SERIAL_PORT}"
fi

TIMEZONE="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
TIMEZONE="${TIMEZONE:-UTC}"
FREQUENCY_MHZ="$(awk -v f="${FREQUENCY}" 'BEGIN { printf "%.6f", f / 1000000 }')"

echo
echo "PP5CI Hotspot"
echo "  Plataforma : ${MODE}"
echo "  Indicativo : ${CALLSIGN}"
echo "  Módulo     : ${MODULE}"
echo "  Frequência : ${FREQUENCY} Hz (${FREQUENCY_MHZ} MHz)"
echo "  Serial     : ${SERIAL_PORT}"
echo "  Timezone   : ${TIMEZONE}"
echo

say "Instalando dependências"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y build-essential git curl ca-certificates pkg-config nlohmann-json3-dev libcurl4-openssl-dev \
  python3 python3-venv python3-pip mosquitto sudo nginx npm

if ! command -v node >/dev/null || [[ "$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)" -lt 20 ]]; then
  say "Instalando Node.js 22 para compilar o frontend"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if systemctl list-unit-files ModemManager.service >/dev/null 2>&1; then
  systemctl disable --now ModemManager.service || true
fi

if [[ "${MODE}" == "rpi" ]]; then
  say "Configurando UART GPIO do Raspberry Pi"
  BOOT_CONFIG=""
  for candidate in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "${candidate}" ]] && BOOT_CONFIG="${candidate}" && break
  done
  [[ -n "${BOOT_CONFIG}" ]] || die "config.txt do Raspberry Pi não encontrado."
  if ! grep -Eq '^enable_uart=1([[:space:]]|$)' "${BOOT_CONFIG}"; then
    printf '\n# PP5CI Hotspot - MMDVM HAT UART\nenable_uart=1\n' >> "${BOOT_CONFIG}"
    RPI_UART_CHANGED=1
  fi
  for cmdline in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [[ -f "${cmdline}" ]] && grep -Eq 'console=(serial0|ttyAMA0|ttyS0),' "${cmdline}"; then
      cp -a "${cmdline}" "${cmdline}.pp5ci-hotspot.bak"
      sed -E -i 's/(^| )console=(serial0|ttyAMA0|ttyS0),[0-9]+//g; s/  +/ /g; s/^ //; s/ $//' "${cmdline}"
      RPI_UART_CHANGED=1
    fi
  done
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
usermod -aG dialout "${SERVICE_USER}"

say "Compilando MMDVMHost"
rm -rf "${BUILD_ROOT}"
mkdir -p "${BUILD_ROOT}"
git clone https://github.com/g4klx/MMDVM-Host.git "${BUILD_ROOT}/MMDVM-Host"
git -C "${BUILD_ROOT}/MMDVM-Host" checkout "${MMDVMHOST_REF}"
git -C "${BUILD_ROOT}/MMDVM-Host" apply --check "${ROOT_DIR}/patches/MMDVMHost-live-rssi.patch"
git -C "${BUILD_ROOT}/MMDVM-Host" apply "${ROOT_DIR}/patches/MMDVMHost-live-rssi.patch"
make -C "${BUILD_ROOT}/MMDVM-Host" -j"$(nproc)"

say "Compilando DStarGateway"
git clone https://github.com/F4FXL/DStarGateway.git "${BUILD_ROOT}/DStarGateway"
git -C "${BUILD_ROOT}/DStarGateway" checkout "${DSTARGATEWAY_REF}"
make -C "${BUILD_ROOT}/DStarGateway" -j"$(nproc)" CPPFLAGS="-include cstdint -W -O3 -Wall -std=c++17"

say "Instalando cadeia D-Star"
install -d -m 0755 "${APP_DIR}/bin" "${CONFIG_DIR}" /usr/local/share/dstargateway.d
install -m 0755 "${BUILD_ROOT}/MMDVM-Host/MMDVM-Host" "${APP_DIR}/bin/MMDVM-Host"
install -m 0755 "${BUILD_ROOT}/DStarGateway/DStarGateway/dstargateway" "${APP_DIR}/bin/dstargateway"
cp -a "${BUILD_ROOT}/DStarGateway/Data/." /usr/local/share/dstargateway.d/

STAMP="$(date +%Y%m%d-%H%M%S)"
for cfg in "${CONFIG_DIR}/MMDVM-Host.ini" "${CONFIG_DIR}/DStarGateway.cfg" "${CONFIG_DIR}/RSSI.dat"; do
  [[ -f "${cfg}" ]] && cp -a "${cfg}" "${cfg}.bak.${STAMP}"
done
cp "${ROOT_DIR}/config/MMDVM-Host.ini.example" "${CONFIG_DIR}/MMDVM-Host.ini"
cp "${ROOT_DIR}/config/DStarGateway.cfg.example" "${CONFIG_DIR}/DStarGateway.cfg"
install -m 0644 "${ROOT_DIR}/config/RSSI.dat" "${CONFIG_DIR}/RSSI.dat"

sed -i \
  -e "s|__CALLSIGN__|${CALLSIGN}|g" \
  -e "s|__MODULE__|${MODULE}|g" \
  -e "s|__FREQUENCY__|${FREQUENCY}|g" \
  -e "s|__SERIAL_PORT__|${SERIAL_PORT}|g" \
  "${CONFIG_DIR}/MMDVM-Host.ini"
sed -i \
  -e "s|__CALLSIGN__|${CALLSIGN}|g" \
  -e "s|__MODULE__|${MODULE}|g" \
  -e "s|__FREQUENCY_MHZ__|${FREQUENCY_MHZ}|g" \
  "${CONFIG_DIR}/DStarGateway.cfg"

say "Criando senha administrativa com PBKDF2-SHA256"
umask 077
printf '%s' "${ADMIN_PASSWORD}" | python3 -c '
import base64, hashlib, json, os, sys
password = sys.stdin.read().encode()
salt = os.urandom(24)
iterations = 310000
digest = hashlib.pbkdf2_hmac("sha256", password, salt, iterations)
json.dump({
    "algorithm": "pbkdf2-sha256",
    "iterations": iterations,
    "salt": base64.b64encode(salt).decode(),
    "hash": base64.b64encode(digest).decode(),
}, sys.stdout, indent=2)
print()
' > "${CONFIG_DIR}/admin-password.json"
unset ADMIN_PASSWORD
chown root:"${SERVICE_USER}" "${CONFIG_DIR}/admin-password.json"
chmod 0640 "${CONFIG_DIR}/admin-password.json"
umask 022

say "Instalando backend e dependências Python"
rm -rf "${APP_DIR}/backend" "${APP_DIR}/venv"
cp -a "${ROOT_DIR}/backend" "${APP_DIR}/backend"
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/backend/requirements.txt"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0755 "${STATE_DIR}"
install -d -o root -g "${SERVICE_USER}" -m 0750 "${STATE_DIR}/releases"

say "Compilando e publicando frontend"
pushd "${ROOT_DIR}/frontend" >/dev/null
npm ci
npm run build
popd >/dev/null
rm -rf "${WEB_DIR}"
install -d -m 0755 "${WEB_DIR}"
cp -a "${ROOT_DIR}/frontend/dist/." "${WEB_DIR}/"

say "Instalando administração, updater e broker"
install -m 0755 "${ROOT_DIR}/scripts/pp5ci-hotspot-admin.py" /usr/local/sbin/pp5ci-hotspot-admin
install -d -m 0755 /usr/local/libexec
install -m 0755 "${ROOT_DIR}/scripts/pp5ci-hotspot-updater.py" /usr/local/libexec/pp5ci-hotspot-updater
install -m 0440 "${ROOT_DIR}/config/pp5ci-hotspot.sudoers" /etc/sudoers.d/pp5ci-hotspot
visudo -cf /etc/sudoers.d/pp5ci-hotspot >/dev/null
install -d -m 0755 /etc/mosquitto/conf.d
install -m 0644 "${ROOT_DIR}/mosquitto/pp5ci-hotspot.conf" /etc/mosquitto/conf.d/pp5ci-hotspot.conf
cp "${ROOT_DIR}/config/web.env.example" "${CONFIG_DIR}/web.env"
sed -i "s|__TIMEZONE__|${TIMEZONE}|g" "${CONFIG_DIR}/web.env"

say "Instalando serviços systemd"
for unit in "${ROOT_DIR}"/systemd/pp5ci-hotspot-*.service "${ROOT_DIR}"/systemd/pp5ci-hotspot-*.timer; do
  install -m 0644 "${unit}" "/etc/systemd/system/$(basename "${unit}")"
done
systemctl daemon-reload

say "Configurando Nginx"
cat > /etc/nginx/sites-available/pp5ci-hotspot <<'NGINX'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /var/www/pp5ci-hotspot;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 3600;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/pp5ci-hotspot /etc/nginx/sites-enabled/pp5ci-hotspot
nginx -t

say "Ativando serviços"
systemctl enable mosquitto.service nginx.service pp5ci-hotspot-dstargateway.service pp5ci-hotspot-mmdvmhost.service \
  pp5ci-hotspot-collector.service pp5ci-hotspot-api.service pp5ci-hotspot-hosts-update.timer
systemctl restart mosquitto.service
systemctl restart pp5ci-hotspot-dstargateway.service

if [[ "${MODE}" == "rpi" && ! -e "${SERIAL_PORT}" ]]; then
  echo "AVISO: ${SERIAL_PORT} ainda não existe. O MMDVMHost ficará habilitado e iniciará após o reboot."
else
  systemctl restart pp5ci-hotspot-mmdvmhost.service
fi
systemctl restart pp5ci-hotspot-collector.service pp5ci-hotspot-api.service nginx.service
systemctl start pp5ci-hotspot-hosts-update.timer

/usr/local/sbin/pp5ci-hotspot-admin update-hosts <<<'{"restart":true}' || true

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "============================================================"
echo " PP5CI Hotspot instalado"
echo "============================================================"
echo " Indicativo : ${CALLSIGN}"
echo " Interface  : http://${IP:-IP-DESTE-EQUIPAMENTO}/"
echo " Admin      : use a senha criada durante esta instalação"
echo " Updates    : https://github.com/cleziotc/pp5ci-hotspot/releases"
if [[ "${MODE}" == "rpi" ]]; then
  echo " MMDVM HAT  : GPIO UART /dev/serial0 (pinos físicos 8 TX, 10 RX e GND)"
  if [[ "${RPI_UART_CHANGED}" -eq 1 ]]; then
    echo " IMPORTANTE : reinicie o Raspberry Pi para aplicar a configuração da UART."
  fi
fi
echo "============================================================"
